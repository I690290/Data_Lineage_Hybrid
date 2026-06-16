"""Parser orchestrator: walk the source tree, dispatch by language, then
cross-link JCL DD bindings onto COBOL logical files.

Cross-linking: COBOL only knows ``SELECT CUST-FILE ASSIGN TO CUSTFILE`` (a DD
name).  JCL knows ``//CUSTFILE DD DSN=PROD.CUSTOMER.DAILY.EXTRACT``.  The
orchestrator re-points every COBOL edge/column-mapping that references the
logical ``File:CUSTFILE`` node onto the physical ``File:<DSN>`` node - still a
purely deterministic join, no inference involved.
"""

from __future__ import annotations

from pathlib import Path

from .base import (
    ColumnMapping,
    EdgeType,
    EntityNode,
    LineageEdge,
    NodeKind,
    ParseResult,
    Provenance,
    UnparsedStatement,
)
from .cobol_parser import CobolParser
from .jcl_parser import JclParser
from .plsql_parser import PlsqlParser
from .sort_resolver import resolve_sort_columns

_SKIP_SUFFIXES = {".cpy"}  # copybooks are expanded inline, never parsed alone


class ParserOrchestrator:
    def __init__(self):
        # fresh parser instances per orchestrator: the COBOL parser keeps
        # per-program artefacts for nested-CALL resolution
        cobol, jcl, plsql = CobolParser(), JclParser(), PlsqlParser()
        self._cobol = cobol
        self._parsers = {
            ".cbl": cobol, ".cob": cobol,
            ".jcl": jcl,
            ".sql": plsql, ".pls": plsql, ".prc": plsql,
        }

    def parse_tree(self, source_dir: Path) -> ParseResult:
        combined = ParseResult(path=str(source_dir), language="MIXED")
        for path in sorted(source_dir.rglob("*")):
            if not path.is_file() or path.suffix.lower() in _SKIP_SUFFIXES:
                continue
            parser = self._parsers.get(path.suffix.lower())
            if parser is None:
                continue
            combined.merge(parser.parse(path))

        # nested CALL lineage needs every program parsed, and must run before
        # cross-linking (the re-resolved mappings still use logical file ids)
        self._cobol.resolve_calls(combined)
        self._cross_link_dd_bindings(combined)
        self._dedupe_nodes(combined)
        # DFSORT/SyncSort control cards -> column lineage; needs the record
        # layouts that cross-linking just placed on the physical FILE nodes
        resolve_sort_columns(combined)
        # entity view must never show less than column view
        self._reconcile_entity_edges(combined)
        return combined

    # ------------------------------------------------------------------
    def _cross_link_dd_bindings(self, result: ParseResult) -> None:
        bindings = []
        for node in result.nodes:
            if node.kind == NodeKind.JOB:
                bindings.extend(node.attributes.get("dd_bindings", []))

        for b in bindings:
            logical_id = f"{NodeKind.FILE.value}:{b['dd_name']}".upper()
            physical_id = f"{NodeKind.FILE.value}:{b['dsn']}".upper()
            logical = next((n for n in result.nodes if n.id == logical_id), None)
            if logical is None:
                continue
            physical = next((n for n in result.nodes if n.id == physical_id), None)
            if physical is None:
                physical = EntityNode(kind=NodeKind.FILE, name=b["dsn"])
                result.nodes.append(physical)
            physical.columns = sorted(set(physical.columns) | set(logical.columns))
            if "record_layout" in logical.attributes:
                physical.attributes.setdefault(
                    "record_layout", logical.attributes["record_layout"])
            physical.attributes.setdefault("dd_aliases", []).append(
                {"dd_name": b["dd_name"], "job": b["job"], "step": b["step"]})

            program = b["program"].upper()
            for edge in result.edges:
                if edge.program != program:
                    continue
                if edge.source_id == logical_id:
                    edge.source_id = physical_id
                if edge.target_id == logical_id:
                    edge.target_id = physical_id
                for cm in edge.column_mappings:
                    cm.source_columns = [
                        s.replace(f"{logical_id}|", f"{physical_id}|")
                        for s in cm.source_columns]
                    if cm.target_column.startswith(f"{logical_id}|"):
                        cm.target_column = cm.target_column.replace(
                            f"{logical_id}|", f"{physical_id}|")
            # after re-pointing: connect unload column names to this
            # reader's FD field names (two namespaces, same bytes)
            if "unloaded_by" in physical.attributes:
                self._bridge_unload_fd_alias(result, physical, logical, program)

        # Drop logical file nodes that were fully re-pointed
        referenced = {e.source_id for e in result.edges} | {e.target_id for e in result.edges}
        result.nodes = [
            n for n in result.nodes
            if not (n.kind == NodeKind.FILE and "logical_file" in n.attributes
                    and n.id not in referenced)]

    # ------------------------------------------------------------------
    def _bridge_unload_fd_alias(self, result: ParseResult, physical: EntityNode,
                                logical: EntityNode, program: str) -> None:
        """A DSNTIAUL-unloaded file is written under its SELECT-list column
        names but read through a COBOL FD that names the *same bytes* with
        program-local names.  The file has ONE physical schema, so the FD
        names are canonicalised onto the unload (writer-side) column names:
        every reader column ref is rewritten and the FD names are dropped
        from the node (kept in ``fd_aliases_resolved`` for transparency).

        Ordinal pairing is deterministic for DSNTIAUL output (fields are
        written in SELECT order) *provided* the FD is byte-contiguous from
        position 1 (a leading/mid-record FILLER would shift alignment) and
        the field counts match exactly.  A record-level unload ('|*')
        bridges record-level; anything unverifiable is coverage telemetry.
        """
        unload_edge = next(
            (e for e in result.edges
             if e.target_id == physical.id and e.edge_type == EdgeType.WRITES_TO
             and e.program == physical.attributes["unloaded_by"]), None)
        if unload_edge is None or not logical.columns:
            return
        reads = any(e.source_id == physical.id and e.program == program
                    and e.edge_type == EdgeType.READS_FROM for e in result.edges)
        bridged = physical.attributes.setdefault("fd_alias_bridged", [])
        if not reads or program in bridged:
            return
        bridged.append(program)

        unload_cols = [cm.target_column.rsplit("|", 1)[1]
                       for cm in unload_edge.column_mappings]
        if unload_cols == ["*"]:
            for field in logical.columns:    # record-level, engine convention
                unload_edge.column_mappings.append(ColumnMapping(
                    source_columns=[f"{physical.id}|*"],
                    target_column=f"{physical.id}|{field}",
                    transformation=f"record-level: unload record read via "
                                   f"{program} FD"))
            return

        layout = logical.attributes.get("record_layout", [])
        contiguous = bool(layout) and layout[0]["start"] == 1 and all(
            layout[i]["start"] + layout[i]["length"] == layout[i + 1]["start"]
            for i in range(len(layout) - 1))
        if contiguous and len(unload_cols) == len(logical.columns):
            # one physical schema, two name sets: rewrite the reader's FD
            # refs onto the canonical unload names so the file exposes a
            # single column list instead of duplicate aliases
            alias = dict(zip(logical.columns, unload_cols))
            prefix = f"{physical.id}|"

            def canon(ref: str) -> str:
                if ref.startswith(prefix):
                    field = ref[len(prefix):]
                    return prefix + alias.get(field, field)
                return ref

            for edge in result.edges:
                for cm in edge.column_mappings:
                    cm.source_columns = [canon(s) for s in cm.source_columns]
                    cm.target_column = canon(cm.target_column)
            physical.columns = [c for c in physical.columns if c not in alias]
            for f in physical.attributes.get("record_layout", []):
                f["field"] = alias.get(f["field"], f["field"])
            physical.attributes.setdefault(
                "fd_aliases_resolved", {}).update(alias)
        else:
            result.unparsed.append(UnparsedStatement(
                program=program, language="JCL",
                statement_type="UNLOAD_FD_ALIAS",
                snippet=(f"{physical.name}: unload columns {unload_cols} vs "
                         f"FD fields {logical.columns}")[:200],
                path=result.path, line=0,
                reason="unload SELECT list and reader FD cannot be aligned "
                       "deterministically (count mismatch or non-contiguous "
                       "record layout)"))

    # ------------------------------------------------------------------
    def _reconcile_entity_edges(self, result: ParseResult) -> None:
        """Invariant: the entity view must never show *less* than the column
        view.  A column mapping can pull from an entity that has no
        entity-level READS_FROM edge to the writing program - data crossing
        a CALL boundary is the canonical case (the callee owns the DB2 read,
        the caller owns the write).  Derive the missing READS_FROM edge from
        the column-level evidence; it is deterministic because the mappings
        it is derived from are.
        """
        node_ids = {n.id for n in result.nodes}
        reads = {(e.source_id, e.target_id) for e in result.edges
                 if e.edge_type == EdgeType.READS_FROM}
        derived: list[LineageEdge] = []
        for e in result.edges:
            if (e.edge_type != EdgeType.WRITES_TO
                    or e.provenance != Provenance.DETERMINISTIC):
                continue
            program_id = e.source_id
            for cm in e.column_mappings:
                for ref in cm.source_columns:
                    owner = ref.rsplit("|", 1)[0]
                    if (owner in (program_id, e.target_id)
                            or owner not in node_ids
                            or owner.startswith(("PROGRAM:", "JOB:"))
                            or (owner, program_id) in reads):
                        continue
                    reads.add((owner, program_id))
                    derived.append(LineageEdge(
                        source_id=owner, target_id=program_id,
                        edge_type=EdgeType.READS_FROM, program=e.program,
                        transformation="derived from column-level mappings",
                        evidence=f"{ref} feeds {cm.target_column} "
                                 f"({(cm.transformation or '')[:150]})"))
        result.edges.extend(derived)

    # ------------------------------------------------------------------
    def _dedupe_nodes(self, result: ParseResult) -> None:
        merged: dict[str, EntityNode] = {}
        for node in result.nodes:
            if node.id in merged:
                kept = merged[node.id]
                kept.columns = sorted(set(kept.columns) | set(node.columns))
                kept.language = kept.language or node.language
                kept.path = kept.path or node.path
                for k, v in node.attributes.items():
                    kept.attributes.setdefault(k, v)
            else:
                merged[node.id] = node
        result.nodes = list(merged.values())
