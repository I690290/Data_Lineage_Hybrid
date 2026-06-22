"""AI edge-resolution: turn flagged dynamic constructs into PROVISIONAL edges.

Pipeline per construct:
  1. ``resolve``  - the LLM proposes lineage edges as structured JSON, given
                    the flagged snippet, its surrounding context and the
                    catalogue of entities the deterministic parser already
                    found (so the model anchors to known names).
  2. ``evaluate`` - a second, independent LLM pass scores each proposed edge
                    (see evaluator.py); edges below the configured confidence
                    threshold are dropped.
  3. For accepted WRITES_TO edges with no column mappings, a third targeted
                    ``column_retry`` pass asks specifically for column-level
                    detail so that Column Lineage view stays populated.
  4. Survivors are emitted with provenance=AI_INFERRED, status=PROVISIONAL -
                    they NEVER enter the graph as confirmed facts.
"""

from __future__ import annotations

import logging

from parsers.base import (
    ColumnMapping,
    DynamicConstruct,
    EdgeStatus,
    EdgeType,
    EntityNode,
    LineageEdge,
    NodeKind,
    Provenance,
)

from .base import AIProvider
from .evaluator import EdgeEvaluator

log = logging.getLogger(__name__)

_SYSTEM = """You are a senior mainframe/database engineer doing data-lineage analysis.
A deterministic parser flagged a construct it could not resolve statically
(dynamic SQL built at run time, or a JCL symbolic only known at submission).
Propose the most likely data-lineage edges. Be conservative: only propose
edges that are strongly implied by the code. Use a name pattern with '*'
(e.g. ACCT_*) when the concrete name is parameterised.

Return JSON: {
"lineage": [{
  "source_entity": "<TABLE or FILE name>",
  "source_kind": "Table|File",
  "target_entity": "<TABLE or FILE name>",
  "target_kind": "Table|File",
  "edge_type": "READS_FROM|WRITES_TO",
  "direction_note": "READS_FROM means the program reads the source; WRITES_TO means the program writes the target",
  "column_mappings": [{"source_column": "...", "target_column": "...", "transformation": "..."}],
  "reasoning": "<one sentence for this edge>"
}],
"confidence_score": <0.0-1.0 your overall confidence in the proposal>,
"reasoning": "<overall explanation of how you resolved the construct>"
}"""

_COLUMN_SYSTEM = """You are a senior mainframe/database engineer specialising in
column-level data lineage. A data-movement edge has already been accepted but
its column-level mappings are missing. Analyse the code snippet carefully and
return every column-to-column transformation you can identify.

Return JSON:
{
  "column_mappings": [
    {
      "source_column": "<source column — real name, not a placeholder>",
      "target_column": "<target column — real name, not a placeholder>",
      "transformation": "<exact COBOL/SQL expression, or DIRECT for a straight copy>"
    }
  ],
  "reasoning": "<one sentence explaining what you found>"
}
If column names cannot be determined from the code, return column_mappings as [].
Never invent column names that are not present in the code."""


# model output that names nothing real - rejected before the judge runs
_PLACEHOLDER_NAMES = {"", "none", "null", "unknown", "n/a", "?", "*"}


def _named(value) -> bool:
    return bool(value) and str(value).strip().lower() not in _PLACEHOLDER_NAMES


_KIND_PREFIXES = tuple(f"{k.value.upper()}:" for k in NodeKind)


def _strip_kind_prefix(name: str) -> str:
    """Drop a leading ``Kind:`` the model may have echoed into an entity name
    (e.g. ``FILE:CR_ACX_VALID_*``); the emit step re-derives it from
    ``EntityNode.id``, so leaving it would double-prefix to ``FILE:FILE:...``
    and split one entity into two nodes."""
    s = str(name).strip()
    up = s.upper()
    for pfx in _KIND_PREFIXES:
        if up.startswith(pfx):
            return s[len(pfx):]
    return s


class EdgeResolver:
    def __init__(self, provider: AIProvider, threshold: float):
        self._provider = provider
        self._evaluator = EdgeEvaluator(provider)
        self._threshold = threshold

    def resolve_all(self, constructs: list[DynamicConstruct],
                    known_entities: list[str]) -> tuple[list[EntityNode], list[LineageEdge]]:
        nodes: list[EntityNode] = []
        edges: list[LineageEdge] = []
        for construct in constructs:
            try:
                n, e = self._resolve_one(construct, known_entities)
                nodes.extend(n)
                edges.extend(e)
            except Exception:
                log.exception("AI resolution failed for %s @ %s:%s",
                              construct.construct_type, construct.path, construct.line)
        return nodes, edges

    # ------------------------------------------------------------------
    def _resolve_one(self, construct: DynamicConstruct,
                     known_entities: list[str]) -> tuple[list[EntityNode], list[LineageEdge]]:
        user = (
            f"Language: {construct.language}\n"
            f"Program: {construct.program}\n"
            f"Construct type: {construct.construct_type}\n"
            f"Flagged snippet:\n{construct.snippet}\n\n"
            f"Surrounding context:\n{construct.context}\n\n"
            f"Entities already known to the lineage graph:\n"
            + "\n".join(sorted(set(known_entities))))
        payload = self._provider.complete_json(_SYSTEM, user)
        if isinstance(payload, dict):
            # structured contract: {"lineage": [...], "confidence_score",
            # "reasoning"}; "edges" accepted for backward compatibility
            proposals = payload.get("lineage", payload.get("edges", []))
            self_confidence = payload.get("confidence_score")
            overall_reasoning = payload.get("reasoning", "")
        else:
            proposals, self_confidence, overall_reasoning = payload, None, ""

        nodes: list[EntityNode] = []
        edges: list[LineageEdge] = []
        program_id = f"{NodeKind.PROGRAM.value}:{construct.program}".upper()

        seen: set[tuple] = set()
        for prop in proposals:
            # malformed / duplicate proposals never reach the judge
            edge_type_raw = prop.get("edge_type", "WRITES_TO")
            for fld in ("source_entity", "target_entity"):
                if _named(prop.get(fld)):
                    prop[fld] = _strip_kind_prefix(prop[fld])
            anchor = (prop.get("target_entity") if edge_type_raw == "WRITES_TO"
                      else prop.get("source_entity"))
            if edge_type_raw not in ("READS_FROM", "WRITES_TO") or not _named(anchor):
                log.info("Dropped malformed AI proposal: %s", prop)
                continue
            key = (str(prop.get("source_entity")).upper(),
                   str(prop.get("target_entity")).upper(), edge_type_raw)
            if key in seen:
                log.info("Dropped duplicate AI proposal: %s", prop)
                continue
            seen.add(key)

            verdict = self._evaluator.evaluate(construct, prop)
            if verdict["confidence"] < self._threshold:
                log.info("Dropped AI edge (confidence %.2f < %.2f): %s",
                         verdict["confidence"], self._threshold, prop)
                continue

            edge_type = EdgeType(edge_type_raw)
            entity_name = str(anchor).upper()
            kind_raw = (prop.get("target_kind") if edge_type == EdgeType.WRITES_TO
                        else prop.get("source_kind")) or "Table"
            kind = NodeKind.FILE if kind_raw.lower() == "file" else NodeKind.TABLE
            entity = EntityNode(kind=kind, name=entity_name,
                                attributes={"provenance": Provenance.AI_INFERRED.value,
                                            "model": self._provider.model_id,
                                            "construct_id": construct.id})
            nodes.append(entity)

            # placeholder column names (e.g. '?' echoed from VALUES markers)
            # carry no lineage - keep only mappings naming both ends
            mappings = [ColumnMapping(
                source_columns=[m["source_column"]],
                target_column=m["target_column"],
                transformation=m.get("transformation", "ai-inferred"))
                for m in prop.get("column_mappings", [])
                if _named(m.get("source_column")) and _named(m.get("target_column"))]

            # WRITES_TO edges with no column mappings from the first pass get a
            # targeted follow-up call so Column Lineage view stays populated.
            if not mappings and edge_type == EdgeType.WRITES_TO:
                log.info(
                    "WRITES_TO %s→%s has no column mappings; requesting column detail",
                    prop.get("source_entity"), prop.get("target_entity"))
                mappings = self._resolve_column_mappings(construct, prop)

            src, tgt = ((program_id, entity.id) if edge_type == EdgeType.WRITES_TO
                        else (entity.id, program_id))
            reasoning = prop.get("reasoning") or overall_reasoning
            edges.append(LineageEdge(
                source_id=src, target_id=tgt, edge_type=edge_type,
                program=construct.program,
                transformation=prop.get("reasoning"),
                column_mappings=mappings,
                provenance=Provenance.AI_INFERRED,
                status=EdgeStatus.PROVISIONAL,
                confidence=round(verdict["confidence"], 2),
                reasoning=reasoning,
                # auditability: which model said what, against which prompt
                ai_metadata={
                    "provider": self._provider.name,
                    "model": self._provider.model_id,
                    "construct_id": construct.id,
                    "construct_type": construct.construct_type,
                    "source": f"{construct.path}:{construct.line}",
                    "prompt_context": user[:1500],
                    "self_confidence": self_confidence,
                    "judge_confidence": round(verdict["confidence"], 2),
                    "judge_rationale": verdict["rationale"],
                },
                evidence=(f"{construct.snippet}\n--- AI rationale: "
                          f"{reasoning} | Judge: {verdict['rationale']}")))
        return nodes, edges

    # ------------------------------------------------------------------
    def _resolve_column_mappings(
        self, construct: DynamicConstruct, proposal: dict,
    ) -> list[ColumnMapping]:
        """Third-pass: targeted call to recover column-level detail for an
        already-accepted WRITES_TO edge that had no column mappings."""
        user = (
            f"Language: {construct.language}\n"
            f"Program: {construct.program}\n"
            f"Identified data movement:\n"
            f"  Source: {proposal.get('source_entity')} "
            f"({proposal.get('source_kind', 'Table')})\n"
            f"  Target: {proposal.get('target_entity')} "
            f"({proposal.get('target_kind', 'Table')})\n"
            f"  Direction: {proposal.get('edge_type')}\n\n"
            f"Code snippet:\n{construct.snippet}\n\n"
            f"Context:\n{construct.context}\n\n"
            "List every column-to-column mapping with its transformation expression."
        )
        try:
            result = self._provider.complete_json(_COLUMN_SYSTEM, user)
            raw = result.get("column_mappings", []) if isinstance(result, dict) else []
            mappings = [
                ColumnMapping(
                    source_columns=[m["source_column"]],
                    target_column=m["target_column"],
                    transformation=m.get("transformation", "ai-inferred"),
                )
                for m in raw
                if _named(m.get("source_column")) and _named(m.get("target_column"))
            ]
            if mappings:
                log.info(
                    "Column retry recovered %d mapping(s) for %s→%s",
                    len(mappings),
                    proposal.get("source_entity"),
                    proposal.get("target_entity"),
                )
            else:
                log.info(
                    "Column retry returned no mappings for %s→%s; "
                    "entity-level edge kept without column detail",
                    proposal.get("source_entity"),
                    proposal.get("target_entity"),
                )
            return mappings
        except Exception:
            log.exception(
                "Column-level retry failed for %s @ %s:%s",
                construct.construct_type, construct.path, construct.line,
            )
            return []
