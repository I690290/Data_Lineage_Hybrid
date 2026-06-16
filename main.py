"""Hybrid Data Lineage Engine - ingestion CLI.

Usage:
    uv run python main.py ingest [--source ./mock-code] [--no-ai] [--wipe]
    uv run python main.py export [--source ./mock-code] [-o lineage.json]

``ingest``: deterministic parse -> AI edge-resolution for flagged constructs
            -> evaluation gate -> Neo4j upsert.
``export``: same pipeline but writes JSON instead of Neo4j (no DB needed).
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import logging
import sys
from pathlib import Path

from config import load_config
from parsers import ParserOrchestrator
from parsers.base import ParseResult

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
log = logging.getLogger("pipeline")


def run_pipeline(source: Path, use_ai: bool) -> ParseResult:
    log.info("Deterministic parse of %s", source)
    result = ParserOrchestrator().parse_tree(source)
    log.info("Deterministic: %d nodes, %d edges, %d flagged dynamic constructs",
             len(result.nodes), len(result.edges), len(result.dynamic_constructs))

    for dc in result.dynamic_constructs:
        log.info("  FLAGGED %-13s %s (%s:%s)", dc.construct_type, dc.program,
                 Path(dc.path).name, dc.line)

    # --- coverage telemetry: detected-but-unmapped data movement ----------
    if result.unparsed:
        log.warning("COVERAGE: %d data-movement statement(s) detected but NOT "
                    "mapped - lineage may be incomplete:", len(result.unparsed))
        for u in result.unparsed:
            log.warning("  UNPARSED %-24s %s (%s:%s)", u.statement_type,
                        u.program, Path(u.path).name, u.line)
            log.warning("           %s | %s", u.snippet[:90], u.reason)
    else:
        log.info("COVERAGE: all detected data-movement statements were mapped")

    if use_ai and result.dynamic_constructs:
        from ai_engine import confidence_threshold, get_provider
        from ai_engine.lineage_graph import LineageGraphRunner
        provider = get_provider()
        threshold = confidence_threshold()
        log.info(
            "AI edge-resolution (React+Reflexion / LangGraph) via provider '%s' "
            "(threshold %.2f)", provider.name, threshold)
        resolver = LineageGraphRunner(provider, threshold)
        known = [n.id for n in result.nodes]
        ai_nodes, ai_edges = resolver.resolve_all(result.dynamic_constructs, known)
        log.info("AI proposed %d nodes, %d PROVISIONAL edges (post-evaluation)",
                 len(ai_nodes), len(ai_edges))
        result.nodes.extend(ai_nodes)
        result.edges.extend(ai_edges)
    elif result.dynamic_constructs:
        log.warning("AI disabled: %d dynamic constructs left unresolved",
                    len(result.dynamic_constructs))
    return result


def cmd_ingest(args: argparse.Namespace) -> None:
    result = run_pipeline(Path(args.source), use_ai=args.ai)
    from graph import Neo4jWriter
    writer = Neo4jWriter()
    try:
        if args.wipe:
            writer.wipe()
        writer.init_schema()
        writer.write(result.nodes, result.edges)
    finally:
        writer.close()
    log.info("Ingestion complete.")


def cmd_export(args: argparse.Namespace) -> None:
    result = run_pipeline(Path(args.source), use_ai=args.ai)
    payload = {
        "nodes": [dataclasses.asdict(n) | {"id": n.id} for n in result.nodes],
        "edges": [dataclasses.asdict(e) | {"id": e.id} for e in result.edges],
        "dynamic_constructs": [dataclasses.asdict(d) | {"id": d.id}
                               for d in result.dynamic_constructs],
        "unparsed": [dataclasses.asdict(u) for u in result.unparsed],
    }
    Path(args.output).write_text(json.dumps(payload, indent=2, default=str))
    log.info("Wrote %s", args.output)


def main() -> None:
    cfg = load_config()
    default_source = cfg.get("ingestion", {}).get("source_dir", "./mock-code")
    ai_default = bool(cfg["ai"].get("enabled", True))

    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    for name, fn in (("ingest", cmd_ingest), ("export", cmd_export)):
        p = sub.add_parser(name)
        p.add_argument("--source", default=default_source)
        p.add_argument("--no-ai", dest="ai", action="store_false", default=ai_default)
        p.set_defaults(func=fn)
    sub.choices["ingest"].add_argument("--wipe", action="store_true",
                                       help="clear the graph before ingesting")
    sub.choices["export"].add_argument("-o", "--output", default="lineage.json")

    args = parser.parse_args()
    try:
        args.func(args)
    except Exception as exc:
        log.error("%s", exc)
        sys.exit(1)


if __name__ == "__main__":
    main()
