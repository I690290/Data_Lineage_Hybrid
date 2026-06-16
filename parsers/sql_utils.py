"""Shared deterministic SQL helpers used by both the PL/SQL parser and the
COBOL parser (embedded EXEC SQL cursors)."""

from __future__ import annotations

import re

from .base import NodeKind

RE_QUALIFIED_COL = re.compile(r"\b([A-Z0-9_]+)\.([A-Z0-9_]+)\b", re.I)
RE_BARE_COL = re.compile(r"\b([A-Z][A-Z0-9_]*)\b", re.I)
RE_FROM_CLAUSE = re.compile(
    r"\bFROM\s+(.*?)(?:\bWHERE\b|\bGROUP\s+BY\b|\bORDER\s+BY\b|$)", re.I | re.S)

SQL_KEYWORDS = {
    "UPPER", "LOWER", "SUM", "MIN", "MAX", "AVG", "COUNT", "CASE", "WHEN",
    "THEN", "ELSE", "END", "AS", "NVL", "COALESCE", "TRIM", "SUBSTR",
    "TO_CHAR", "TO_DATE", "TO_NUMBER", "DECODE", "DISTINCT", "AND", "OR",
    "NOT", "NULL", "IS", "IN", "BETWEEN", "LIKE", "CHAR", "VARCHAR_FORMAT",
    "CURRENT", "DATE", "TIMESTAMP", "SYSDATE", "TRUNC", "REPLACE",
    "ADD_MONTHS", "ABS", "ROUND", "FLOOR", "CEIL", "CAST", "BYTE",
}


def normalize_name(name: str) -> str:
    """Strip Oracle double quotes from (possibly schema-qualified) names."""
    return name.replace('"', "").upper()


def split_top_level(s: str, sep: str = ",") -> list[str]:
    """Split on `sep` ignoring separators nested inside parentheses/quotes."""
    parts, depth, in_str, cur = [], 0, False, []
    for ch in s:
        if ch == "'":
            in_str = not in_str
        elif not in_str:
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
            elif ch == sep and depth == 0:
                parts.append("".join(cur).strip())
                cur = []
                continue
        cur.append(ch)
    if cur:
        parts.append("".join(cur).strip())
    return [p for p in parts if p]


def alias_map(from_clause: str) -> dict[str, str]:
    """``FROM CRISK.CUST_ACCOUNT_MASTER A JOIN X B ON ...`` -> alias->table."""
    aliases: dict[str, str] = {}
    clause = re.split(r"\bON\b", from_clause, flags=re.I)[0]
    for chunk in re.split(
            r"\b(?:INNER\s+|LEFT\s+(?:OUTER\s+)?|RIGHT\s+(?:OUTER\s+)?)?JOIN\b|,",
            clause, flags=re.I):
        toks = chunk.split()
        if not toks:
            continue
        table = normalize_name(toks[0])
        alias = normalize_name(toks[1]) if len(toks) > 1 else table
        aliases[alias] = table
        aliases[table] = table
    for m in re.finditer(r"\bJOIN\s+([A-Z0-9_$#.\"]+)(?:\s+([A-Z0-9_]+))?",
                         from_clause, re.I):
        table = normalize_name(m.group(1))
        alias = normalize_name(m.group(2)) if m.group(2) else table
        if alias != "ON":
            aliases[alias] = table
            aliases[table] = table
    return aliases


def source_columns(expr: str, aliases: dict[str, str]) -> list[str]:
    """Qualified ``Table:NAME|COL`` source refs used by a select expression."""
    cols: list[str] = []
    expr_wo_strings = re.sub(r"'[^']*'", "", expr)
    for alias, col in RE_QUALIFIED_COL.findall(expr_wo_strings):
        table = aliases.get(alias.upper())
        if table:
            cols.append(f"{NodeKind.TABLE.value}:{table}|{col}".upper())
    if not cols:
        tables = set(aliases.values())
        if len(tables) == 1:  # single-table FROM: bare column names
            table = next(iter(tables))
            for tok in RE_BARE_COL.findall(expr_wo_strings):
                if tok.upper() not in SQL_KEYWORDS and tok.upper() not in aliases:
                    cols.append(f"{NodeKind.TABLE.value}:{table}|{tok}".upper())
    return list(dict.fromkeys(cols))
