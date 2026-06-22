"""Read-side repository: lineage traversals shaped for the React Flow UI."""

from __future__ import annotations

import json

from neo4j import GraphDatabase

from config import neo4j_settings


def _attrs(raw: str | None) -> dict:
    """Node attributes are stored as a JSON string (Neo4j has no map props)."""
    try:
        return json.loads(raw) if raw else {}
    except (TypeError, ValueError):
        return {}


def _steps(raw: str | None, fallback: str | None = None) -> list[str]:
    """Ordered transformation steps (source->target), stored as a JSON list.
    Falls back to splitting the joined transformation string."""
    try:
        val = json.loads(raw) if raw else None
        if isinstance(val, list) and val:
            return val
    except (TypeError, ValueError):
        pass
    if fallback and fallback != "direct":
        return [s.strip() for s in fallback.split("; ") if s.strip()]
    return []

# TRANSFORMS_TO at entity level = view definitions (table -> view);
# column-level TRANSFORMS_TO lives on Column nodes, unreachable from here.
_ENTITY_RELS = "READS_FROM|WRITES_TO|EXECUTES|TRANSFORMS_TO"


class LineageRepository:
    def __init__(self):
        s = neo4j_settings()
        self._driver = GraphDatabase.driver(s["uri"], auth=(s["user"], s["password"]))
        self._database = s["database"]

    def close(self) -> None:
        self._driver.close()

    # ------------------------------------------------------------------
    def list_entities(self) -> list[dict]:
        query = (
            "MATCH (n) WHERE n:Table OR n:File OR n:Program OR n:Job "
            "OPTIONAL MATCH (n)-[:HAS_COLUMN]->(c:Column) "
            "RETURN n.id AS id, n.name AS name, labels(n)[0] AS kind, "
            "       n.language AS language, n.attributes AS attributes, "
            "       count(c) AS column_count "
            "ORDER BY kind, name")
        with self._driver.session(database=self._database) as session:
            return [dict(r) | {"attributes": _attrs(r["attributes"])}
                    for r in session.run(query)]

    # ------------------------------------------------------------------
    def lineage(self, entity_id: str, depth: int = 3, level: str = "table") -> dict:
        depth = max(1, min(int(depth), 8))
        with self._driver.session(database=self._database) as session:
            nodes, edges = self._entity_neighbourhood(session, entity_id, depth)
            if level == "column":
                edges = [e for e in edges if e["data"]["edge_type"] == "EXECUTES"]
                edges += self._column_edges(session, [n["id"] for n in nodes])
            return {"nodes": nodes, "edges": edges, "level": level,
                    "root": entity_id.upper()}

    def _entity_neighbourhood(self, session, entity_id: str, depth: int):
        query = (
            f"MATCH (start {{id: $id}}) "
            f"OPTIONAL MATCH p = (start)-[:{_ENTITY_RELS}*1..{depth}]-(m) "
            "WITH start, collect(p) AS paths "
            "WITH start, paths, "
            "  reduce(ns = [start], p IN paths | ns + nodes(p)) AS all_nodes, "
            "  reduce(rs = [], p IN paths | rs + relationships(p)) AS all_rels "
            "UNWIND all_nodes AS n "
            "WITH collect(DISTINCT n) AS ns, all_rels "
            "UNWIND (CASE WHEN size(all_rels) = 0 THEN [null] ELSE all_rels END) AS r "
            "WITH ns, collect(DISTINCT r) AS rs "
            "RETURN ns, rs")
        record = session.run(query, id=entity_id.upper()).single()
        if record is None:
            return [], []

        nodes = []
        for n in record["ns"]:
            label = list(n.labels)[0]
            cols = session.run(
                "MATCH ({id: $id})-[:HAS_COLUMN]->(c:Column) "
                "RETURN c.name AS name ORDER BY name", id=n["id"])
            nodes.append({
                "id": n["id"], "name": n["name"], "kind": label,
                "language": n.get("language"), "path": n.get("path"),
                "attributes": _attrs(n.get("attributes")),
                "columns": [c["name"] for c in cols],
            })
        edges = []
        for r in record["rs"]:
            if r is None:
                continue
            edges.append({
                "id": r.get("edge_id") or f"{r.start_node['id']}>{r.end_node['id']}",
                "source": r.start_node["id"], "target": r.end_node["id"],
                "data": {
                    "edge_type": r.type,
                    "program": r.get("program"),
                    "transformation": r.get("transformation"),
                    "provenance": r.get("provenance", "DETERMINISTIC"),
                    "status": r.get("status", "CONFIRMED"),
                    "confidence": r.get("confidence", 1.0),
                    "evidence": r.get("evidence"),
                    "reasoning": r.get("reasoning"),
                    "ai_metadata": _attrs(r.get("ai_metadata")),
                },
            })
        return nodes, edges

    def _column_edges(self, session, entity_ids: list[str]) -> list[dict]:
        query = (
            "MATCH (s:Column)-[r:TRANSFORMS_TO]->(t:Column) "
            "WHERE s.owner_id IN $ids AND t.owner_id IN $ids "
            "RETURN s, t, r")
        edges = []
        for rec in session.run(query, ids=entity_ids):
            s, t, r = rec["s"], rec["t"], rec["r"]
            edges.append({
                "id": r.get("edge_id") or f"{s['id']}>{t['id']}",
                "source": s["owner_id"], "target": t["owner_id"],
                "sourceHandle": s["id"], "targetHandle": t["id"],
                "data": {
                    "edge_type": "TRANSFORMS_TO",
                    "source_column": s["name"], "target_column": t["name"],
                    "program": r.get("program"),
                    "transformation": r.get("transformation"),
                    "transform_steps": _steps(r.get("transform_steps"),
                                              r.get("transformation")),
                    "provenance": r.get("provenance", "DETERMINISTIC"),
                    "status": r.get("status", "CONFIRMED"),
                    "confidence": r.get("confidence", 1.0),
                    "reasoning": r.get("reasoning"),
                    "evidence": r.get("evidence"),
                    "ai_metadata": _attrs(r.get("ai_metadata")),
                },
            })
        return edges

    # ------------------------------------------------------------------
    def provisional_edges(self) -> list[dict]:
        query = (
            "MATCH (a)-[r]->(b) WHERE r.status = 'PROVISIONAL' "
            "RETURN r.edge_id AS edge_id, type(r) AS edge_type, "
            "       a.id AS source, b.id AS target, r.confidence AS confidence, "
            "       r.transformation AS transformation, r.evidence AS evidence, "
            "       r.reasoning AS reasoning, r.ai_metadata AS ai_metadata")
        with self._driver.session(database=self._database) as session:
            return [dict(rec) | {"ai_metadata": _attrs(rec["ai_metadata"])}
                    for rec in session.run(query)]

    def review_edge(self, edge_id: str, approve: bool) -> int:
        status = "CONFIRMED" if approve else "REJECTED"
        query = (
            "MATCH ()-[r]->() WHERE r.edge_id = $edge_id "
            "SET r.status = $status RETURN count(r) AS n")
        with self._driver.session(database=self._database) as session:
            return session.run(query, edge_id=edge_id, status=status).single()["n"]
