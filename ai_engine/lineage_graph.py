"""LangGraph-based React + Reflexion agentic resolver.

Architecture (one graph invocation per flagged construct):

  resolve_node
      │  (fan-out via Send — one branch per proposal)
      ├── evaluate_node ──► DROP ──► END
      ├── evaluate_node ──► EMIT ──► emit_node ──► END
      └── evaluate_node ──► REFLEXION ──► column_retry_node ──► emit_node ──► END

React:     resolve_node calls the LLM once and returns all proposals.
Reflect:   evaluate_node (LLM-as-judge) independently scores each proposal.
Reflexion: column_retry_node observes missing column detail on an accepted
           WRITES_TO edge, reflects, and re-invokes the LLM with a focused
           column-level prompt before emitting.

Results from all branches are merged via operator.add reducers, so the
single graph invocation returns (emitted_nodes, emitted_edges) for the
whole construct.

Provider-agnostic: any AIProvider (NVIDIA NIM or Amazon Bedrock) plugs in
via the factory — no provider-specific logic in this module.

AWS deployment: plain Python, no extra runtime. Deploy as Lambda handler,
ECS task, or Step Functions activity.
"""

from __future__ import annotations

import logging
import operator
from typing import Annotated, Any, TypedDict

from langgraph.graph import END, StateGraph
from langgraph.types import Send

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
from .resolver import _COLUMN_SYSTEM, _SYSTEM, _named, _strip_kind_prefix

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Graph state
#
# Two schemas because LangGraph fan-out (Send) does NOT commit per-branch
# payloads to shared channels: a node reached via Send reads its Send payload
# as input, but the *conditional edge* after it reads the committed channel
# snapshot — where per-branch scalars are still their START value. Routing on
# a shared scalar therefore sees None, and parallel branches writing the same
# non-reducer channel collide ("can receive only one value per step").
#
# So each proposal runs in its own isolated subgraph (ProposalState): the Send
# payload seeds that subgraph's channels, so its internal routing reads the
# correct per-branch values, and concurrent branches never share scalars. Only
# the operator.add reducer channels (ProposalOutput) bubble back to the outer
# graph (ResolverState) and merge across all branches.
# ---------------------------------------------------------------------------
class ResolverState(TypedDict):
    """Outer graph: one LLM resolve call, then fan-out to per-proposal subgraphs."""
    # ── inputs set once at START ──────────────────────────────────────────
    construct: DynamicConstruct
    known_entities: list[str]
    provider: Any          # AIProvider — not serialised (local execution only)
    evaluator: Any         # EdgeEvaluator
    threshold: float

    # ── resolve_node output (handed to each branch via the Send payload) ──
    proposals: list[dict]
    self_confidence: float | None
    overall_reasoning: str
    prompt_context: str    # stored in ai_metadata for audit trail

    # ── accumulated outputs (operator.add merges all branches) ────────────
    emitted_nodes: Annotated[list[EntityNode], operator.add]
    emitted_edges: Annotated[list[LineageEdge], operator.add]


class ProposalState(TypedDict):
    """Inner subgraph: evaluate → route → [column_retry] → emit for ONE proposal.

    Seeded per Send, so its channels carry this branch's proposal in isolation.
    """
    # ── seeded from the Send payload ──────────────────────────────────────
    construct: DynamicConstruct
    provider: Any
    evaluator: Any
    threshold: float
    self_confidence: float | None
    overall_reasoning: str
    prompt_context: str
    current_proposal: dict
    verdict: dict | None

    # ── outputs (reducers) — the only channels exported to the outer graph ─
    emitted_nodes: Annotated[list[EntityNode], operator.add]
    emitted_edges: Annotated[list[LineageEdge], operator.add]


class ProposalOutput(TypedDict):
    """Restricts the subgraph's exported channels to the reducer aggregators.

    Without this the subgraph would also return its scalar inputs (construct,
    provider, …), and every branch writing those non-reducer channels in the
    same super-step would collide on the outer graph.
    """
    emitted_nodes: Annotated[list[EntityNode], operator.add]
    emitted_edges: Annotated[list[LineageEdge], operator.add]


# ---------------------------------------------------------------------------
# Node: one LLM call that produces all proposals for the construct
# ---------------------------------------------------------------------------
def resolve_node(state: ResolverState) -> dict:
    construct      = state["construct"]
    known          = state["known_entities"]
    provider: AIProvider = state["provider"]

    user = (
        f"Language: {construct.language}\n"
        f"Program: {construct.program}\n"
        f"Construct type: {construct.construct_type}\n"
        f"Flagged snippet:\n{construct.snippet}\n\n"
        f"Surrounding context:\n{construct.context}\n\n"
        f"Entities already known to the lineage graph:\n"
        + "\n".join(sorted(set(known)))
    )
    payload = provider.complete_json(_SYSTEM, user)
    if isinstance(payload, dict):
        proposals       = payload.get("lineage", payload.get("edges", []))
        self_confidence = payload.get("confidence_score")
        overall_reason  = payload.get("reasoning", "")
    else:
        proposals, self_confidence, overall_reason = payload, None, ""

    # deduplicate and drop structurally malformed proposals before the judge
    seen: set[tuple] = set()
    clean: list[dict] = []
    for prop in proposals:
        edge_type_raw = prop.get("edge_type", "WRITES_TO")
        # the model sometimes returns an already-prefixed entity (e.g.
        # "FILE:CR_ACX_VALID_*"); strip it so emit_node doesn't double-prefix
        # into "FILE:FILE:..." and so dedup collapses prefixed/bare variants
        for fld in ("source_entity", "target_entity"):
            if _named(prop.get(fld)):
                prop[fld] = _strip_kind_prefix(prop[fld])
        anchor = (prop.get("target_entity") if edge_type_raw == "WRITES_TO"
                  else prop.get("source_entity"))
        if edge_type_raw not in ("READS_FROM", "WRITES_TO") or not _named(anchor):
            log.info("resolve_node: dropped malformed proposal %s", prop)
            continue
        key = (str(prop.get("source_entity")).upper(),
               str(prop.get("target_entity")).upper(), edge_type_raw)
        if key in seen:
            log.info("resolve_node: dropped duplicate proposal %s", prop)
            continue
        seen.add(key)
        clean.append(prop)

    return {
        "proposals":         clean,
        "self_confidence":   self_confidence,
        "overall_reasoning": overall_reason,
        "prompt_context":    user[:1500],
    }


# ---------------------------------------------------------------------------
# Fan-out: after resolve, run one isolated proposal subgraph per proposal
# ---------------------------------------------------------------------------
def fan_out_proposals(state: ResolverState):
    """Return a Send per proposal so each runs in its own isolated subgraph.

    The payload seeds the subgraph's channels, so its internal routing reads
    this branch's proposal (not a shared channel that Send never commits).
    """
    proposals = state.get("proposals", [])
    if not proposals:
        return [END]
    return [
        Send(
            "proposal",
            {
                "construct":         state["construct"],
                "provider":          state["provider"],
                "evaluator":         state["evaluator"],
                "threshold":         state["threshold"],
                "self_confidence":   state["self_confidence"],
                "overall_reasoning": state["overall_reasoning"],
                "prompt_context":    state["prompt_context"],
                "current_proposal":  prop,
                "verdict":           None,
                "emitted_nodes":     [],
                "emitted_edges":     [],
            },
        )
        for prop in proposals
    ]


# ---------------------------------------------------------------------------
# Node: judge evaluates the current proposal
# ---------------------------------------------------------------------------
def evaluate_node(state: ProposalState) -> dict:
    evaluator: EdgeEvaluator = state["evaluator"]
    prop    = state["current_proposal"]
    verdict = evaluator.evaluate(state["construct"], prop)
    log.info(
        "evaluate_node: %s→%s confidence=%.2f",
        prop.get("source_entity"), prop.get("target_entity"),
        verdict["confidence"],
    )
    return {"verdict": verdict}


# ---------------------------------------------------------------------------
# Routing: drop / reflexion-retry / emit
# ---------------------------------------------------------------------------
def route_after_evaluate(state: ProposalState) -> str:
    verdict   = state["verdict"]
    threshold = state["threshold"]
    prop      = state["current_proposal"]

    if verdict["confidence"] < threshold:
        log.info("route: DROP (confidence %.2f < %.2f)",
                 verdict["confidence"], threshold)
        return "drop"

    # Reflexion trigger: WRITES_TO accepted but column_mappings empty/placeholder
    if prop.get("edge_type") == "WRITES_TO" and not any(
        _named(m.get("source_column")) and _named(m.get("target_column"))
        for m in prop.get("column_mappings", [])
    ):
        log.info("route: COLUMN_RETRY (accepted WRITES_TO but no column detail)")
        return "column_retry"

    return "emit"


# ---------------------------------------------------------------------------
# Node: Reflexion — observe missing columns, reflect, re-invoke LLM
# ---------------------------------------------------------------------------
def column_retry_node(state: ProposalState) -> dict:
    provider: AIProvider = state["provider"]
    construct = state["construct"]
    prop      = state["current_proposal"]

    user = (
        f"Language: {construct.language}\n"
        f"Program: {construct.program}\n"
        f"Identified data movement:\n"
        f"  Source: {prop.get('source_entity')} ({prop.get('source_kind', 'Table')})\n"
        f"  Target: {prop.get('target_entity')} ({prop.get('target_kind', 'Table')})\n"
        f"  Direction: {prop.get('edge_type')}\n\n"
        f"Code snippet:\n{construct.snippet}\n\n"
        f"Context:\n{construct.context}\n\n"
        "List every column-to-column mapping with its transformation expression."
    )
    try:
        result   = provider.complete_json(_COLUMN_SYSTEM, user)
        raw_cols = result.get("column_mappings", []) if isinstance(result, dict) else []
        retry    = [m for m in raw_cols
                    if _named(m.get("source_column")) and _named(m.get("target_column"))]
    except Exception:
        log.exception("column_retry_node failed for %s @ %s:%s",
                      construct.construct_type, construct.path, construct.line)
        retry = []

    if retry:
        log.info("column_retry_node recovered %d mapping(s) for %s→%s",
                 len(retry), prop.get("source_entity"), prop.get("target_entity"))
    else:
        log.info("column_retry_node: no columns recovered for %s→%s",
                 prop.get("source_entity"), prop.get("target_entity"))

    return {"current_proposal": {**prop, "column_mappings": retry}}


# ---------------------------------------------------------------------------
# Node: build EntityNode + LineageEdge and accumulate via operator.add
# ---------------------------------------------------------------------------
def emit_node(state: ProposalState) -> dict:
    construct        = state["construct"]
    prop             = state["current_proposal"]
    verdict          = state["verdict"]
    provider: AIProvider = state["provider"]
    program_id = f"{NodeKind.PROGRAM.value}:{construct.program}".upper()

    edge_type_raw = prop.get("edge_type", "WRITES_TO")
    edge_type     = EdgeType(edge_type_raw)
    anchor        = (prop.get("target_entity") if edge_type == EdgeType.WRITES_TO
                     else prop.get("source_entity"))
    entity_name   = str(anchor).upper()
    kind_raw      = (prop.get("target_kind") if edge_type == EdgeType.WRITES_TO
                     else prop.get("source_kind")) or "Table"
    kind          = NodeKind.FILE if kind_raw.lower() == "file" else NodeKind.TABLE

    entity = EntityNode(
        kind=kind, name=entity_name,
        attributes={
            "provenance":   Provenance.AI_INFERRED.value,
            "model":        provider.model_id,
            "construct_id": construct.id,
        },
    )
    mappings = [
        ColumnMapping(
            source_columns=[m["source_column"]],
            target_column=m["target_column"],
            transformation=m.get("transformation", "ai-inferred"),
        )
        for m in prop.get("column_mappings", [])
        if _named(m.get("source_column")) and _named(m.get("target_column"))
    ]
    src, tgt = ((program_id, entity.id) if edge_type == EdgeType.WRITES_TO
                else (entity.id, program_id))
    reasoning = prop.get("reasoning") or state["overall_reasoning"]
    edge = LineageEdge(
        source_id=src, target_id=tgt, edge_type=edge_type,
        program=construct.program,
        transformation=prop.get("reasoning"),
        column_mappings=mappings,
        provenance=Provenance.AI_INFERRED,
        status=EdgeStatus.PROVISIONAL,
        confidence=round(verdict["confidence"], 2),
        reasoning=reasoning,
        ai_metadata={
            "provider":         provider.name,
            "model":            provider.model_id,
            "construct_id":     construct.id,
            "construct_type":   construct.construct_type,
            "source":           f"{construct.path}:{construct.line}",
            "prompt_context":   state["prompt_context"],
            "self_confidence":  state["self_confidence"],
            "judge_confidence": round(verdict["confidence"], 2),
            "judge_rationale":  verdict["rationale"],
        },
        evidence=(f"{construct.snippet}\n--- AI rationale: "
                  f"{reasoning} | Judge: {verdict['rationale']}"),
    )
    return {
        "emitted_nodes": [entity],
        "emitted_edges": [edge],
    }


# ---------------------------------------------------------------------------
# Inner subgraph: evaluate → route → [column_retry] → emit for ONE proposal.
# Each Send invocation runs this with isolated state (see ProposalState).
# ---------------------------------------------------------------------------
def _build_proposal_graph():
    g = StateGraph(ProposalState, output_schema=ProposalOutput)

    g.add_node("evaluate",     evaluate_node)
    g.add_node("column_retry", column_retry_node)
    g.add_node("emit",         emit_node)

    g.set_entry_point("evaluate")
    g.add_conditional_edges(
        "evaluate",
        route_after_evaluate,
        {"drop": END, "column_retry": "column_retry", "emit": "emit"},
    )
    g.add_edge("column_retry", "emit")
    g.add_edge("emit", END)

    return g.compile()


_PROPOSAL_GRAPH = _build_proposal_graph()


# ---------------------------------------------------------------------------
# Outer graph: resolve once, then fan-out one proposal subgraph per proposal.
# Compiled once at module import.
# ---------------------------------------------------------------------------
def _build_graph():
    g = StateGraph(ResolverState)

    g.add_node("resolve",  resolve_node)
    g.add_node("proposal", _PROPOSAL_GRAPH)

    g.set_entry_point("resolve")

    # Fan-out: one Send per proposal → isolated proposal subgraph
    g.add_conditional_edges("resolve", fan_out_proposals, ["proposal", END])
    g.add_edge("proposal", END)

    return g.compile()


_GRAPH = _build_graph()


# ---------------------------------------------------------------------------
# Public entry point — drop-in replacement for EdgeResolver
# ---------------------------------------------------------------------------
class LineageGraphRunner:
    """React + Reflexion agentic resolver backed by a LangGraph state machine.

    Identical interface to EdgeResolver so it can be swapped in main.py
    by changing one import.  Provider-agnostic: works with NVIDIA NIM or
    Amazon Bedrock via the existing AIProvider ABC.
    """

    def __init__(self, provider: AIProvider, threshold: float):
        self._provider  = provider
        self._evaluator = EdgeEvaluator(provider)
        self._threshold = threshold

    def resolve_all(
        self,
        constructs: list[DynamicConstruct],
        known_entities: list[str],
    ) -> tuple[list[EntityNode], list[LineageEdge]]:
        all_nodes: list[EntityNode] = []
        all_edges: list[LineageEdge] = []
        for construct in constructs:
            try:
                n, e = self._run_construct(construct, known_entities)
                all_nodes.extend(n)
                all_edges.extend(e)
            except Exception:
                log.exception(
                    "LineageGraphRunner failed for %s @ %s:%s",
                    construct.construct_type, construct.path, construct.line,
                )
        return all_nodes, all_edges

    def _run_construct(
        self,
        construct: DynamicConstruct,
        known_entities: list[str],
    ) -> tuple[list[EntityNode], list[LineageEdge]]:
        initial: ResolverState = {
            "construct":         construct,
            "known_entities":    known_entities,
            "provider":          self._provider,
            "evaluator":         self._evaluator,
            "threshold":         self._threshold,
            "proposals":         [],
            "self_confidence":   None,
            "overall_reasoning": "",
            "prompt_context":    "",
            "emitted_nodes":     [],
            "emitted_edges":     [],
        }
        final = _GRAPH.invoke(initial)
        return final.get("emitted_nodes", []), final.get("emitted_edges", [])
