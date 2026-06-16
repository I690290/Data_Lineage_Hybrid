"""Idempotent Neo4j writer: MERGE everything, never duplicate on re-ingest."""

from __future__ import annotations

import json
import logging

from neo4j import GraphDatabase

from config import neo4j_settings
from parsers.base import EntityNode, LineageEdge

from .schema import CONSTRAINTS, ENTITY_LABELS

log = logging.getLogger(__name__)


def _col_ref(ref: str, fallback_owner: str) -> tuple[str, str, str]:
    """'OWNER_ID|COL' -> (column_id, owner_id, column_name)."""
    if "|" in ref:
        owner, col = ref.rsplit("|", 1)
    else:
        owner, col = fallback_owner, ref
    col = col.upper()
    return f"{owner}|{col}", owner, col


class Neo4jWriter:
    def __init__(self):
        s = neo4j_settings()
        self._driver = GraphDatabase.driver(s["uri"], auth=(s["user"], s["password"]))
        self._database = s["database"]

    def close(self) -> None:
        self._driver.close()

    def init_schema(self) -> None:
        with self._driver.session(database=self._database) as session:
            for stmt in CONSTRAINTS:
                session.run(stmt)

    # ------------------------------------------------------------------
    def write(self, nodes: list[EntityNode], edges: list[LineageEdge]) -> None:
        with self._driver.session(database=self._database) as session:
            for node in nodes:
                self._write_node(session, node)
            for edge in edges:
                self._write_edge(session, edge)
        log.info("Wrote %d nodes, %d edges to Neo4j", len(nodes), len(edges))

    def _write_node(self, session, node: EntityNode) -> None:
        label = node.kind.value
        if label not in ENTITY_LABELS:
            return
        session.run(
            f"MERGE (n:{label} {{id: $id}}) "
            "SET n.name = $name, n.language = $language, n.path = $path, "
            "    n.attributes = $attributes",
            id=node.id, name=node.name, language=node.language,
            path=node.path, attributes=json.dumps(node.attributes))
        for col in node.columns:
            session.run(
                f"MATCH (n:{label} {{id: $id}}) "
                "MERGE (c:Column {id: $cid}) "
                "SET c.name = $col, c.owner_id = $id, c.owner_name = $name "
                "MERGE (n)-[:HAS_COLUMN]->(c)",
                id=node.id, cid=f"{node.id}|{col.upper()}",
                col=col.upper(), name=node.name)

    def _write_edge(self, session, edge: LineageEdge) -> None:
        # entity-level edge (TRANSFORMS_TO between entities = view definition)
        rel = edge.edge_type.value
        session.run(
            "MATCH (a {id: $src}), (b {id: $tgt}) "
            f"MERGE (a)-[r:{rel} {{edge_id: $edge_id}}]->(b) "
            "SET r.program = $program, r.transformation = $transformation, "
            "    r.provenance = $provenance, r.status = $status, "
            "    r.confidence = $confidence, r.evidence = $evidence, "
            "    r.reasoning = $reasoning, r.ai_metadata = $ai_metadata",
            src=edge.source_id, tgt=edge.target_id,
            program=edge.program or "", edge_id=edge.id,
            transformation=edge.transformation,
            provenance=edge.provenance.value, status=edge.status.value,
            confidence=edge.confidence, evidence=edge.evidence,
            reasoning=edge.reasoning,
            ai_metadata=json.dumps(edge.ai_metadata) if edge.ai_metadata else None)

        # Column-level TRANSFORMS_TO edges from the mappings
        entity_id = (edge.target_id if edge.edge_type.value == "WRITES_TO"
                     else edge.source_id)
        for cm in edge.column_mappings:
            tgt_id, tgt_owner, tgt_col = _col_ref(cm.target_column, entity_id)
            for src_ref in cm.source_columns:
                if not src_ref:
                    continue
                src_id, src_owner, src_col = _col_ref(src_ref, entity_id)
                session.run(
                    "MERGE (s:Column {id: $sid}) "
                    "  SET s.name = $scol, s.owner_id = $sowner "
                    "MERGE (t:Column {id: $tid}) "
                    "  SET t.name = $tcol, t.owner_id = $towner "
                    "MERGE (s)-[r:TRANSFORMS_TO {program: $program}]->(t) "
                    "SET r.edge_id = $edge_id, r.transformation = $logic, "
                    "    r.provenance = $provenance, r.status = $status, "
                    "    r.confidence = $confidence, r.reasoning = $reasoning, "
                    "    r.evidence = $evidence, "
                    "    r.ai_metadata = $ai_metadata",
                    sid=src_id, scol=src_col, sowner=src_owner,
                    tid=tgt_id, tcol=tgt_col, towner=tgt_owner,
                    program=edge.program or "",
                    edge_id=f"{edge.id}:{src_col}>{tgt_col}",
                    logic=cm.transformation,
                    provenance=edge.provenance.value, status=edge.status.value,
                    confidence=edge.confidence, reasoning=edge.reasoning,
                    evidence=edge.evidence,
                    ai_metadata=(json.dumps(edge.ai_metadata)
                                 if edge.ai_metadata else None))
                # make sure owners are linked to their columns
                for owner_id, col_id in ((src_owner, src_id), (tgt_owner, tgt_id)):
                    session.run(
                        "MATCH (o {id: $oid}), (c:Column {id: $cid}) "
                        "MERGE (o)-[:HAS_COLUMN]->(c)",
                        oid=owner_id, cid=col_id)

    # ------------------------------------------------------------------
    def wipe(self) -> None:
        with self._driver.session(database=self._database) as session:
            session.run("MATCH (n) DETACH DELETE n")
        log.info("Wiped graph")
