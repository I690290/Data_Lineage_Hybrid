"""Amazon Bedrock provider: Converse API for chat, InvokeModel for Titan
embeddings.  Credentials come from the standard AWS chain (.env / profile)."""

from __future__ import annotations

import json
import os

import boto3

from .base import AIProvider


class BedrockProvider(AIProvider):
    name = "bedrock"

    def __init__(self, cfg: dict):
        region = os.environ.get("AWS_REGION", cfg.get("region", "us-east-1"))
        self._client = boto3.client("bedrock-runtime", region_name=region)
        self._chat_model = cfg.get("chat_model", "amazon.nova-pro-v1:0")
        self._embed_model = cfg.get("embed_model", "amazon.titan-embed-text-v2:0")
        self.model_id = self._chat_model

    def embed(self, texts: list[str]) -> list[list[float]]:
        vectors = []
        for text in texts:  # Titan embed is single-input
            resp = self._client.invoke_model(
                modelId=self._embed_model,
                body=json.dumps({"inputText": text[:8000]}))
            vectors.append(json.loads(resp["body"].read())["embedding"])
        return vectors

    def complete(self, system: str, user: str, max_tokens: int = 1024) -> str:
        resp = self._client.converse(
            modelId=self._chat_model,
            system=[{"text": system}],
            messages=[{"role": "user", "content": [{"text": user}]}],
            inferenceConfig={"temperature": 0.1, "maxTokens": max_tokens})
        return resp["output"]["message"]["content"][0]["text"]
