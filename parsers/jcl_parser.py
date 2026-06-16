"""Deterministic JCL parser.

Extracts, per job:

* the JOB card                          -> ``Job`` node
* ``EXEC PGM=``  steps                  -> ``EXECUTES`` edges
* application program steps             -> (program, DD name) -> DSN bindings,
      used by the orchestrator to re-point COBOL logical files onto physical
      datasets (the COBOL side knows direction and columns).
* utility steps (SORT/ICETOOL/IDCAMS/IEBGENER) -> per-step ``Program`` nodes
      with READS_FROM / WRITES_TO edges derived from ``DISP=`` (SHR/OLD read,
      NEW/MOD write); inline ``SYSIN DD *`` control cards are captured as the
      step's transformation logic (e.g. DFSORT JOINKEYS).
* FTP steps                             -> the ``put <local> <remote>`` is
      parsed from the inline INPUT deck; a remote name containing an
      unresolved symbolic (e.g. ``&DATE``) is flagged for AI resolution.
* ``// SET SYM=VAL``                    -> local symbol table; ``&SYM`` /
      ``&SYM.`` substitution is deterministic.  A DSN still containing ``&``
      afterwards depends on a system symbol -> flagged ``JCL_SYMBOLIC``.
* TSO/E batch monitors (IKJEFT01/IKJEFT1A/IKJEFT1B) -> the ``SYSTSIN`` deck
      is inspected for ``RUN PROGRAM(...)``:
        - DSNTIAUL  -> ``SYSIN`` SELECTs become table READS_FROM + column-
          mapped WRITES_TO onto the paired ``SYSRECnn`` unload datasets.
        - DSNTEP2/4 -> dynamic SQL executor; DML statements are coverage
          telemetry (``JCL_TSO_SQL``), never guessed.
        - any other program -> treated like ``EXEC PGM=`` (DD bindings are
          handed to the COBOL side for direction and columns).
      A missing/non-inline SYSTSIN or an unrecognised command stream lands
      in telemetry (``JCL_TSO_SYSTSIN`` / ``JCL_TSO_RUN``).
* ``IEFBR14`` housekeeping steps are skipped (no data movement).
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
from .sql_utils import RE_FROM_CLAUSE, alias_map, source_columns, split_top_level

_RE_SYMBOL = re.compile(r"&([A-Z@#$][A-Z0-9@#$]*)\.?")
_RE_DSN = re.compile(r"DSN=([^,\s]+)", re.I)
_RE_DISP = re.compile(r"DISP=\(?([A-Z]+)", re.I)
_RE_PGM = re.compile(r"PGM=([A-Z0-9@#$]+)", re.I)
_RE_FTP_PUT = re.compile(r"\bput\s+'([^']+)'\s+(\S+)", re.I | re.S)
_RE_TSO_RUN = re.compile(r"\bRUN\s+PROGRAM\s*\(\s*([A-Z0-9@#$]+)\s*\)", re.I)
_RE_TSO_PLAN = re.compile(r"\bPLAN\s*\(\s*([A-Z0-9@#$]+)\s*\)", re.I)
_RE_SELECT_LIST = re.compile(r"^\s*SELECT\s+(.*?)\bFROM\b", re.I | re.S)
_RE_SIMPLE_COL = re.compile(r"^(?:[A-Z0-9_]+\.)?([A-Z0-9_]+)$", re.I)

_UTILITY_PGMS = {"SORT", "DFSORT", "ICETOOL", "ICEMAN", "IDCAMS", "IEBGENER", "IEBCOPY"}
_TSO_PGMS = {"IKJEFT01", "IKJEFT1A", "IKJEFT1B"}   # TSO/E batch monitors
_SKIP_PGMS = {"IEFBR14"}
_NON_DATA_DDS = {"STEPLIB", "JOBLIB", "SYSOUT", "SYSPRINT", "SYSIN",
                 "SYSDBOUT", "SYSUDUMP", "DBRM", "INPUT", "OUTPUT",
                 "SYSTSPRT", "SYSPUNCH", "CEEDUMP"}


def _substitute(value: str, symbols: dict[str, str]) -> str:
    """Apply local SET symbols; ``&SYM.`` consumes the trailing dot."""
    def repl(m: re.Match) -> str:
        sym = m.group(1).upper()
        return symbols.get(sym, m.group(0))

    prev = None
    while prev != value:
        prev = value
        value = _RE_SYMBOL.sub(repl, value)
    return value


def _read_statements(path: Path) -> list[dict]:
    """JCL statements with continuations joined and inline DD * data attached."""
    statements: list[dict] = []
    pending: dict | None = None
    collecting_inline = False
    for lineno, raw in enumerate(path.read_text().splitlines(), start=1):
        if raw.startswith("//*"):
            continue
        if not raw.startswith("//"):
            if raw.startswith("/*"):
                collecting_inline = False
            elif collecting_inline and statements:
                statements[-1]["inline"].append(raw.rstrip())
            continue
        collecting_inline = False
        body = raw[2:72].rstrip()
        if pending is not None:
            pending["text"] += body.lstrip()
            if not pending["text"].rstrip().endswith(","):
                statements.append(pending)
                pending = None
            continue
        stmt = {"line": lineno, "text": body, "inline": []}
        if body.rstrip().endswith(","):
            pending = stmt
        else:
            statements.append(stmt)
            if re.search(r"\bDD\s+(\*|DATA)\s*$", body):
                collecting_inline = True
    if pending is not None:
        statements.append(pending)
    return statements


class JclParser:
    language = "JCL"

    def parse(self, path: Path) -> ParseResult:
        result = ParseResult(path=str(path), language=self.language)
        statements = _read_statements(path)

        job_name = path.stem.upper()
        symbols: dict[str, str] = {}
        bindings: list[dict] = []
        step: str | None = None
        pgm: str | None = None
        util_node: EntityNode | None = None
        sysin_cards: list[str] = []
        tso: dict | None = None
        job_node = None

        def flush_sysin():
            """Attach captured control cards to the utility's write edges."""
            if util_node is None or not sysin_cards:
                return
            cards = "\n".join(sysin_cards)[:600]
            util_node.attributes["control_cards"] = list(sysin_cards)
            for e in result.edges:
                if e.program == util_node.name and e.edge_type == EdgeType.WRITES_TO:
                    e.transformation = cards

        def flush_tso():
            """Resolve a completed IKJEFT* step from its SYSTSIN deck."""
            nonlocal tso
            if tso is None:
                return
            ctx, tso = tso, None
            if not ctx["systsin"]:
                result.unparsed.append(UnparsedStatement(
                    program=job_name, language=self.language,
                    statement_type="JCL_TSO_SYSTSIN",
                    snippet=f"//{ctx['step']} EXEC PGM={ctx['monitor']}",
                    path=str(path), line=ctx["line"],
                    reason="SYSTSIN is not an inline deck; the TSO command "
                           "stream cannot be inspected"))
                return
            deck = "\n".join(ctx["systsin"])
            run = _RE_TSO_RUN.search(deck)
            if run is None:
                result.unparsed.append(UnparsedStatement(
                    program=job_name, language=self.language,
                    statement_type="JCL_TSO_RUN",
                    snippet=deck[:200], path=str(path), line=ctx["line"],
                    reason="no RUN PROGRAM(...) in SYSTSIN; TSO command "
                           "stream is not mapped"))
                return
            run_pgm = run.group(1).upper()
            plan = (_RE_TSO_PLAN.search(deck) or [None, ""])[1].upper()
            if run_pgm == "DSNTIAUL":
                self._handle_dsntiaul(ctx, plan, symbols, result, job_name,
                                      str(path))
            elif run_pgm in ("DSNTEP2", "DSNTEP4"):
                self._handle_dsntep(ctx, run_pgm, plan, result, job_name,
                                    str(path))
            else:
                # application program run under the TSO monitor: same
                # contract as EXEC PGM= - COBOL supplies direction + columns
                pgm_node = EntityNode(kind=NodeKind.PROGRAM, name=run_pgm,
                                      language="COBOL")
                result.nodes.append(pgm_node)
                result.edges.append(LineageEdge(
                    source_id=f"{NodeKind.JOB.value}:{job_name}".upper(),
                    target_id=pgm_node.id, edge_type=EdgeType.EXECUTES,
                    program=job_name,
                    evidence=f"//{ctx['step']} EXEC PGM={ctx['monitor']} / "
                             f"SYSTSIN RUN PROGRAM({run_pgm})"))
                for dd in ctx["dds"]:
                    dsn = _substitute(dd["dsn"], symbols)
                    if "&" in dsn or "(" in dsn or dsn.startswith("*."):
                        result.unparsed.append(UnparsedStatement(
                            program=run_pgm, language=self.language,
                            statement_type="JCL_TSO_RUN",
                            snippet=f"//{dd['name']} DD DSN={dd['dsn']}"[:200],
                            path=str(path), line=dd["line"],
                            reason="dataset reference under TSO RUN step is "
                                   "not statically resolvable"))
                        continue
                    bindings.append({"job": job_name, "step": ctx["step"],
                                     "program": run_pgm,
                                     "dd_name": dd["name"], "dsn": dsn})

        for stmt in statements:
            fields = stmt["text"].split(None, 2)
            if not fields:
                continue

            if fields[0].upper() == "SET":         # "// SET SYM=VAL"
                for assign in fields[1].split(","):
                    if "=" in assign:
                        k, v = assign.split("=", 1)
                        symbols[k.strip().upper()] = _substitute(v.strip(), symbols)
                continue
            if fields[0].upper() in ("DD", "PEND", "EXEC", "IF", "ENDIF"):
                continue                            # unnamed continuation/concat
            if len(fields) < 2:
                continue

            name, op = fields[0].upper(), fields[1].upper()
            params = fields[2] if len(fields) > 2 else ""

            if op == "JOB":
                job_name = name
                job_node = EntityNode(kind=NodeKind.JOB, name=job_name,
                                      language=self.language, path=str(path))
                result.nodes.append(job_node)

            elif op == "INCLUDE":
                result.unparsed.append(UnparsedStatement(
                    program=job_name, language=self.language,
                    statement_type="JCL_INCLUDE",
                    snippet=f"//{name} INCLUDE {params}"[:200],
                    path=str(path), line=stmt["line"],
                    reason="INCLUDE member expansion is not supported"))

            elif op == "EXEC":
                flush_sysin()
                flush_tso()
                sysin_cards, util_node = [], None
                m = _RE_PGM.search(params)
                if not m:
                    # EXEC <proc> - cataloged/in-stream procedure invocation:
                    # the steps live in the proc member we cannot see here.
                    proc = params.split(",")[0].replace("PROC=", "").strip()
                    result.unparsed.append(UnparsedStatement(
                        program=job_name, language=self.language,
                        statement_type="JCL_PROC",
                        snippet=f"//{name} EXEC {params}"[:200],
                        path=str(path), line=stmt["line"],
                        reason=f"procedure '{proc}' invocation - PROC "
                               "expansion is not supported"))
                    step = pgm = None
                    continue
                step, pgm = name, m.group(1).upper()
                if pgm in _SKIP_PGMS:
                    pgm = None
                    continue
                if pgm in _TSO_PGMS:
                    # defer: the step's meaning is in the SYSTSIN deck
                    tso = {"step": step, "monitor": pgm, "line": stmt["line"],
                           "systsin": None, "sysin": [], "dds": []}
                    continue
                if pgm in _UTILITY_PGMS or pgm == "FTP":
                    util_node = EntityNode(
                        kind=NodeKind.PROGRAM, name=f"{pgm}.{step}",
                        language="JCL-UTILITY", path=str(path),
                        attributes={"job": job_name, "step": step, "utility": pgm})
                    result.nodes.append(util_node)
                    target_id = util_node.id
                else:
                    pgm_node = EntityNode(kind=NodeKind.PROGRAM, name=pgm,
                                          language="COBOL")
                    result.nodes.append(pgm_node)
                    target_id = pgm_node.id
                result.edges.append(LineageEdge(
                    source_id=f"{NodeKind.JOB.value}:{job_name}".upper(),
                    target_id=target_id, edge_type=EdgeType.EXECUTES,
                    program=job_name, evidence=f"//{step} EXEC PGM={pgm}"))

            elif op == "DD" and tso is not None:
                if name == "SYSTSIN" and stmt["inline"]:
                    tso["systsin"] = stmt["inline"]
                elif name == "SYSIN" and stmt["inline"]:
                    tso["sysin"] = stmt["inline"]
                elif name not in _NON_DATA_DDS:
                    dm = _RE_DSN.search(params)
                    if dm:
                        disp = (_RE_DISP.search(params) or [None, "SHR"])[1]
                        tso["dds"].append({
                            "name": name, "dsn": dm.group(1).upper(),
                            "disp": disp.upper(), "line": stmt["line"]})

            elif op == "DD" and pgm:
                if name in ("SYSIN", "INPUT") and stmt["inline"]:
                    sysin_cards = stmt["inline"]
                    if pgm == "FTP" and util_node is not None:
                        self._handle_ftp(stmt, util_node, symbols, result,
                                         job_name, step)
                    continue
                if name in _NON_DATA_DDS:
                    continue
                m = _RE_DSN.search(params)
                if not m:
                    continue
                raw_dsn = m.group(1).upper()
                if raw_dsn.startswith("*."):
                    result.unparsed.append(UnparsedStatement(
                        program=pgm, language=self.language,
                        statement_type="JCL_REFERBACK",
                        snippet=f"//{name} DD DSN={raw_dsn}"[:200],
                        path=str(path), line=stmt["line"],
                        reason="backward reference (DSN=*.step.dd) is not resolved"))
                    continue
                if "(" in raw_dsn:
                    is_gdg = bool(re.search(r"\(([+-]?\d+)\)", raw_dsn))
                    result.unparsed.append(UnparsedStatement(
                        program=pgm, language=self.language,
                        statement_type="JCL_GDG" if is_gdg else "JCL_PDS_MEMBER",
                        snippet=f"//{name} DD DSN={raw_dsn}"[:200],
                        path=str(path), line=stmt["line"],
                        reason=("GDG generation reference is not resolved"
                                if is_gdg else
                                "PDS member dataset reference is not mapped")))
                    continue
                dsn = _substitute(raw_dsn, symbols)
                if "&" in dsn:
                    set_lines = [f"// SET {k}={v}" for k, v in symbols.items()]
                    result.dynamic_constructs.append(DynamicConstruct(
                        program=(util_node.name if util_node else pgm),
                        language=self.language, construct_type="JCL_SYMBOLIC",
                        snippet=f"//{name} DD DSN={m.group(1).upper()}",
                        context="\n".join(set_lines + [
                            f"//{step} EXEC PGM={pgm}",
                            f"//{name} DD {params}"]),
                        path=str(path), line=stmt["line"]))
                    continue

                ds_node = EntityNode(
                    kind=NodeKind.FILE, name=dsn,
                    attributes={"dd_name": name, "job": job_name, "step": step})
                result.nodes.append(ds_node)

                if util_node is not None:
                    # utility step: direction from DISP
                    disp = (_RE_DISP.search(params) or [None, "SHR"])[1].upper()
                    if disp in ("NEW", "MOD"):
                        util_node.attributes.setdefault("output_dds", []).append(
                            {"dd_name": name, "dsn": dsn})
                        result.edges.append(LineageEdge(
                            source_id=util_node.id, target_id=ds_node.id,
                            edge_type=EdgeType.WRITES_TO, program=util_node.name,
                            evidence=f"//{name} DD DSN={dsn},DISP={disp}"))
                    else:
                        util_node.attributes.setdefault("input_dds", []).append(
                            {"dd_name": name, "dsn": dsn})
                        result.edges.append(LineageEdge(
                            source_id=ds_node.id, target_id=util_node.id,
                            edge_type=EdgeType.READS_FROM, program=util_node.name,
                            evidence=f"//{name} DD DSN={dsn},DISP={disp}"))
                else:
                    # application step: COBOL supplies direction + columns
                    bindings.append({"job": job_name, "step": step,
                                     "program": pgm, "dd_name": name, "dsn": dsn})

        flush_sysin()
        flush_tso()
        if job_node is not None:
            job_node.attributes["dd_bindings"] = bindings
        return result

    # ------------------------------------------------------------------
    def _handle_dsntiaul(self, ctx: dict, plan: str, symbols: dict,
                         result: ParseResult, job_name: str, path: str) -> None:
        """DSNTIAUL unload: SYSIN SELECT <n> writes dataset SYSREC<n>."""
        step = ctx["step"]
        util = EntityNode(
            kind=NodeKind.PROGRAM, name=f"DSNTIAUL.{step}",
            language="JCL-UTILITY", path=path,
            attributes={"job": job_name, "step": step,
                        "utility": ctx["monitor"], "db2_program": "DSNTIAUL",
                        "plan": plan, "systsin": list(ctx["systsin"])})
        result.nodes.append(util)
        result.edges.append(LineageEdge(
            source_id=f"{NodeKind.JOB.value}:{job_name}".upper(),
            target_id=util.id, edge_type=EdgeType.EXECUTES, program=job_name,
            evidence=f"//{step} EXEC PGM={ctx['monitor']} / "
                     "SYSTSIN RUN PROGRAM(DSNTIAUL)"))

        sysrecs = sorted((d for d in ctx["dds"] if d["name"].startswith("SYSREC")),
                         key=lambda d: d["name"])
        stmts = [s.strip() for s in split_top_level("\n".join(ctx["sysin"]), ";")
                 if s.strip()]
        for i, stmt in enumerate(stmts):
            if not stmt.upper().startswith("SELECT"):
                result.unparsed.append(UnparsedStatement(
                    program=util.name, language=self.language,
                    statement_type="JCL_TSO_SQL",
                    snippet=" ".join(stmt.split())[:200],
                    path=path, line=ctx["line"],
                    reason="DSNTIAUL SYSIN statement is not a SELECT; "
                           "unload semantics unknown"))
                continue
            if i >= len(sysrecs):
                result.unparsed.append(UnparsedStatement(
                    program=util.name, language=self.language,
                    statement_type="JCL_TSO_SQL",
                    snippet=" ".join(stmt.split())[:200],
                    path=path, line=ctx["line"],
                    reason=f"no SYSREC{i:02d} DD to pair with unload "
                           f"statement {i + 1}"))
                continue
            dsn = _substitute(sysrecs[i]["dsn"], symbols)
            if "&" in dsn:
                result.dynamic_constructs.append(DynamicConstruct(
                    program=util.name, language=self.language,
                    construct_type="JCL_SYMBOLIC",
                    snippet=f"//{sysrecs[i]['name']} DD DSN={sysrecs[i]['dsn']}",
                    context="\n".join(ctx["systsin"] + ctx["sysin"]),
                    path=path, line=sysrecs[i]["line"]))
                continue
            self._map_unload(stmt, dsn, util, result, path, ctx["line"])

    def _map_unload(self, stmt: str, dsn: str, util: EntityNode,
                    result: ParseResult, path: str, line: int) -> None:
        sql = " ".join(stmt.split())
        select_list = _RE_SELECT_LIST.match(sql)
        from_clause = RE_FROM_CLAUSE.search(sql)
        if not select_list or not from_clause:
            result.unparsed.append(UnparsedStatement(
                program=util.name, language=self.language,
                statement_type="JCL_TSO_SQL", snippet=sql[:200],
                path=path, line=line,
                reason="DSNTIAUL SELECT could not be parsed"))
            return
        aliases = alias_map(from_clause.group(1))
        tables = sorted(set(aliases.values()))
        for table in tables:
            table_node = EntityNode(kind=NodeKind.TABLE, name=table,
                                    attributes={"dbms": "DB2"})
            result.nodes.append(table_node)
            result.edges.append(LineageEdge(
                source_id=table_node.id, target_id=util.id,
                edge_type=EdgeType.READS_FROM, program=util.name,
                transformation="DSNTIAUL UNLOAD", evidence=sql[:300]))

        file_node = EntityNode(kind=NodeKind.FILE, name=dsn,
                               attributes={"unloaded_by": util.name})
        mappings: list[ColumnMapping] = []
        for expr in split_top_level(select_list.group(1)):
            expr = expr.strip()
            if expr == "*":
                if len(tables) == 1:   # record-level, engine convention
                    mappings.append(ColumnMapping(
                        source_columns=[f"TABLE:{tables[0]}|*".upper()],
                        target_column=f"{file_node.id}|*",
                        transformation=sql[:400]))
                continue
            simple = _RE_SIMPLE_COL.match(expr)
            sources = source_columns(expr, aliases)
            if not simple or not sources:
                result.unparsed.append(UnparsedStatement(
                    program=util.name, language=self.language,
                    statement_type="JCL_TSO_SQL",
                    snippet=expr[:200], path=path, line=line,
                    reason="unload select-list expression is not a plain "
                           "column; output position cannot be named"))
                continue
            col = simple.group(1).upper()
            file_node.columns.append(col)
            mappings.append(ColumnMapping(
                source_columns=sources,
                target_column=f"{file_node.id}|{col}",
                transformation=f"DSNTIAUL UNLOAD: {expr}"))
        result.nodes.append(file_node)
        result.edges.append(LineageEdge(
            source_id=util.id, target_id=file_node.id,
            edge_type=EdgeType.WRITES_TO, program=util.name,
            transformation=sql[:400], column_mappings=mappings,
            evidence=f"SYSREC unload to {dsn}"))

    def _handle_dsntep(self, ctx: dict, run_pgm: str, plan: str,
                       result: ParseResult, job_name: str, path: str) -> None:
        """DSNTEP2/4 execute arbitrary SQL: SELECT output goes to SYSPRINT
        (no dataset lineage); DML is detected-but-unmapped telemetry."""
        step = ctx["step"]
        util = EntityNode(
            kind=NodeKind.PROGRAM, name=f"{run_pgm}.{step}",
            language="JCL-UTILITY", path=path,
            attributes={"job": job_name, "step": step,
                        "utility": ctx["monitor"], "db2_program": run_pgm,
                        "plan": plan})
        result.nodes.append(util)
        result.edges.append(LineageEdge(
            source_id=f"{NodeKind.JOB.value}:{job_name}".upper(),
            target_id=util.id, edge_type=EdgeType.EXECUTES, program=job_name,
            evidence=f"//{step} EXEC PGM={ctx['monitor']} / "
                     f"SYSTSIN RUN PROGRAM({run_pgm})"))
        for stmt in split_top_level("\n".join(ctx["sysin"]), ";"):
            stmt = " ".join(stmt.split())
            if not stmt:
                continue
            verb = stmt.split()[0].upper()
            if verb in ("INSERT", "UPDATE", "DELETE", "MERGE", "TRUNCATE"):
                result.unparsed.append(UnparsedStatement(
                    program=util.name, language=self.language,
                    statement_type="JCL_TSO_SQL", snippet=stmt[:200],
                    path=path, line=ctx["line"],
                    reason=f"DML executed via {run_pgm} is not mapped to "
                           "lineage"))

    # ------------------------------------------------------------------
    def _handle_ftp(self, stmt, ftp_node: EntityNode, symbols: dict,
                    result: ParseResult, job_name: str, step: str) -> None:
        deck = "\n".join(stmt["inline"])
        for m in _RE_FTP_PUT.finditer(deck):
            local = _substitute(m.group(1).upper(), symbols)
            remote = _substitute(m.group(2), symbols)
            local_node = EntityNode(kind=NodeKind.FILE, name=local,
                                    attributes={"job": job_name, "step": step})
            result.nodes.append(local_node)
            result.edges.append(LineageEdge(
                source_id=local_node.id, target_id=ftp_node.id,
                edge_type=EdgeType.READS_FROM, program=ftp_node.name,
                evidence=f"FTP put '{local}'"))
            if "&" in remote:
                # remote name depends on a submission-time symbol
                result.dynamic_constructs.append(DynamicConstruct(
                    program=ftp_node.name, language=self.language,
                    construct_type="JCL_SYMBOLIC",
                    snippet=f"put '{local}' {remote}",
                    context=deck, path=result.path, line=stmt["line"]))
            else:
                remote_node = EntityNode(kind=NodeKind.FILE, name=remote.upper(),
                                         attributes={"transport": "FTP"})
                result.nodes.append(remote_node)
                result.edges.append(LineageEdge(
                    source_id=ftp_node.id, target_id=remote_node.id,
                    edge_type=EdgeType.WRITES_TO, program=ftp_node.name,
                    transformation="FTP transfer (ascii)",
                    evidence=f"put '{local}' {remote}"))
