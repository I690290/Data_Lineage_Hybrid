"""DFSORT / SyncSort (IBM mainframe dialect) control-card column resolver.

Turns a SORT utility step's inline SYSIN deck into deterministic
column-level lineage:

* ``JOINKEYS FILES=Fn,FIELDS=(p,l,o,...)``  -> join-key byte ranges per input
* ``JOIN UNPAIRED,...``                     -> join type (metadata)
* ``REFORMAT FIELDS=(Fn:p,l,...)``          -> joined-record byte composition
* ``SORT/MERGE FIELDS=(...)``               -> ordering only (no movement)
* ``INREC/OUTREC FIELDS|BUILD=(p,l,...)``   -> record re-build
* ``OUTFIL FNAMES=dd,INCLUDE=(...),BUILD=(p,l,...)`` -> output re-build/filter

Byte ranges are mapped back to fields by intersecting them with the
``record_layout`` (1-based start/length per field) that the COBOL parser
recovers from the copybooks of the programs reading/writing the same
datasets - the orchestrator runs this *after* DD cross-linking so the
layouts already sit on the physical ``FILE:<DSN>`` nodes.

Determinism contract: an unsupported card token or a missing layout emits
``UnparsedStatement`` coverage telemetry (``JCL_SORT_CONTROL``), never a
guessed mapping.
"""

from __future__ import annotations

import re

from .base import (
    ColumnMapping,
    EdgeType,
    EntityNode,
    NodeKind,
    ParseResult,
    UnparsedStatement,
)

_SORT_UTILITIES = {"SORT", "DFSORT", "ICETOOL", "ICEMAN"}

_RE_FILES = re.compile(r"FILES?=([A-Z0-9]+)", re.I)
_RE_FIELDS = re.compile(r"(?:FIELDS|BUILD)=\(([^)]*)\)", re.I)
_RE_FNAMES = re.compile(r"FNAMES=([A-Z0-9]+)", re.I)
_RE_NUM = re.compile(r"^\d+$")


class UnsupportedCard(Exception):
    """A movement-shaped control card we detected but cannot map."""


# ---------------------------------------------------------------------------
# control-card parsing
# ---------------------------------------------------------------------------
def _join_continuations(cards: list[str]) -> list[str]:
    """DFSORT continuation: a line ending in ',' or '-' continues."""
    stmts: list[str] = []
    pending = ""
    for raw in cards:
        line = raw.strip()
        if not line:
            continue
        pending += line
        if pending.endswith(",") or pending.endswith("-"):
            pending = pending.rstrip("-")
            continue
        stmts.append(pending)
        pending = ""
    if pending:
        stmts.append(pending)
    return stmts


def _split_top_level(s: str) -> list[str]:
    """Split on commas outside parentheses / quotes."""
    parts, depth, cur, in_str = [], 0, "", False
    for ch in s:
        if ch == "'":
            in_str = not in_str
        elif not in_str:
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
            elif ch == "," and depth == 0:
                parts.append(cur)
                cur = ""
                continue
        cur += ch
    if cur:
        parts.append(cur)
    return parts


def _parse_pos_len_pairs(body: str, stmt: str) -> list[tuple[int, int]]:
    """'1,20,A,21,10,A' / '1,20,CH,A,...' / '1,20,21,10' -> [(start,len),...]

    Non-numeric tokens between pairs (order/format flags) are skipped;
    anything else (literals, edit masks, %nn parse fields) is unsupported.
    """
    tokens = [t.strip() for t in body.split(",") if t.strip()]
    pairs: list[tuple[int, int]] = []
    i = 0
    while i < len(tokens):
        if not _RE_NUM.match(tokens[i]):
            raise UnsupportedCard(
                f"unsupported token '{tokens[i]}' in {stmt.split()[0]} card")
        if i + 1 >= len(tokens) or not _RE_NUM.match(tokens[i + 1]):
            raise UnsupportedCard(
                f"dangling position '{tokens[i]}' in {stmt.split()[0]} card")
        pairs.append((int(tokens[i]), int(tokens[i + 1])))
        i += 2
        # skip trailing format/order flags (CH, A, D, PD, ZD, BI, ...)
        while i < len(tokens) and not _RE_NUM.match(tokens[i]):
            if not re.fullmatch(r"[A-Z]{1,3}\d?", tokens[i], re.I):
                raise UnsupportedCard(
                    f"unsupported token '{tokens[i]}' in {stmt.split()[0]} card")
            i += 1
    return pairs


def _parse_reformat(body: str) -> list[tuple[str, int, int]]:
    """'F2:1,160' / 'F1:1,20,F2:5,10,30,8' -> [(tag,start,len),...]"""
    segments: list[tuple[str, int, int]] = []
    tag = None
    nums: list[int] = []

    def flush():
        if len(nums) % 2:
            raise UnsupportedCard("odd position/length list in REFORMAT card")
        for j in range(0, len(nums), 2):
            segments.append((tag, nums[j], nums[j + 1]))
        nums.clear()

    for token in (t.strip() for t in body.split(",") if t.strip()):
        if ":" in token:
            head, rest = token.split(":", 1)
            if tag is not None:
                flush()
            tag = head.upper()
            token = rest
        if not _RE_NUM.match(token):
            raise UnsupportedCard(
                f"unsupported token '{token}' in REFORMAT card (?/FILL not mapped)")
        if tag is None:
            raise UnsupportedCard("REFORMAT positions before any Fn: tag")
        nums.append(int(token))
    flush()
    return segments


def _parse_cards(cards: list[str]) -> dict:
    """Structured view of the deck; raises UnsupportedCard when a
    movement-shaped card contains syntax we do not model."""
    spec: dict = {"joinkeys": {}, "join": None, "reformat": None,
                  "sort": None, "rebuilds": [], "outfil_dd": None,
                  "include": None}
    for stmt in _join_continuations(cards):
        if stmt.lstrip().startswith("*"):
            continue                          # DFSORT comment line
        op = stmt.split()[0].upper() if stmt.split() else ""
        operands = stmt[len(op):].replace(" ", "")
        if op == "JOINKEYS":
            fm, dm = _RE_FILES.search(operands), _RE_FIELDS.search(operands)
            if not fm or not dm:
                raise UnsupportedCard("JOINKEYS without FILES=/FIELDS=")
            spec["joinkeys"][fm.group(1).upper()] = \
                _parse_pos_len_pairs(dm.group(1), stmt)
        elif op == "JOIN":
            spec["join"] = operands
        elif op == "REFORMAT":
            dm = _RE_FIELDS.search(operands)
            if not dm:
                raise UnsupportedCard("REFORMAT without FIELDS=")
            spec["reformat"] = _parse_reformat(dm.group(1))
        elif op in ("SORT", "MERGE"):
            spec["sort"] = operands          # ordering only - no data movement
        elif op in ("INREC", "OUTREC"):
            dm = _RE_FIELDS.search(operands)
            if not dm:
                raise UnsupportedCard(f"{op} without FIELDS=/BUILD=")
            spec["rebuilds"].append(_parse_pos_len_pairs(dm.group(1), stmt))
        elif op == "OUTFIL":
            for part in _split_top_level(operands):
                key = part.split("=", 1)[0].upper()
                if key == "FNAMES":
                    spec["outfil_dd"] = _RE_FNAMES.search(part).group(1).upper()
                elif key == "BUILD":
                    dm = _RE_FIELDS.search(part)
                    spec["rebuilds"].append(
                        _parse_pos_len_pairs(dm.group(1), stmt))
                elif key in ("INCLUDE", "OMIT"):
                    spec["include"] = part   # row filter - no column movement
                else:
                    raise UnsupportedCard(f"unsupported OUTFIL operand '{key}'")
        elif op in ("OPTION", "ALTSEQ", "END", "SUM", "OMIT", "INCLUDE"):
            continue                          # no column movement modelled
        else:
            raise UnsupportedCard(f"unsupported control card '{op}'")
    return spec


# ---------------------------------------------------------------------------
# byte-range algebra
# ---------------------------------------------------------------------------
def _apply_build(segments: list[tuple[str, int, int]],
                 build: list[tuple[int, int]]) -> list[tuple[str, int, int]]:
    """Re-build a record laid out by `segments` (consecutive from byte 1):
    each BUILD (start,len) selects bytes of the current record and lays them
    consecutively in the new one."""
    out: list[tuple[str, int, int]] = []
    for b_start, b_len in build:
        need_lo, need_hi = b_start, b_start + b_len - 1
        pos = 1
        for tag, src_start, length in segments:
            seg_lo, seg_hi = pos, pos + length - 1
            lo, hi = max(need_lo, seg_lo), min(need_hi, seg_hi)
            if lo <= hi:
                out.append((tag, src_start + (lo - seg_lo), hi - lo + 1))
            pos += length
    return out


def _fields_in_range(layout: list[dict], lo: int, hi: int) -> list[dict]:
    return [f for f in layout
            if f["start"] <= hi and f["start"] + f["length"] - 1 >= lo]


def _source_ranges_for(segments, tag, lo, hi):
    """Output-byte ranges (out_lo, out_hi) fed from `tag` bytes [lo, hi]."""
    ranges, pos = [], 1
    for seg_tag, src_start, length in segments:
        src_lo, src_hi = src_start, src_start + length - 1
        if seg_tag == tag:
            o_lo, o_hi = max(lo, src_lo), min(hi, src_hi)
            if o_lo <= o_hi:
                ranges.append((pos + (o_lo - src_lo), pos + (o_hi - src_lo)))
        pos += length
    return ranges


# ---------------------------------------------------------------------------
# orchestrator entry point
# ---------------------------------------------------------------------------
def resolve_sort_columns(result: ParseResult) -> None:
    nodes_by_id = {n.id: n for n in result.nodes}
    for node in result.nodes:
        if (node.kind != NodeKind.PROGRAM
                or node.attributes.get("utility") not in _SORT_UTILITIES
                or not node.attributes.get("control_cards")):
            continue
        try:
            _resolve_step(node, nodes_by_id, result)
        except UnsupportedCard as exc:
            result.unparsed.append(UnparsedStatement(
                program=node.name, language="JCL",
                statement_type="JCL_SORT_CONTROL",
                snippet="\n".join(node.attributes["control_cards"])[:300],
                path=node.path or "", line=0,
                reason=f"SORT control cards detected but not mapped: {exc}"))


def _layout_of(nodes_by_id: dict[str, EntityNode], dsn: str) -> list[dict]:
    file_node = nodes_by_id.get(f"{NodeKind.FILE.value}:{dsn}".upper())
    layout = file_node.attributes.get("record_layout") if file_node else None
    if not layout:
        raise UnsupportedCard(f"no record layout recovered for dataset {dsn}")
    return layout


def _resolve_step(node: EntityNode, nodes_by_id: dict, result: ParseResult) -> None:
    spec = _parse_cards(node.attributes["control_cards"])
    inputs = {d["dd_name"].upper(): d["dsn"] for d in
              node.attributes.get("input_dds", [])}
    outputs = {d["dd_name"].upper(): d["dsn"] for d in
               node.attributes.get("output_dds", [])}
    if not inputs or not outputs:
        return

    # ---- bind JOINKEYS tags (F1/F2) to input DDs -----------------------
    def dd_for_tag(tag: str) -> str:
        n = tag[1:] if tag.upper().startswith("F") and tag[1:].isdigit() else None
        candidates = ([f"SORTJNF{n}", f"SORTIN{int(n):02d}", f"SORTIN{n}"]
                      if n else [tag.upper()])
        for dd in candidates:
            if dd in inputs:
                return inputs[dd]
        raise UnsupportedCard(f"no input DD found for JOINKEYS file {tag}")

    tag_dsn: dict[str, str] = {t: dd_for_tag(t) for t in spec["joinkeys"]}

    # ---- joined/base record composition --------------------------------
    if spec["reformat"] is not None:
        segments = [(tag, start, length)
                    for tag, start, length in spec["reformat"]]
        for tag, _, _ in segments:
            if tag not in tag_dsn:
                tag_dsn[tag] = dd_for_tag(tag)
    elif spec["joinkeys"]:
        raise UnsupportedCard("JOINKEYS without REFORMAT is not mapped")
    else:
        # plain SORT/MERGE/COPY: single input passed through
        if len(inputs) != 1:
            raise UnsupportedCard("multiple SORTIN inputs without REFORMAT")
        dsn = next(iter(inputs.values()))
        tag_dsn = {"F1": dsn}
        layout = _layout_of(nodes_by_id, dsn)
        record_len = max(f["start"] + f["length"] - 1 for f in layout)
        segments = [("F1", 1, record_len)]

    for build in spec["rebuilds"]:
        segments = _apply_build(segments, build)

    # ---- output file + layouts -----------------------------------------
    out_dsn = (inputs.get(spec["outfil_dd"]) or outputs.get(spec["outfil_dd"])
               if spec["outfil_dd"] else None) or next(iter(outputs.values()))
    out_layout = _layout_of(nodes_by_id, out_dsn)
    layouts = {tag: _layout_of(nodes_by_id, dsn) for tag, dsn in tag_dsn.items()}
    out_id = f"{NodeKind.FILE.value}:{out_dsn}".upper()
    file_ids = {tag: f"{NodeKind.FILE.value}:{dsn}".upper()
                for tag, dsn in tag_dsn.items()}

    mappings: dict[str, ColumnMapping] = {}

    def add(sources: list[str], target_field: str, logic: str) -> None:
        target = f"{out_id}|{target_field}"
        if target in mappings:
            cm = mappings[target]
            cm.source_columns = list(dict.fromkeys(cm.source_columns + sources))
            if logic not in cm.transformation:
                cm.transformation = f"{cm.transformation}; {logic}"[:400]
        else:
            mappings[target] = ColumnMapping(
                source_columns=list(dict.fromkeys(sources)),
                target_column=target, transformation=logic[:400])

    # ---- pass-through data lineage (REFORMAT/BUILD byte moves) ----------
    pos = 1
    for tag, src_start, length in segments:
        out_lo, out_hi = pos, pos + length - 1
        for tgt in _fields_in_range(out_layout, out_lo, out_hi):
            t_lo = max(out_lo, tgt["start"])
            t_hi = min(out_hi, tgt["start"] + tgt["length"] - 1)
            s_lo = src_start + (t_lo - out_lo)
            s_hi = src_start + (t_hi - out_lo)
            srcs = [f"{file_ids[tag]}|{f['field']}"
                    for f in _fields_in_range(layouts[tag], s_lo, s_hi)]
            if srcs:
                add(srcs, tgt["field"],
                    f"DFSORT {tag}[{s_lo}:{s_hi}] -> OUT[{t_lo}:{t_hi}] "
                    f"(REFORMAT/BUILD)")
        pos += length

    # ---- join-key lineage: keys of one side flow to the output fields ---
    # fed by the matching key bytes of the other side
    tags = list(spec["joinkeys"])
    for a in tags:
        for b in tags:
            if a == b:
                continue
            for (a_start, a_len), (b_start, b_len) in zip(
                    spec["joinkeys"][a], spec["joinkeys"][b]):
                a_fields = _fields_in_range(
                    layouts[a], a_start, a_start + a_len - 1)
                for out_lo, out_hi in _source_ranges_for(
                        segments, b, b_start, b_start + b_len - 1):
                    for tgt in _fields_in_range(out_layout, out_lo, out_hi):
                        srcs = [f"{file_ids[a]}|{f['field']}" for f in a_fields]
                        if srcs:
                            add(srcs, tgt["field"],
                                f"JOINKEYS {a}=({a_start},{a_len}) matched "
                                f"{b}=({b_start},{b_len})"
                                + (f" [JOIN {spec['join']}]" if spec["join"] else ""))

    if not mappings:
        return
    write_edge = next(
        (e for e in result.edges
         if e.program == node.name and e.edge_type == EdgeType.WRITES_TO
         and e.source_id == node.id and e.target_id == out_id), None)
    if write_edge is not None:
        write_edge.column_mappings.extend(mappings.values())
