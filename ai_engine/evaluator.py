"""LLM-as-judge evaluation of AI-proposed lineage edges.

A separate inference pass (no shared prompt with the resolver) scores each
proposed edge against the original source evidence.  The score gates whether
the edge enters the graph at all; edges that pass are still PROVISIONAL and
carry the judge's rationale for the human reviewer.
"""

from __future__ import annotations

from parsers.base import DynamicConstruct

from .base import AIProvider

_SYSTEM = """You are auditing a data-lineage edge proposed by another model for a
dynamic code construct. Judge ONLY whether the edge is supported by the code
evidence. Penalise invented table/file names that have no basis in the code.
Return JSON: {"confidence": <0.0-1.0>, "verdict": "ACCEPT|REJECT", "rationale": "<one sentence>"}"""


class EdgeEvaluator:
    def __init__(self, provider: AIProvider):
        self._provider = provider

    def evaluate(self, construct: DynamicConstruct, proposal: dict) -> dict:
        user = (
            f"Code evidence ({construct.language}, program {construct.program}):\n"
            f"{construct.snippet}\n\nContext:\n{construct.context[:3000]}\n\n"
            f"Proposed edge:\n{proposal}")
        try:
            verdict = self._provider.complete_json(_SYSTEM, user, max_tokens=512)
            return {
                "confidence": float(verdict.get("confidence", 0.0)),
                "verdict": verdict.get("verdict", "REJECT"),
                "rationale": verdict.get("rationale", ""),
            }
        except Exception as exc:  # judge failure -> fail closed
            return {"confidence": 0.0, "verdict": "REJECT",
                    "rationale": f"evaluator error: {exc}"}
