"""Deterministic COBOL parser.

A grammar-driven, division-aware parser for the COBOL subset that matters
for lineage:

* ``ENVIRONMENT DIVISION``  -> SELECT ... ASSIGN TO <DD name>   (file binding)
* ``DATA DIVISION``         -> FD record layouts (incl. COPY expansion from
                               sibling / copybooks/ members)
* ``PROCEDURE DIVISION``    -> MOVE / COMPUTE / STRING transform chains,
                               READ ... INTO (record-level), OPEN direction,
                               EXEC SQL: DECLARE CURSOR + FETCH INTO pairing,
                               static INSERT, dynamic SQL flagging.

Column-level lineage is built by resolving every field of each OUTPUT file
back through the transform chains to either (a) input-file fields or
(b) DB2 columns bound via cursor SELECT lists.

Dynamic SQL (``PREPARE`` / ``EXECUTE IMMEDIATE``) is *flagged*, never guessed.
The implementation is a hand-written division-aware parser behind the same
``parse()`` contract an ANTLR COBOL85 grammar could fulfil.
"""

from __future__ import annotations

import re
from pathlib import Path

from .base import (
    ColumnMapping,
    DynamicConstruct,
    EdgeType,
    EntityNode,
    LineageEdge,
    NodeKind,
    ParseResult,
    UnparsedStatement,
)
from .sql_utils import alias_map, normalize_name, source_columns, split_top_level

_RE_PROGRAM_ID = re.compile(r"PROGRAM-ID\.\s+([A-Z0-9-]+)", re.I)
_RE_SELECT_ASSIGN = re.compile(r"SELECT\s+([A-Z0-9-]+)\s+ASSIGN\s+TO\s+([A-Z0-9-]+)", re.I)
_RE_COPY = re.compile(r"^\s*COPY\s+([A-Z0-9-]+)\s*\.", re.I | re.M)
_RE_FD = re.compile(r"^\s*FD\s+([A-Z0-9-]+)", re.I)
_RE_FIELD = re.compile(r"^\s*(\d{2})\s+([A-Z0-9-]+)(\s+PIC|\s+REDEFINES|\s*\.)", re.I)
_RE_PIC_CLAUSE = re.compile(
    r"\bPIC(?:TURE)?\s+(?:IS\s+)?([-+$*ZB9AXSVP0-9().,/]+(?:CR|DB)?)"
    r"(?:\s+(?:USAGE\s+)?(?:IS\s+)?(COMP-[1-5]|COMP|COMPUTATIONAL(?:-[1-5])?"
    r"|BINARY|PACKED-DECIMAL|DISPLAY))?", re.I)
_RE_LAYOUT_UNSUPPORTED = re.compile(r"\b(OCCURS|REDEFINES)\b", re.I)
_RE_OPEN = re.compile(r"OPEN\s+(INPUT|OUTPUT|EXTEND|I-O)\s+([A-Z0-9-]+)", re.I)
_RE_MOVE = re.compile(
    r"\bMOVE\s+(?:FUNCTION\s+[A-Z0-9-]+\s*\(\s*)*"
    r"(?:FUNCTION\s+[A-Z0-9-]+\s*\(\s*)*([A-Z0-9-]+)[\s)]*\s+TO\s+([A-Z0-9-]+)", re.I)
_RE_COMPUTE = re.compile(
    r"\bCOMPUTE\s+([A-Z0-9-]+)(?:\s+ROUNDED)?\s*=\s*(.+?)"
    r"(?=\bEND-COMPUTE\b|\bON\s+SIZE\b|\.(?:\s|$))", re.I | re.S)
_RE_STRING = re.compile(r"\bSTRING\s+(.+?)\bINTO\s+([A-Z0-9-]+)", re.I | re.S)
_RE_READ_INTO = re.compile(r"\bREAD\s+([A-Z0-9-]+)\s+INTO\s+([A-Z0-9-]+)", re.I)
_RE_EXEC_SQL = re.compile(r"EXEC\s+SQL(.*?)END-EXEC", re.I | re.S)
_RE_SQL_INSERT = re.compile(
    r"INSERT\s+INTO\s+([A-Z0-9_$#.]+)\s*\(([^)]*)\)\s*VALUES\s*\((.*)\)", re.I | re.S)
_RE_DECLARE_CURSOR = re.compile(
    r"DECLARE\s+([A-Z0-9_]+)\s+CURSOR\s+FOR\s+SELECT\s+(.*?)\bFROM\s+(.*)", re.I | re.S)
_RE_FETCH = re.compile(r"FETCH\s+([A-Z0-9_]+)\s+INTO\s+(.*)", re.I | re.S)
_RE_HOST_VAR = re.compile(r":([A-Z0-9-]+)", re.I)
_RE_IDENT = re.compile(r"\b([A-Z][A-Z0-9-]{2,})\b", re.I)
_RE_STATIC_CALL = re.compile(
    r"\bCALL\s+'([A-Z0-9-]+)'\s+USING\s+([A-Z0-9-\s,]+?)\s*(?:\bEND-CALL\b|\.)", re.I)
_RE_PROC_USING = re.compile(
    r"PROCEDURE\s+DIVISION\s+USING\s+([A-Z0-9-\s,]+?)\s*\.", re.I)
_CALL_ARG_NOISE = {"BY", "REFERENCE", "CONTENT", "VALUE"}

# Arithmetic ... GIVING <target>: ADD/SUBTRACT/MULTIPLY/DIVIDE accumulate the
# operand identifiers as sources of the GIVING target (same contract as COMPUTE).
_RE_ARITH_GIVING = re.compile(
    r"\b(ADD|SUBTRACT|MULTIPLY|DIVIDE)\s+(.+?)\s+GIVING\s+(.+?)"
    r"(?=\bREMAINDER\b|\bON\s+SIZE\b|\bNOT\s+ON\b"
    r"|\bEND-(?:ADD|SUBTRACT|MULTIPLY|DIVIDE)\b|\.(?:\s|$))", re.I | re.S)
_ARITH_NOISE = {"TO", "BY", "INTO", "FROM", "GIVING", "ROUNDED", "REMAINDER"}

# EVALUATE conditional bucketing and SEARCH/SEARCH ALL table lookups: the
# variables driving the decision (the EVALUATE subject + WHEN conditions, or the
# SEARCH key argument) become sources of every value the branch assigns - so the
# bucket / looked-up output traces back to the column that selected it.
_RE_EVALUATE = re.compile(r"\bEVALUATE\b(.+?)\bEND-EVALUATE\b", re.I | re.S)
_RE_SEARCH = re.compile(
    r"\bSEARCH\s+(?:ALL\s+)?([A-Z0-9-]+)(.+?)\bEND-SEARCH\b", re.I | re.S)
_RE_WHEN = re.compile(r"\bWHEN\b(.+?)(?=\bWHEN\b|$)", re.I | re.S)
_RE_MOVE_TO_TARGET = re.compile(r"\bMOVE\b.+?\bTO\s+([A-Z0-9-]+)", re.I | re.S)
_RE_MOVE_SUBSCRIPTED = re.compile(
    r"\bMOVE\s+([A-Z0-9-]+)\s*\([^)]*\)\s*TO\s+([A-Z0-9-]+)", re.I)
_RE_COMPUTE_TARGET = re.compile(r"\bCOMPUTE\s+([A-Z0-9-]+)", re.I)
_RE_SEARCH_ARG = re.compile(r"\bWHEN\b[^=<>]*?[=<>]\s*([A-Z][A-Z0-9-]*)", re.I)
_RE_BRANCH_VERB = re.compile(
    r"\b(MOVE|COMPUTE|PERFORM|CONTINUE|SET|ADD|SUBTRACT|MULTIPLY|DIVIDE|GO|NEXT)\b",
    re.I)
_EVAL_NOISE = {"TRUE", "FALSE", "OTHER", "WHEN", "ALSO", "THRU", "THROUGH",
               "AND", "OR", "NOT", "EVALUATE", "END-EVALUATE", "ANY"}

_COBOL_KEYWORDS = {
    "MOVE", "TO", "COMPUTE", "STRING", "INTO", "DELIMITED", "BY", "SIZE",
    "SPACE", "SPACES", "ZERO", "ZEROS", "ZEROES", "END-STRING", "END-COMPUTE",
    "PERFORM", "UNTIL", "READ", "OPEN", "CLOSE", "INPUT", "OUTPUT", "AT",
    "END", "NOT", "SET", "TRUE", "STOP", "RUN", "VALUE", "PIC", "FILLER",
    "FUNCTION", "TRIM", "LENGTH", "CURRENT-DATE", "REVERSE", "UPPER-CASE",
    "LOWER-CASE", "NUMVAL",
}
_LITERAL_SOURCES = {"SPACES", "SPACE", "ZEROS", "ZEROES", "ZERO",
                    "HIGH-VALUES", "LOW-VALUES", "QUOTES"}


def _normalize(path: Path) -> list[tuple[int, str]]:
    """Strip fixed-format columns: keep area A+B (cols 8-72), drop comments."""
    out: list[tuple[int, str]] = []
    for lineno, raw in enumerate(path.read_text().splitlines(), start=1):
        if len(raw) < 7:
            continue
        if raw[6] in ("*", "/"):
            continue
        code = raw[7:72].rstrip()
        if code.strip():
            out.append((lineno, code))
    return out


def _find_copybook(member: str, source_dir: Path) -> Path | None:
    candidates = list(source_dir.iterdir())
    for sub in ("copybooks", "COPYBOOKS", "copylib"):
        if (source_dir / sub).is_dir():
            candidates.extend((source_dir / sub).iterdir())
    for candidate in candidates:
        if (candidate.is_file() and candidate.stem.upper() == member
                and candidate.suffix.lower() in (".cpy", ".cob", ".cbl")):
            return candidate
    return None


def _expand_copybooks(lines: list[tuple[int, str]], source_dir: Path) -> list[tuple[int, str]]:
    """Inline COPY <member> from copybook files (deterministic expansion)."""
    expanded: list[tuple[int, str]] = []
    for lineno, code in lines:
        m = _RE_COPY.match(code)
        if not m:
            expanded.append((lineno, code))
            continue
        member = _find_copybook(m.group(1).upper(), source_dir)
        if member is not None:
            expanded.extend(_normalize(member))
        else:  # copybook not found - keep the COPY line so nothing is invented
            expanded.append((lineno, code))
    return expanded


def _expand_pic(pic: str) -> str:
    """'X(20)' -> 'XXXX...' ; repeat factors expanded, case-normalised."""
    return re.sub(r"([-+$*ZB90AXSVP])\((\d+)\)",
                  lambda m: m.group(1) * int(m.group(2)), pic.upper())


def _pic_storage_length(pic: str, usage: str | None) -> int:
    """Storage bytes for one elementary item (the subset needed for FDs)."""
    usage = (usage or "").upper().replace("COMPUTATIONAL", "COMP")
    if usage in ("COMP-1",):
        return 4
    if usage in ("COMP-2",):
        return 8
    expanded = _expand_pic(pic)
    digits = expanded.count("9")
    if usage in ("COMP-3", "PACKED-DECIMAL"):
        return digits // 2 + 1
    if usage in ("COMP", "COMP-4", "COMP-5", "BINARY"):
        return 2 if digits <= 4 else 4 if digits <= 9 else 8
    # DISPLAY (incl. numeric-edited): S, V and P occupy no storage
    return len([c for c in expanded if c not in "SVP"])


def _strip_literals(text: str) -> str:
    return re.sub(r"'[^']*'|\"[^\"]*\"", " ", text)


def _blank_literals(text: str) -> str:
    """Replace literal contents with spaces, preserving every offset."""
    return re.sub(r"'[^']*'|\"[^\"]*\"",
                  lambda m: "'" + " " * (len(m.group(0)) - 2) + "'", text)


def _src_line(lines: list[tuple[int, str]], text: str, pos: int) -> int:
    """Map an offset in the joined normalised text to the original line no."""
    idx = text[:pos].count("\n")
    return lines[min(idx, len(lines) - 1)][0]


# Detectors for data-movement-shaped statements the transform engine does
# not model.  Each hit becomes an UnparsedStatement (coverage telemetry).
_UNPARSED_DETECTORS: list[tuple[str, re.Pattern, str]] = [
    ("COBOL_CALL", re.compile(r"\bCALL\s+\S+(?:\s+USING\b[^.]*)?", re.I),
     "inter-program data flow (CALL ... USING) is not traced"),
    ("COBOL_UNSTRING", re.compile(r"\bUNSTRING\b[^.]*", re.I | re.S),
     "UNSTRING field splitting is not modelled"),
    ("COBOL_MOVE_CORRESPONDING",
     re.compile(r"\bMOVE\s+CORR(?:ESPONDING)?\b[^.]*", re.I),
     "MOVE CORRESPONDING requires group-structure matching"),
    ("COBOL_WRITE_FROM",
     re.compile(r"\bWRITE\s+[A-Z0-9-]+\s+FROM\s+[A-Z0-9-]+", re.I),
     "WRITE ... FROM record movement is not traced"),
    ("COBOL_EXEC_CICS", re.compile(r"\bEXEC\s+CICS\b.*?END-EXEC", re.I | re.S),
     "CICS commands are not supported"),
]

# EXEC SQL verbs that move no data (skipped silently); every other verb is
# either handled (DECLARE/FETCH/INSERT/PREPARE/EXECUTE) or flagged unparsed.
_BENIGN_SQL_VERBS = {"INCLUDE", "OPEN", "CLOSE", "COMMIT", "ROLLBACK",
                     "WHENEVER", "CONNECT", "SET", "LOCK"}


class CobolParser:
    language = "COBOL"

    def __init__(self):
        # per-program machinery kept for cross-program CALL resolution
        # (consumed by resolve_calls after the whole tree is parsed)
        self._artifacts: dict[str, dict] = {}

    def parse(self, path: Path) -> ParseResult:
        lines = _expand_copybooks(_normalize(path), path.parent)
        text = "\n".join(code for _, code in lines)
        result = ParseResult(path=str(path), language=self.language)

        m = _RE_PROGRAM_ID.search(text)
        program = m.group(1).upper() if m else path.stem.upper()
        program_node = EntityNode(
            kind=NodeKind.PROGRAM, name=program, language=self.language, path=str(path))
        result.nodes.append(program_node)

        logical_to_dd = {l.upper(): d.upper() for l, d in _RE_SELECT_ASSIGN.findall(text)}
        file_fields, file_layouts = self._parse_fds(lines)
        ws_groups = self._parse_ws_groups(lines)
        open_modes = {f.upper(): mode.upper() for mode, f in _RE_OPEN.findall(text)}

        # --- file nodes; map every file field to its owning entity --------
        field_owner: dict[str, str] = {}
        file_nodes: dict[str, EntityNode] = {}   # logical name -> node
        for logical, dd in logical_to_dd.items():
            fields = file_fields.get(logical, [])
            attributes = {"logical_file": logical, "bound_via": "ASSIGN"}
            if logical in file_layouts:
                attributes["record_layout"] = file_layouts[logical]
            node = EntityNode(
                kind=NodeKind.FILE, name=dd, columns=fields,
                attributes=attributes)
            result.nodes.append(node)
            file_nodes[logical] = node
            for f in fields:
                field_owner[f] = node.id

        transforms = self._parse_transforms(text, logical_to_dd, file_nodes, ws_groups)
        # whole-record MOVE recA TO recB (a byte-for-byte group copy) -> expand
        # to elementary field lineage and fold into the transform graph so it
        # chains transitively (WS/LINKAGE intermediaries, READ INTO, etc.)
        records = self._parse_record_layouts(lines)
        self._expand_group_moves(text, records, file_nodes, {},
                                 transforms, program, result)
        # EVALUATE bucketing / SEARCH lookups: decision drivers -> branch
        # outputs (and the spans they consume, so telemetry does not re-flag
        # the literal / subscripted MOVEs inside them)
        conditional_spans = self._parse_conditionals(text, transforms)
        ws_literals = self._parse_ws_literals(lines)
        self._parse_exec_sql(lines, text, program, program_node, field_owner,
                             transforms, ws_literals, result)
        self._detect_unparsed(lines, text, program, result, conditional_spans)

        # --- entity edges + column mappings for OUTPUT files --------------
        output_edges: list[tuple[LineageEdge, EntityNode]] = []
        for logical, node in file_nodes.items():
            mode = open_modes.get(logical, "INPUT")
            if mode == "INPUT":
                result.edges.append(LineageEdge(
                    source_id=node.id, target_id=program_node.id,
                    edge_type=EdgeType.READS_FROM, program=program,
                    evidence=f"SELECT {logical} ASSIGN TO {node.name} / OPEN INPUT"))
            else:
                mappings = self._build_write_mappings(node, transforms, field_owner)
                edge = LineageEdge(
                    source_id=program_node.id, target_id=node.id,
                    edge_type=EdgeType.WRITES_TO, program=program,
                    transformation=f"OPEN {mode} {logical}",
                    column_mappings=mappings,
                    evidence=f"SELECT {logical} ASSIGN TO {node.name} / OPEN {mode}")
                result.edges.append(edge)
                output_edges.append((edge, node))

        self._artifacts[program] = {
            "program_node": program_node,
            "transforms": transforms,
            "field_owner": field_owner,
            "ws_groups": ws_groups,
            "linkage_groups": self._parse_section_groups(lines, "LINKAGE SECTION"),
            "linkage_params": self._parse_linkage_params(text),
            "call_sites": self._parse_call_sites(lines, text),
            "output_edges": output_edges,
        }
        return result

    def _build_write_mappings(self, node: EntityNode, transforms: dict,
                              field_owner: dict) -> list[ColumnMapping]:
        mappings: list[ColumnMapping] = []
        for field in node.columns:
            sources, logics = self._resolve(field, transforms, field_owner)
            sources = [s for s in sources if not s.startswith(node.id)]
            if not sources:
                continue
            steps = list(dict.fromkeys(s for s in logics if s))  # source->target
            mappings.append(ColumnMapping(
                source_columns=sources,
                target_column=f"{node.id}|{field}",
                transformation=("; ".join(steps) or "direct")[:1000],
                transform_steps=steps))
        return mappings

    def _parse_record_layouts(self, lines: list[tuple[int, str]]) -> dict:
        """Symbol table of every 01-level record/group area across the FILE,
        WORKING-STORAGE and LINKAGE sections: ``record name -> {section, fd,
        fields:[{field,start,length}], valid}``.  ``fields`` are the elementary
        items with 1-based byte offsets (COBOL group-move semantics are a
        byte-for-byte copy, so byte offset is the field correspondence).  FILE
        records also carry ``fd`` (the logical file that owns the bytes).
        ``valid`` is False if OCCURS/REDEFINES makes offsets non-linear."""
        records: dict[str, dict] = {}
        section: str | None = None
        fd_name: str | None = None
        cur: str | None = None
        for _, code in lines:
            u = code.upper().strip()
            if u.startswith("FILE SECTION"):
                section, fd_name, cur = "FILE", None, None
                continue
            if u.startswith("WORKING-STORAGE SECTION"):
                section, fd_name, cur = "WORKING-STORAGE", None, None
                continue
            if u.startswith("LINKAGE SECTION"):
                section, fd_name, cur = "LINKAGE", None, None
                continue
            if u.startswith("PROCEDURE DIVISION"):
                break
            if section is None:
                continue
            fd = _RE_FD.match(code)
            if fd and section == "FILE":
                fd_name, cur = fd.group(1).upper(), None
                continue
            fm = _RE_FIELD.match(code)
            if not fm:
                continue
            level, name = int(fm.group(1)), fm.group(2).upper()
            if level == 88:
                continue
            if level == 1:
                cur = name
                records[cur] = {"section": section,
                                "fd": fd_name if section == "FILE" else None,
                                "fields": [], "offset": 1, "valid": True}
                continue
            if cur is None:
                continue
            rec = records[cur]
            if _RE_LAYOUT_UNSUPPORTED.search(code):
                rec["valid"] = False
            pic = _RE_PIC_CLAUSE.search(code)
            if pic:
                length = _pic_storage_length(pic.group(1).rstrip("."), pic.group(2))
                if name != "FILLER":
                    rec["fields"].append({"field": name, "start": rec["offset"],
                                          "length": length})
                rec["offset"] += length
        for rec in records.values():
            rec.pop("offset", None)
        # keep only true GROUP records (>=2 subordinate fields): an elementary
        # 01 (a single PIC X area, e.g. a metric/print line) is one field, so a
        # MOVE into it is an ordinary elementary move the transform graph
        # already resolves - not a group copy.
        return {k: v for k, v in records.items() if len(v["fields"]) >= 2}

    def _expand_group_moves(self, text, records, file_nodes, fd_to_logical,
                            transforms, program, result) -> None:
        """Generic whole-record move resolution.  ``MOVE recA TO recB`` where
        both are known record areas is a byte-for-byte copy; expand it to
        elementary field correspondences (paired by byte offset) and feed them
        into the transform graph so they chain transitively - through WS/LINKAGE
        intermediaries, READ INTO, and further moves - exactly like elementary
        MOVEs.  A source field on a FILE record is a qualified terminal
        (``<file_id>|field``); on a WS/LINKAGE record it stays a bare name the
        resolver chains further.  A move whose records cannot be aligned
        deterministically lands in COVERAGE telemetry - never silently dropped,
        never guessed (the agentic layer may still propose a correspondence)."""
        for m in _RE_MOVE.finditer(text):
            s, t = m.group(1).upper(), m.group(2).upper()
            if s not in records or t not in records:
                continue                      # not a record-to-record move
            pairs = self._pair_record_fields(records[s], records[t])
            if not pairs:
                line = text[:m.start()].count("\n") + 1
                result.unparsed.append(UnparsedStatement(
                    program=program, language=self.language,
                    statement_type="COBOL_GROUP_MOVE",
                    snippet=f"MOVE {s} TO {t}", path=result.path, line=line,
                    reason="group move between records with no alignable byte "
                           "layout (OCCURS/REDEFINES or mismatched structure)"))
                continue
            src_owner = self._record_entity_id(records[s], file_nodes, fd_to_logical)
            for sf, tf in pairs:
                src_ref = f"{src_owner}|{sf}" if src_owner else sf
                # an internal self-named pass-through (WS<->LINKAGE copy of the
                # same copybook, e.g. the MVC comm area) neither introduces a
                # source nor renames a field - it carries no lineage and only
                # adds noise to every field's transform chain, so skip it.
                if src_ref == tf:
                    continue
                self._add_transform(
                    transforms, tf, [src_ref],
                    f"group move: MOVE {s} TO {t} (whole-record copy)")

    @staticmethod
    def _pair_record_fields(srec: dict, trec: dict) -> list[tuple[str, str]]:
        """Pair source/target elementary fields of a group move.  By BYTE START
        position when both layouts are reliable (the correct COBOL semantics);
        ordinal only as a fallback when offsets are unavailable but the field
        counts match; otherwise no pairing (caller routes to telemetry)."""
        sf, tf = srec["fields"], trec["fields"]
        if not sf or not tf:
            return []
        if srec["valid"] and trec["valid"]:
            src_by_start = {f["start"]: f["field"] for f in sf}
            return [(src_by_start[t["start"]], t["field"])
                    for t in tf if t["start"] in src_by_start]
        if len(sf) == len(tf):
            return [(a["field"], b["field"]) for a, b in zip(sf, tf)]
        return []

    @staticmethod
    def _record_entity_id(rec: dict, file_nodes: dict,
                          fd_to_logical: dict) -> str | None:
        """The lineage entity that owns a record's bytes: its FILE node id for
        an FD record, else None (a WS/LINKAGE area is internal - its fields
        chain on through the transform graph)."""
        fd = rec.get("fd")
        logical = fd_to_logical.get(fd, fd) if fd else None
        node = file_nodes.get(logical) if logical else None
        return node.id if node else None

    def _parse_call_sites(self, lines, text) -> list[dict]:
        """Static CALL 'literal' USING sites (dynamic targets stay telemetry)."""
        sites = []
        for m in _RE_STATIC_CALL.finditer(text):
            args = [a for a in re.split(r"[,\s]+", m.group(2).upper())
                    if a and a not in _CALL_ARG_NOISE]
            sites.append({"callee": m.group(1).upper(), "args": args,
                          "line": _src_line(lines, text, m.start())})
        return sites

    def _parse_linkage_params(self, text: str) -> list[str]:
        m = _RE_PROC_USING.search(text)
        if not m:
            return []
        return [p for p in re.split(r"[,\s]+", m.group(1).upper()) if p]

    # ------------------------------------------------------------------
    def resolve_calls(self, combined: ParseResult) -> None:
        """Deterministic nested-CALL lineage across parsed programs.

        CALL ... USING passes storage by reference: caller argument <n> and
        callee PROCEDURE DIVISION USING parameter <n> describe the same
        record.  When both sides expand the same copybook the child field
        names match exactly - those children inherit the callee's terminal
        sources (e.g. DB2 columns bound via FETCH INTO).  No name match,
        no mapping: unmatched calls stay in coverage telemetry.
        """
        for caller, art in self._artifacts.items():
            for call in art["call_sites"]:
                callee_art = self._artifacts.get(call["callee"])
                if callee_art is None:
                    self._update_call_telemetry(
                        combined, caller, call["line"],
                        reason=f"callee '{call['callee']}' source not in scan "
                               "scope; inter-program data flow not traced")
                    continue

                combined.edges.append(LineageEdge(
                    source_id=art["program_node"].id,
                    target_id=callee_art["program_node"].id,
                    edge_type=EdgeType.EXECUTES, program=caller,
                    transformation=f"CALL '{call['callee']}' USING "
                                   + " ".join(call["args"]),
                    evidence=f"static CALL at {Path(combined.path).name} "
                             f"caller {caller} line {call['line']}"))

                injected = 0
                for arg, param in zip(call["args"], callee_art["linkage_params"]):
                    caller_children = set(art["ws_groups"].get(arg, []))
                    callee_children = callee_art["linkage_groups"].get(param, [])
                    for child in callee_children:
                        if child not in caller_children:
                            continue
                        sources, logics = self._resolve(
                            child, callee_art["transforms"],
                            callee_art["field_owner"])
                        if not sources:
                            continue
                        logic = (f"CALL '{call['callee']}' USING {arg}->{param}: "
                                 + ("; ".join(dict.fromkeys(logics)) or "direct"))
                        self._add_transform(art["transforms"], child,
                                            sources, logic[:800])
                        injected += 1

                if injected:
                    # re-resolve the caller's output mappings with the
                    # cross-program transforms now in place, and retire the
                    # COBOL_CALL telemetry entry *by mapping it*
                    for edge, node in art["output_edges"]:
                        edge.column_mappings = self._build_write_mappings(
                            node, art["transforms"], art["field_owner"])
                    self._update_call_telemetry(
                        combined, caller, call["line"], remove=True)
                else:
                    self._update_call_telemetry(
                        combined, caller, call["line"],
                        reason=f"callee '{call['callee']}' linked (EXECUTES) but "
                               "no USING parameter field could be matched")

    @staticmethod
    def _update_call_telemetry(combined: ParseResult, program: str, line: int,
                               reason: str | None = None,
                               remove: bool = False) -> None:
        for u in list(combined.unparsed):
            if (u.statement_type == "COBOL_CALL" and u.program == program
                    and u.line == line):
                if remove:
                    combined.unparsed.remove(u)
                elif reason:
                    u.reason = reason

    # ------------------------------------------------------------------
    def _parse_fds(self, lines: list[tuple[int, str]]
                   ) -> tuple[dict[str, list[str]], dict[str, list[dict]]]:
        """Logical file name -> elementary field names under its FD, plus a
        byte-position layout (1-based start/length from the PIC clauses) so
        downstream consumers (DFSORT control-card resolution) can map byte
        ranges back to fields.  A layout containing OCCURS / REDEFINES is
        dropped rather than guessed (offsets would no longer be linear)."""
        fields: dict[str, list[str]] = {}
        layouts: dict[str, list[dict]] = {}
        layout_valid: dict[str, bool] = {}
        offsets: dict[str, int] = {}
        current: str | None = None
        in_file_section = False
        for _, code in lines:
            upper = code.upper().strip()
            if upper.startswith("FILE SECTION"):
                in_file_section = True
                continue
            if in_file_section and upper.endswith("SECTION.") and "FILE" not in upper:
                in_file_section = False
            if not in_file_section:
                continue
            fd = _RE_FD.match(code)
            if fd:
                current = fd.group(1).upper()
                fields.setdefault(current, [])
                layouts.setdefault(current, [])
                layout_valid.setdefault(current, True)
                offsets.setdefault(current, 1)
                continue
            if current:
                fm = _RE_FIELD.match(code)
                if not fm:
                    continue
                level, name = int(fm.group(1)), fm.group(2).upper()
                if level == 88:
                    continue
                if _RE_LAYOUT_UNSUPPORTED.search(code):
                    layout_valid[current] = False
                pic = _RE_PIC_CLAUSE.search(code)
                if pic:                       # elementary item: advance offset
                    # a trailing '.' is the statement period, not an edit char
                    length = _pic_storage_length(pic.group(1).rstrip("."),
                                                 pic.group(2))
                    if name != "FILLER":
                        layouts[current].append({
                            "field": name, "start": offsets[current],
                            "length": length})
                    offsets[current] += length
                if name == "FILLER":
                    continue
                # elementary 01 record (e.g. 01 XML-OUTPUT-RECORD PIC X)
                if level > 1 or "PIC" in fm.group(3).upper():
                    fields[current].append(name)
        return (fields,
                {k: v for k, v in layouts.items()
                 if v and layout_valid.get(k, False)})

    def _parse_ws_groups(self, lines: list[tuple[int, str]]) -> dict[str, list[str]]:
        return self._parse_section_groups(lines, "WORKING-STORAGE SECTION")

    def _parse_section_groups(self, lines: list[tuple[int, str]],
                              section: str) -> dict[str, list[str]]:
        """01 group name -> child field names within one DATA DIVISION section."""
        groups: dict[str, list[str]] = {}
        current: str | None = None
        in_section = False
        for _, code in lines:
            upper = code.upper().strip()
            if upper.startswith(section):
                in_section = True
                continue
            if in_section and (upper.startswith("PROCEDURE DIVISION")
                               or (upper.endswith("SECTION.") and not upper.startswith(section.split()[0]))):
                in_section = False
            if not in_section:
                continue
            fm = _RE_FIELD.match(code)
            if fm:
                level, name = int(fm.group(1)), fm.group(2).upper()
                if level == 1:
                    current = name
                    groups.setdefault(current, [])
                elif current and level != 88 and name != "FILLER":
                    groups[current].append(name)
        return groups

    # ------------------------------------------------------------------
    def _add_transform(self, transforms: dict, target: str,
                       sources: list[str], logic: str) -> None:
        """Accumulate (conditional branches both contribute sources)."""
        target = target.upper()
        if target in transforms:
            old_sources, old_logic = transforms[target]
            merged = list(dict.fromkeys(old_sources + sources))
            logic = old_logic if logic in old_logic else f"{old_logic}; {logic}"
            transforms[target] = (merged, logic)
        else:
            transforms[target] = (sources, logic)

    def _parse_transforms(self, text: str, logical_to_dd: dict,
                          file_nodes: dict, ws_groups: dict) -> dict:
        transforms: dict[str, tuple[list[str], str]] = {}
        for src, tgt in _RE_MOVE.findall(text):
            if src.upper() in _LITERAL_SOURCES:
                continue
            self._add_transform(transforms, tgt, [src.upper()],
                                f"MOVE {src.upper()} TO {tgt.upper()}")
        for tgt, expr in _RE_COMPUTE.findall(text):
            srcs = [i.upper() for i in _RE_IDENT.findall(_strip_literals(expr))
                    if i.upper() not in _COBOL_KEYWORDS]
            self._add_transform(transforms, tgt, srcs,
                                f"COMPUTE {tgt.upper()} = {' '.join(expr.split())}")
        for body, tgt in _RE_STRING.findall(text):
            srcs = [i.upper() for i in _RE_IDENT.findall(_strip_literals(body))
                    if i.upper() not in _COBOL_KEYWORDS]
            self._add_transform(transforms, tgt, srcs,
                                f"STRING {' '.join(body.split())} INTO {tgt.upper()}")
        # ADD/SUBTRACT/MULTIPLY/DIVIDE ... GIVING <target(s)>: operand fields
        # are the sources of each GIVING target (same contract as COMPUTE).
        for verb, operands, targets in _RE_ARITH_GIVING.findall(text):
            srcs = [i.upper() for i in _RE_IDENT.findall(_strip_literals(operands))
                    if i.upper() not in _COBOL_KEYWORDS
                    and i.upper() not in _ARITH_NOISE]
            tgts = [t.upper() for t in _RE_IDENT.findall(targets)
                    if t.upper() not in _ARITH_NOISE]
            logic = (f"{verb.upper()} {' '.join(operands.split())} "
                     f"GIVING {' '.join(targets.split())}")
            for tgt in tgts:
                self._add_transform(transforms, tgt, srcs, logic)
        # READ <file> INTO <ws-group>: record-level lineage - every child of
        # the group descends from the input file (no positional guessing).
        for logical, group in _RE_READ_INTO.findall(text):
            node = file_nodes.get(logical.upper())
            if node is None:
                continue
            token = f"{node.id}|*"
            logic = f"READ {logical.upper()} INTO {group.upper()} (record-level)"
            for child in ws_groups.get(group.upper(), []):
                self._add_transform(transforms, child, [token], logic)
        return transforms

    @staticmethod
    def _cond_idents(fragment: str) -> list[str]:
        """Field identifiers participating in a condition (literals, COBOL
        keywords and EVALUATE/relational noise removed)."""
        return [i.upper() for i in _RE_IDENT.findall(_strip_literals(fragment))
                if i.upper() not in _COBOL_KEYWORDS
                and i.upper() not in _EVAL_NOISE]

    def _parse_conditionals(self, text: str, transforms: dict) -> list[tuple[int, int]]:
        """EVALUATE bucketing + SEARCH/SEARCH ALL lookups -> column lineage.

        The decision drivers (EVALUATE subject + WHEN conditions, or the SEARCH
        key argument) become sources of every value assigned inside the branch,
        so a bucketed status / looked-up rate traces back to the field that
        selected it - even when the assigned value itself is a literal or a
        subscripted table cell the elementary transform engine cannot follow.

        Returns the character spans consumed, so ``_detect_unparsed`` does not
        re-flag the literal / reference-modified / subscripted MOVEs inside them.
        """
        spans: list[tuple[int, int]] = []

        # ---- EVALUATE ... END-EVALUATE ------------------------------------
        for ev in _RE_EVALUATE.finditer(text):
            spans.append(ev.span())
            block = ev.group(1)
            head = re.split(r"\bWHEN\b", block, maxsplit=1, flags=re.I)[0]
            drivers = self._cond_idents(head)
            for wm in _RE_WHEN.finditer(block):
                vb = _RE_BRANCH_VERB.search(wm.group(1))
                cond = wm.group(1)[:vb.start()] if vb else wm.group(1)
                drivers.extend(self._cond_idents(cond))
            drivers = list(dict.fromkeys(drivers))
            if not drivers:
                continue
            targets = {m.group(1).upper()
                       for m in _RE_MOVE_TO_TARGET.finditer(block)}
            targets |= {m.group(1).upper()
                        for m in _RE_COMPUTE_TARGET.finditer(block)}
            logic = f"EVALUATE bucketing on {', '.join(drivers)}"
            for tgt in targets:
                self._add_transform(transforms, tgt, drivers, logic)

        # ---- SEARCH / SEARCH ALL ... END-SEARCH ---------------------------
        for sm in _RE_SEARCH.finditer(text):
            spans.append(sm.span())
            table, body = sm.group(1).upper(), sm.group(2)
            args = list(dict.fromkeys(a.upper() for a in _RE_SEARCH_ARG.findall(body)))
            done: set[str] = set()
            # MOVE table-value(idx) TO target: the lookup result + its key driver
            for valfield, tgt in _RE_MOVE_SUBSCRIPTED.findall(body):
                tgt = tgt.upper()
                srcs = list(dict.fromkeys(args + [valfield.upper()]))
                self._add_transform(
                    transforms, tgt, srcs,
                    f"SEARCH ALL {table}: lookup {valfield.upper()} keyed on "
                    f"{', '.join(args) or 'index'}")
                done.add(tgt)
            if not args:
                continue
            # remaining branch assignments (e.g. AT END default) trace to the key
            for m in _RE_MOVE_TO_TARGET.finditer(body):
                tgt = m.group(1).upper()
                if tgt not in done:
                    self._add_transform(transforms, tgt, args,
                                        f"SEARCH ALL {table}: default keyed on "
                                        f"{', '.join(args)}")
            for m in _RE_COMPUTE_TARGET.finditer(body):
                self._add_transform(transforms, m.group(1).upper(), args,
                                    f"SEARCH ALL {table} keyed on {', '.join(args)}")
        return spans

    def _resolve(self, var: str, transforms: dict, field_owner: dict,
                 depth: int = 0, seen: frozenset = frozenset()) -> tuple[list[str], list[str]]:
        """Resolve a variable to qualified terminal sources + the logic chain.

        ``logics`` is ordered SOURCE -> TARGET: the deepest (closest to the
        origin column) step first, this variable's own step last, so the chain
        reads the way data actually flows (e.g. ``TRIM(A.COL); MOVE HV-X TO
        OUT-FLD``) and the frontend can render the WS hops in order."""
        var = var.upper()
        if depth > 12 or var in seen:
            return [], []
        if "|" in var:                       # already-qualified terminal ref
            return [var], []
        # transform chain first: an output-file field is both a field and a
        # transform target - its lineage is the chain, not itself
        if var in transforms:
            sources, logic = transforms[var]
            resolved, logics = [], []
            for s in sources:
                r, l = self._resolve(s, transforms, field_owner,
                                     depth + 1, seen | {var})
                resolved.extend(r)
                logics.extend(l)
            logics.append(logic)             # this step is closest to target
            return list(dict.fromkeys(resolved)), logics
        if var in field_owner:               # file field terminal
            return [f"{field_owner[var]}|{var}"], []
        return [], []

    def _parse_ws_literals(self, lines: list[tuple[int, str]]) -> dict[str, str]:
        """WORKING-STORAGE field -> its VALUE 'literal' (dynamic-SQL context)."""
        literals: dict[str, str] = {}
        current: str | None = None
        in_ws = False
        for _, code in lines:
            upper = code.upper().strip()
            if upper.startswith("WORKING-STORAGE SECTION"):
                in_ws = True
                continue
            if in_ws and (upper.startswith("PROCEDURE DIVISION")
                          or (upper.endswith("SECTION.")
                              and "WORKING-STORAGE" not in upper)):
                in_ws = False
            if not in_ws:
                continue
            fm = _RE_FIELD.match(code)
            if fm:
                current = fm.group(2).upper()
            m = re.search(r"\bVALUE\s+(?:IS\s+)?'([^']*)'", code, re.I)
            if m and current:
                literals[current] = m.group(1)
        return literals

    def _host_var_context(self, sql: str, transforms: dict,
                          ws_literals: dict[str, str]) -> str:
        """How the host variables of a dynamic statement are assembled:
        the immediate transform logic plus any literal VALUEs feeding it,
        so the AI sees e.g. the static table-name prefix of a built INSERT."""
        parts: list[str] = []
        for hv in _RE_HOST_VAR.findall(sql):
            sources, logic = transforms.get(hv.upper(), ([], ""))
            if logic:
                parts.append(logic)
            for s in sources:
                if s in ws_literals:
                    parts.append(f"{s} VALUE '{ws_literals[s]}'")
        return "\n".join(dict.fromkeys(parts))

    # ------------------------------------------------------------------
    def _parse_exec_sql(self, lines, text, program, program_node,
                        field_owner, transforms, ws_literals,
                        result: ParseResult) -> None:
        cursors: dict[str, list[tuple[list[str], str]]] = {}
        for m in _RE_EXEC_SQL.finditer(text):
            sql = " ".join(m.group(1).split())
            upper = sql.upper()
            verb = upper.split()[0] if upper.split() else ""
            if verb in _BENIGN_SQL_VERBS:
                continue

            line = text[:m.start()].count("\n") + 1
            src_line = lines[min(line - 1, len(lines) - 1)][0]

            if "PREPARE" in upper or "EXECUTE IMMEDIATE" in upper \
                    or upper.startswith("EXECUTE "):
                ctx_start = max(0, line - 20)
                context = "\n".join(code for _, code in lines[ctx_start:line + 5])
                assembly = self._host_var_context(sql, transforms, ws_literals)
                if assembly:
                    context += "\n*> host-variable assembly:\n" + assembly
                result.dynamic_constructs.append(DynamicConstruct(
                    program=program, language=self.language,
                    construct_type="DYNAMIC_SQL",
                    snippet=f"EXEC SQL {sql} END-EXEC",
                    context=context, path=result.path, line=src_line))
                continue

            dc = _RE_DECLARE_CURSOR.search(sql)
            if dc:
                self._handle_cursor(dc, cursors, program, program_node, result)
                continue

            ft = _RE_FETCH.search(sql)
            if ft:
                host_vars = _RE_HOST_VAR.findall(ft.group(2))
                for (srcs, logic), hv in zip(cursors.get(ft.group(1).upper(), []),
                                             host_vars):
                    if srcs:
                        self._add_transform(transforms, hv, srcs, logic)
                continue

            ins = _RE_SQL_INSERT.search(sql)
            if ins:
                self._handle_insert(ins, sql, program, program_node,
                                    field_owner, transforms, result)
                continue

            # detected, not mapped -> coverage telemetry, never silent
            result.unparsed.append(UnparsedStatement(
                program=program, language=self.language,
                statement_type=f"EXEC_SQL_{verb}",
                snippet=f"EXEC SQL {sql} END-EXEC"[:300],
                path=result.path, line=src_line,
                reason=f"embedded SQL verb '{verb}' is not mapped to lineage"))

    # ------------------------------------------------------------------
    def _detect_unparsed(self, lines, text, program, result: ParseResult,
                         skip_spans: list[tuple[int, int]] | None = None) -> None:
        """Flag data-movement-shaped statements the transform engine skipped.

        ``skip_spans`` are EVALUATE/SEARCH blocks already resolved to lineage
        by ``_parse_conditionals``; MOVEs inside them (literal buckets,
        subscripted lookups) are mapped, not gaps, so they are not re-flagged.
        """
        blanked = _blank_literals(text)
        skip_spans = skip_spans or []

        def in_skip(pos: int) -> bool:
            return any(s <= pos < e for s, e in skip_spans)

        # MOVEs the transform regex could not parse (e.g. reference
        # modification: MOVE FUNCTION CURRENT-DATE(1:8) TO WS-DATE)
        matched_moves = {m.start() for m in _RE_MOVE.finditer(blanked)}
        for m in re.finditer(r"\bMOVE\s+[^\s'][^']*?\s+TO\s+[A-Z0-9-]+",
                             blanked, re.I):
            if m.start() in matched_moves or "CORR" in m.group(0).upper() \
                    or in_skip(m.start()):
                continue
            result.unparsed.append(UnparsedStatement(
                program=program, language=self.language,
                statement_type="COBOL_MOVE",
                snippet=" ".join(text[m.start():m.end()].split())[:200],
                path=result.path, line=_src_line(lines, text, m.start()),
                reason="MOVE source expression not supported "
                       "(reference modification / subscripting)"))

        for stype, pattern, reason in _UNPARSED_DETECTORS:
            for m in pattern.finditer(blanked):
                if in_skip(m.start()):
                    continue
                result.unparsed.append(UnparsedStatement(
                    program=program, language=self.language,
                    statement_type=stype,
                    snippet=" ".join(text[m.start():m.end()].split())[:200],
                    path=result.path, line=_src_line(lines, text, m.start()),
                    reason=reason))

    def _handle_cursor(self, dc, cursors, program, program_node, result) -> None:
        cursor, select_list, tail = dc.group(1).upper(), dc.group(2), dc.group(3)
        from_clause = re.split(r"\bWHERE\b|\bGROUP\s+BY\b|\bORDER\s+BY\b",
                               tail, flags=re.I)[0]
        aliases = alias_map(from_clause)
        for table in sorted(set(aliases.values())):
            table_node = EntityNode(kind=NodeKind.TABLE, name=table,
                                    attributes={"dbms": "DB2"})
            result.nodes.append(table_node)
            result.edges.append(LineageEdge(
                source_id=table_node.id, target_id=program_node.id,
                edge_type=EdgeType.READS_FROM, program=program,
                transformation=f"CURSOR {cursor}",
                evidence=f"DECLARE {cursor} CURSOR FOR SELECT ... FROM {table}"))
        exprs = split_top_level(select_list)
        cursors[cursor] = [
            (source_columns(expr, aliases), " ".join(expr.split()))
            for expr in exprs]

    def _handle_insert(self, ins, sql, program, program_node,
                       field_owner, transforms, result) -> None:
        table = normalize_name(ins.group(1))
        cols = [c.strip().upper() for c in ins.group(2).split(",")]
        host_vars = _RE_HOST_VAR.findall(ins.group(3))
        table_node = EntityNode(kind=NodeKind.TABLE, name=table, columns=cols)
        result.nodes.append(table_node)

        mappings: list[ColumnMapping] = []
        for col, hv in zip(cols, host_vars):
            resolved, logics = self._resolve(hv, transforms, field_owner)
            if not resolved:
                continue
            mappings.append(ColumnMapping(
                source_columns=resolved,
                target_column=f"{table_node.id}|{col}",
                transformation=("; ".join(dict.fromkeys(logics)) or "direct")[:400]))
        result.edges.append(LineageEdge(
            source_id=program_node.id, target_id=table_node.id,
            edge_type=EdgeType.WRITES_TO, program=program,
            transformation=f"INSERT INTO {table}",
            column_mappings=mappings,
            evidence=f"EXEC SQL {sql} END-EXEC"[:500]))
