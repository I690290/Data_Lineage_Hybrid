"""Deterministic PL/SQL / Oracle DDL parser built on ``sqlparse``.

Handles:

* ``CREATE [OR REPLACE] PROCEDURE``     -> Program node; DML inside the body
  is attributed to it.
* ``INSERT INTO t [alias] (cols) SELECT``-> column-level mappings (positional
  pairing, alias-resolved sources, expression text kept as transformation).
* ``MERGE INTO ... USING (subquery)``    -> column mappings with subquery
  alias resolution.
* ``UPDATE t SET col = expr [WHERE ...]``-> WRITES_TO with SET/WHERE logic.
* ``DELETE FROM t``                      -> WRITES_TO (logic=DELETE).
* ``CREATE TABLE`` (incl. **ORGANIZATION EXTERNAL**): plain tables register
  their column list; external tables produce a pseudo-loader Program node
  reading the LOCATION file with deterministic XML-tag -> column mappings
  parsed from the ``ENCLOSED BY`` access parameters.
* ``CREATE [OR REPLACE] VIEW``           -> view Table node + entity-level
  TRANSFORMS_TO edges from each source table with column lineage.
* ``EXECUTE IMMEDIATE``                  -> flagged DYNAMIC_SQL for the AI
  edge-resolver (whole procedure as context).

Oracle quoted identifiers (``"SCHEMA"."NAME"``) are normalised throughout.
"""

from __future__ import annotations

import re
from pathlib import Path

import sqlparse

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
from .sql_utils import (
    RE_FROM_CLAUSE,
    RE_QUALIFIED_COL,
    alias_map,
    normalize_name,
    source_columns,
    split_top_level,
)

_NAME = r'["A-Z0-9_$#.]+'
_RE_PROC = re.compile(
    rf"CREATE\s+(?:OR\s+REPLACE\s+)?PROCEDURE\s+({_NAME})", re.I)
_RE_INSERT_SELECT = re.compile(
    rf"INSERT\s+(?:/\*.*?\*/\s*)?INTO\s+({_NAME})(?:\s+[A-Z0-9_]+)?\s*\(([^)]+)\)\s*(SELECT\s+.*?)(?=;)",
    re.I | re.S)
_RE_MERGE = re.compile(
    rf"MERGE\s+INTO\s+({_NAME})\s+([A-Z0-9_]+)\s+USING\s*\((.*?)\)\s*([A-Z0-9_]+)\s+ON\s*\((.*?)\)\s*"
    r"WHEN\s+MATCHED\s+THEN\s+UPDATE\s+SET\s+(.*?)(?=;)", re.I | re.S)
_RE_UPDATE = re.compile(
    rf"UPDATE\s+({_NAME})\s+SET\s+(.*?)(?:\bWHERE\b(.*?))?;", re.I | re.S)
_RE_DELETE = re.compile(rf"DELETE\s+FROM\s+({_NAME})", re.I)
_RE_EXEC_IMM = re.compile(r"EXECUTE\s+IMMEDIATE\s+(.*?);", re.I | re.S)
_RE_CREATE_TABLE = re.compile(rf"CREATE\s+TABLE\s+({_NAME})\s*(?=\()", re.I)
_RE_CREATE_VIEW = re.compile(
    rf"CREATE\s+(?:OR\s+REPLACE\s+)?VIEW\s+({_NAME})\s+AS\s+(SELECT\s+.*?)(?=;)",
    re.I | re.S)
_RE_LOCATION = re.compile(r"LOCATION\s*\(\s*'([^']+)'", re.I)
_RE_ENCLOSED = re.compile(
    r"([A-Z0-9_]+)\s+CHAR\s*\(\d+\)\s*ENCLOSED\s+BY\s+'<([^>']+)>'", re.I)
_RE_COL_DEF = re.compile(rf"^\s*({_NAME})\s+", re.I)


def _balanced_paren_block(text: str, start: int) -> tuple[str, int]:
    """Return the contents of the parenthesised block starting at `start`."""
    depth, in_str = 0, False
    for i in range(start, len(text)):
        ch = text[i]
        if ch == "'":
            in_str = not in_str
        elif not in_str:
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
                if depth == 0:
                    return text[start + 1:i], i
    return text[start + 1:], len(text)


class PlsqlParser:
    language = "PLSQL"

    def parse(self, path: Path) -> ParseResult:
        text = sqlparse.format(path.read_text(), strip_comments=True)
        result = ParseResult(path=str(path), language=self.language)

        proc = _RE_PROC.search(text)
        program_node = None
        if proc or re.search(r"\b(INSERT|UPDATE|MERGE|DELETE)\b",
                             re.sub(r"'[^']*'", "", text), re.I):
            program = (normalize_name(proc.group(1)) if proc
                       else path.stem.upper())
            program_node = EntityNode(
                kind=NodeKind.PROGRAM, name=program,
                language=self.language, path=str(path),
                attributes={"object_type": "PROCEDURE" if proc else "SCRIPT"})
            result.nodes.append(program_node)

        self._handle_create_table(text, result, path)
        self._handle_create_view(text, result)
        if program_node is not None:
            self._handle_insert_select(text, program_node, result)
            self._handle_merge(text, program_node, result)
            self._handle_update(text, program_node, result)
            self._handle_delete(text, program_node, result)
            self._handle_execute_immediate(text, program_node.name, result)
        self._detect_unparsed(
            text, program_node.name if program_node else path.stem.upper(),
            result)
        return result

    # ------------------------------------------------------------------
    def _detect_unparsed(self, text: str, program: str,
                         result: ParseResult) -> None:
        """Flag DML detected outside the spans the handlers actually mapped.

        Catches CTE inserts (WITH ... breaks the INSERT regex), INSERT
        without a column list, MERGE variants beyond WHEN MATCHED UPDATE,
        materialized views, etc. - anything DML-shaped that produced no edge.
        """
        # blank string literal contents, preserving offsets, so DML keywords
        # inside dynamic-SQL strings are not double counted
        blanked = re.sub(r"'[^']*'",
                         lambda m: "'" + " " * (len(m.group(0)) - 2) + "'",
                         text)
        spans: list[tuple[int, int]] = []
        for pattern in (_RE_INSERT_SELECT, _RE_MERGE, _RE_UPDATE,
                        _RE_DELETE, _RE_EXEC_IMM):
            spans.extend(m.span() for m in pattern.finditer(text))

        detector = re.compile(
            r"INSERT\s+(?:/\*.*?\*/\s*)?INTO|MERGE\s+INTO|DELETE\s+FROM"
            r"|\bUPDATE\s+[\"A-Z]|CREATE\s+MATERIALIZED\s+VIEW", re.I)
        for m in detector.finditer(blanked):
            if any(s <= m.start() < e for s, e in spans):
                continue
            stmt_end = blanked.find(";", m.start())
            snippet = text[m.start():stmt_end if stmt_end > 0 else m.start() + 200]
            result.unparsed.append(UnparsedStatement(
                program=program, language=self.language,
                statement_type="SQL_DML_UNMAPPED",
                snippet=" ".join(snippet.split())[:300],
                path=result.path,
                line=text[:m.start()].count("\n") + 1,
                reason="DML statement detected but produced no lineage edge "
                       "(unsupported syntax variant)"))

    # ------------------------------------------------------------------
    def _read_edge(self, program_node, table: str, result, evidence: str) -> None:
        node = EntityNode(kind=NodeKind.TABLE, name=table)
        result.nodes.append(node)
        result.edges.append(LineageEdge(
            source_id=node.id, target_id=program_node.id,
            edge_type=EdgeType.READS_FROM, program=program_node.name,
            evidence=evidence))

    # ------------------------------------------------------------------
    def _handle_create_table(self, text, result, path: Path) -> None:
        for m in _RE_CREATE_TABLE.finditer(text):
            table = normalize_name(m.group(1))
            col_block, block_end = _balanced_paren_block(text, text.index("(", m.end() - 1))
            cols = []
            for chunk in split_top_level(col_block):
                first = chunk.split()[0].upper() if chunk.split() else ""
                if first in ("CONSTRAINT", "PRIMARY", "FOREIGN", "UNIQUE", "CHECK"):
                    continue
                cm = _RE_COL_DEF.match(chunk)
                if cm:
                    cols.append(normalize_name(cm.group(1)).split(".")[-1])
            is_external = bool(re.match(r"\s*ORGANIZATION\s+EXTERNAL",
                                        text[block_end + 1:], re.I))
            table_node = EntityNode(
                kind=NodeKind.TABLE, name=table, columns=cols, path=str(path),
                attributes={"object_type": "EXTERNAL_TABLE" if is_external else "TABLE"})
            result.nodes.append(table_node)

            if is_external:
                self._handle_external_table(text, block_end, table_node, result, path)

    def _handle_external_table(self, text, org_pos, table_node, result, path) -> None:
        """ORACLE_LOADER external table: file -> loader -> table mappings."""
        tail = text[org_pos:]
        loc = _RE_LOCATION.search(tail)
        if not loc:
            return
        xml_file = loc.group(1).upper()
        file_node = EntityNode(
            kind=NodeKind.FILE, name=xml_file,
            attributes={"format": "XML", "directory": "NEPTUNE_FILES_LOAD"})
        result.nodes.append(file_node)

        loader = EntityNode(
            kind=NodeKind.PROGRAM,
            name=f"ORACLE_LOADER.{table_node.name.split('.')[-1]}",
            language="ORACLE-EXT", path=str(path),
            attributes={"object_type": "EXTERNAL_TABLE_LOADER"})
        result.nodes.append(loader)

        mappings = []
        for col, tag in _RE_ENCLOSED.findall(tail):
            col = col.upper()
            if col.lower() == "delim":
                continue
            file_node.columns.append(tag)
            mappings.append(ColumnMapping(
                source_columns=[f"{file_node.id}|{tag.upper()}"],
                target_column=f"{table_node.id}|{col}",
                transformation=f"XML tag <{tag}> ENCLOSED BY"))
        result.edges.append(LineageEdge(
            source_id=file_node.id, target_id=loader.id,
            edge_type=EdgeType.READS_FROM, program=loader.name,
            evidence=f"DEFAULT DIRECTORY NEPTUNE_FILES_LOAD LOCATION ('{xml_file}')"))
        result.edges.append(LineageEdge(
            source_id=loader.id, target_id=table_node.id,
            edge_type=EdgeType.WRITES_TO, program=loader.name,
            transformation="ORACLE_LOADER: RECORDS DELIMITED BY '</Item>'",
            column_mappings=mappings,
            evidence=f"CREATE TABLE {table_node.name} ORGANIZATION EXTERNAL"))

    # ------------------------------------------------------------------
    def _select_mappings(self, select_stmt: str, target_node: EntityNode,
                         target_cols: list[str] | None) -> tuple[list[ColumnMapping], dict]:
        fm = RE_FROM_CLAUSE.search(select_stmt)
        aliases = alias_map(fm.group(1)) if fm else {}
        select_list = re.split(r"\bFROM\b", select_stmt, flags=re.I)[0]
        select_list = re.sub(r"^\s*SELECT\s+", "", select_list, flags=re.I)
        exprs = split_top_level(select_list)

        mappings = []
        for i, expr in enumerate(exprs):
            am = re.search(r"\bAS\s+([A-Z0-9_]+)\s*$", expr, re.I)
            if target_cols is not None:
                if i >= len(target_cols):
                    break
                tgt_col = target_cols[i]
            else:
                tgt_col = (am.group(1) if am
                           else normalize_name(expr.split(".")[-1])).upper()
            expr_body = re.sub(r"\bAS\s+[A-Z0-9_]+\s*$", "", expr, flags=re.I).strip()
            expr_clean = " ".join(expr_body.split())
            srcs = source_columns(expr_body, aliases)
            if not srcs:
                continue
            is_direct = bool(re.fullmatch(r"[A-Z0-9_]+(\.[A-Z0-9_]+)?", expr_clean, re.I))
            mappings.append(ColumnMapping(
                source_columns=srcs,
                target_column=f"{target_node.id}|{tgt_col}",
                transformation="direct" if is_direct else expr_clean[:400]))
        return mappings, aliases

    def _handle_insert_select(self, text, program_node, result) -> None:
        for m in _RE_INSERT_SELECT.finditer(text):
            target = normalize_name(m.group(1))
            target_cols = [normalize_name(c).split(".")[-1]
                           for c in split_top_level(m.group(2))]
            target_node = EntityNode(kind=NodeKind.TABLE, name=target,
                                     columns=target_cols)
            result.nodes.append(target_node)
            mappings, aliases = self._select_mappings(m.group(3), target_node,
                                                      target_cols)
            for table in sorted(set(aliases.values())):
                self._read_edge(program_node, table, result,
                                f"SELECT ... FROM {table}")
            result.edges.append(LineageEdge(
                source_id=program_node.id, target_id=target_node.id,
                edge_type=EdgeType.WRITES_TO, program=program_node.name,
                transformation=f"INSERT INTO {target} SELECT ...",
                column_mappings=mappings,
                evidence=" ".join(m.group(0).split())[:500]))

    def _handle_merge(self, text, program_node, result) -> None:
        for m in _RE_MERGE.finditer(text):
            target = normalize_name(m.group(1))
            target_alias, subquery, sub_alias = m.group(2).upper(), m.group(3), m.group(4).upper()
            set_clause = m.group(6)

            sub_from = RE_FROM_CLAUSE.search(subquery)
            sub_aliases = alias_map(sub_from.group(1)) if sub_from else {}
            sub_select = re.split(r"\bFROM\b", subquery, flags=re.I)[0]
            sub_select = re.sub(r"^\s*SELECT\s+", "", sub_select, flags=re.I)
            sub_exprs: dict[str, str] = {}
            for expr in split_top_level(sub_select):
                am = re.search(r"\bAS\s+([A-Z0-9_]+)\s*$", expr, re.I)
                alias = am.group(1).upper() if am else expr.split(".")[-1].upper()
                sub_exprs[alias] = re.sub(r"\bAS\s+[A-Z0-9_]+\s*$", "", expr,
                                          flags=re.I).strip()

            target_node = EntityNode(kind=NodeKind.TABLE, name=target)
            result.nodes.append(target_node)
            for table in sorted(set(sub_aliases.values())):
                self._read_edge(program_node, table, result,
                                f"MERGE USING (SELECT ... FROM {table})")

            mappings = []
            for assign in split_top_level(set_clause):
                if "=" not in assign:
                    continue
                lhs, rhs = assign.split("=", 1)
                tgt_col = lhs.strip().split(".")[-1].upper()
                srcs: list[str] = []
                rhs_resolved = rhs.strip()
                for alias, col in RE_QUALIFIED_COL.findall(rhs):
                    alias, col = alias.upper(), col.upper()
                    if alias == sub_alias and col in sub_exprs:
                        srcs.extend(source_columns(sub_exprs[col], sub_aliases))
                        rhs_resolved = rhs_resolved.replace(
                            f"{alias}.{col}", f"({' '.join(sub_exprs[col].split())})")
                    elif alias == target_alias:
                        srcs.append(f"{target_node.id}|{col}")
                mappings.append(ColumnMapping(
                    source_columns=list(dict.fromkeys(srcs)),
                    target_column=f"{target_node.id}|{tgt_col}",
                    transformation=" ".join(rhs_resolved.split())[:400]))
            result.edges.append(LineageEdge(
                source_id=program_node.id, target_id=target_node.id,
                edge_type=EdgeType.WRITES_TO, program=program_node.name,
                transformation=f"MERGE INTO {target} WHEN MATCHED UPDATE",
                column_mappings=mappings,
                evidence=" ".join(m.group(0).split())[:500]))

    def _handle_update(self, text, program_node, result) -> None:
        for m in _RE_UPDATE.finditer(text):
            table = normalize_name(m.group(1))
            set_clause = " ".join(m.group(2).split())
            where = " ".join((m.group(3) or "").split())
            node = EntityNode(kind=NodeKind.TABLE, name=table)
            result.nodes.append(node)
            mappings = []
            for assign in split_top_level(m.group(2)):
                if "=" not in assign:
                    continue
                lhs, rhs = assign.split("=", 1)
                mappings.append(ColumnMapping(
                    source_columns=[],
                    target_column=f"{node.id}|{lhs.strip().split('.')[-1].upper()}",
                    transformation=" ".join(rhs.split())[:200]))
            result.edges.append(LineageEdge(
                source_id=program_node.id, target_id=node.id,
                edge_type=EdgeType.WRITES_TO, program=program_node.name,
                transformation=(f"UPDATE SET {set_clause}"
                                + (f" WHERE {where}" if where else ""))[:400],
                column_mappings=mappings,
                evidence=" ".join(m.group(0).split())[:500]))

    def _handle_delete(self, text, program_node, result) -> None:
        clean = re.sub(r"'[^']*'", "''", text)
        for m in _RE_DELETE.finditer(clean):
            table = normalize_name(m.group(1))
            node = EntityNode(kind=NodeKind.TABLE, name=table)
            result.nodes.append(node)
            result.edges.append(LineageEdge(
                source_id=program_node.id, target_id=node.id,
                edge_type=EdgeType.WRITES_TO, program=program_node.name,
                transformation="DELETE", evidence=" ".join(m.group(0).split())))

    # ------------------------------------------------------------------
    def _handle_create_view(self, text, result) -> None:
        for m in _RE_CREATE_VIEW.finditer(text):
            view = normalize_name(m.group(1))
            select_stmt = m.group(2)
            view_node = EntityNode(kind=NodeKind.TABLE, name=view,
                                   attributes={"object_type": "VIEW"})
            result.nodes.append(view_node)
            mappings, aliases = self._select_mappings(select_stmt, view_node, None)
            view_node.columns = [cm.target_column.rsplit("|", 1)[1]
                                 for cm in mappings]
            where = re.search(r"\bWHERE\b(.*?)(?:\bGROUP\s+BY\b|$)",
                              select_stmt, re.I | re.S)
            filter_logic = (" ".join(where.group(1).split())[:300]
                            if where else None)
            for table in sorted(set(aliases.values())):
                table_node = EntityNode(kind=NodeKind.TABLE, name=table)
                result.nodes.append(table_node)
                result.edges.append(LineageEdge(
                    source_id=table_node.id, target_id=view_node.id,
                    edge_type=EdgeType.TRANSFORMS_TO, program=view,
                    transformation=(f"VIEW over {table}"
                                    + (f" WHERE {filter_logic}" if filter_logic else "")),
                    column_mappings=[cm for cm in mappings
                                     if any(s.startswith(table_node.id)
                                            for s in cm.source_columns)],
                    evidence=f"CREATE OR REPLACE VIEW {view} AS SELECT ..."))

    def _handle_execute_immediate(self, text, program, result) -> None:
        for m in _RE_EXEC_IMM.finditer(text):
            result.dynamic_constructs.append(DynamicConstruct(
                program=program, language=self.language,
                construct_type="DYNAMIC_SQL",
                snippet=" ".join(m.group(0).split()),
                context=text,
                path=result.path,
                line=text[:m.start()].count("\n") + 1))
