"""Provider factory: ``config.yaml -> ai.provider`` selects the strategy."""

from __future__ import annotations

from config import load_config

from .base import AIProvider


def get_provider() -> AIProvider:
    cfg = load_config()["ai"]
    provider = cfg.get("provider", "bedrock").lower()
    if provider == "nvidia":
        from .nvidia_provider import NvidiaProvider
        return NvidiaProvider(cfg.get("nvidia", {}))
    if provider == "bedrock":
        from .bedrock_provider import BedrockProvider
        return BedrockProvider(cfg.get("bedrock", {}))
    raise ValueError(f"Unknown ai.provider '{provider}' (expected nvidia|bedrock)")


def ai_enabled() -> bool:
    return bool(load_config()["ai"].get("enabled", True))


def confidence_threshold() -> float:
    return float(load_config()["ai"].get("confidence_threshold", 0.6))
