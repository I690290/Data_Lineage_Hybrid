"""Central configuration: config.yaml (behaviour) + .env (secrets)."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

import yaml
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent
CONFIG_PATH = Path(os.environ.get("LINEAGE_CONFIG", PROJECT_ROOT / "config.yaml"))

load_dotenv(PROJECT_ROOT / ".env")


@lru_cache(maxsize=1)
def load_config() -> dict:
    with open(CONFIG_PATH) as fh:
        cfg = yaml.safe_load(fh)
    # Environment overrides for the toggles that matter operationally
    if os.environ.get("AI_PROVIDER"):
        cfg["ai"]["provider"] = os.environ["AI_PROVIDER"]
    if os.environ.get("AI_ENABLED"):
        cfg["ai"]["enabled"] = os.environ["AI_ENABLED"].lower() in ("1", "true", "yes")
    return cfg


def neo4j_settings() -> dict:
    cfg = load_config()["neo4j"]
    return {
        "uri": os.environ.get("NEO4J_URI", cfg["uri"]),
        "user": os.environ.get("NEO4J_USER", cfg["user"]),
        "password": os.environ.get("NEO4J_PASSWORD", "neo4j_lineage"),
        "database": os.environ.get("NEO4J_DATABASE", cfg.get("database", "neo4j")),
    }
