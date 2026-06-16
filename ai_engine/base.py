"""Provider abstraction (Strategy pattern).

Every provider implements the same three capabilities used by the lineage
pipeline:

* ``embed(texts)``          - embeddings for code-similarity analysis
* ``complete(system, user)``- free-form inference
* ``complete_json(...)``    - inference constrained to a JSON document

Swapping NVIDIA <-> Bedrock is a one-line change in ``config.yaml``
(``ai.provider: nvidia | bedrock``) - no call-site changes anywhere.
"""

from __future__ import annotations

import json
import re
from abc import ABC, abstractmethod


class AIProvider(ABC):
    name: str = "base"
    model_id: str = "unknown"   # concrete chat model, recorded for audit

    @abstractmethod
    def embed(self, texts: list[str]) -> list[list[float]]:
        """Return one embedding vector per input text."""

    @abstractmethod
    def complete(self, system: str, user: str, max_tokens: int = 1024) -> str:
        """Single-turn chat completion."""

    def complete_json(self, system: str, user: str, max_tokens: int = 2048) -> dict | list:
        """Completion that must yield JSON; extracts the first JSON document."""
        raw = self.complete(
            system + "\nRespond ONLY with valid JSON. No prose, no markdown fences.",
            user, max_tokens=max_tokens)
        return _extract_json(raw)


def _extract_json(raw: str) -> dict | list:
    raw = raw.strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", raw, re.S)
    if fence:
        raw = fence.group(1).strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        start = min((i for i in (raw.find("{"), raw.find("[")) if i >= 0), default=-1)
        if start >= 0:
            for end in range(len(raw), start, -1):
                try:
                    return json.loads(raw[start:end])
                except json.JSONDecodeError:
                    continue
        raise ValueError(f"Provider returned non-JSON output: {raw[:200]}")
