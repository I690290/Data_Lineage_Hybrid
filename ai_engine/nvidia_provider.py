"""NVIDIA provider: NIM endpoints exposed through the OpenAI-compatible API
at https://integrate.api.nvidia.com/v1 (auth via NVIDIA_API_KEY)."""

from __future__ import annotations

import os

from openai import OpenAI

from .base import AIProvider


class NvidiaProvider(AIProvider):
    name = "nvidia"

    def __init__(self, cfg: dict):
        api_key = os.environ.get("NVIDIA_API_KEY")
        if not api_key:
            raise RuntimeError("NVIDIA_API_KEY is not set (see .env.example)")
        self._client = OpenAI(
            base_url=cfg.get("base_url", "https://integrate.api.nvidia.com/v1"),
            api_key=api_key)
        self._chat_model = cfg.get("chat_model", "meta/llama-3.3-70b-instruct")
        self._embed_model = cfg.get("embed_model", "nvidia/nv-embedqa-e5-v5")
        self.model_id = self._chat_model

    def embed(self, texts: list[str]) -> list[list[float]]:
        resp = self._client.embeddings.create(
            model=self._embed_model, input=texts,
            extra_body={"input_type": "passage", "truncate": "END"})
        return [d.embedding for d in resp.data]

    def complete(self, system: str, user: str, max_tokens: int = 1024) -> str:
        resp = self._client.chat.completions.create(
            model=self._chat_model,
            messages=[{"role": "system", "content": system},
                      {"role": "user", "content": user}],
            temperature=0.1, max_tokens=max_tokens)
        return resp.choices[0].message.content or ""
