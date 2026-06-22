"""Parser orchestrator: walk the source tree, dispatch by language, then
cross-link JCL DD bindings onto COBOL logical files.

Cross-linking: COBOL only knows ``SELECT CUST-FILE ASSIGN TO CUSTFILE`` (a DD
name).  JCL knows ``//CUSTFILE DD DSN=PROD.CUSTOMER.DAILY.EXTRACT``.  The
orchestrator re-points every COBOL edge/column-mapping that references the
logical ``File:CUSTFILE`` node onto the physical ``File:<DSN>`` node - still a
purely deterministic join, no inference involved.
"""

from __future__ import annotations

import re
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
        # FTP `put <dsn> <remote-with-&symbol>`: reconcile the symbolic remote
        # name against the concrete downstream filename (Oracle external-table
        # LOCATION) so the mainframe->Oracle copy is one connected chain
        self._bridge_ftp_remote_alias(combined)
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
    def _bridge_ftp_remote_alias(self, result: ParseResult) -> None:
        """An FTP ``put <dsn> <remote>`` whose remote name carries a
        submission-time symbolic (``CR_ACX_VALID_&DATE..dat``) is a
        deterministic record copy with one unknown - the symbol.  The JCL
        parser emitted the transfer to a *template* node (``CR_ACX_VALID_*.DAT``)
        and flagged it.  A downstream consumer already names the concrete file
        - an Oracle external-table ``LOCATION ('CR_ACX_VALID_20260622.dat')``.
        A unique match resolves the symbol, unifies the two file identities
        into the concrete node, carries the source dataset's record schema
        across the (byte-identity) copy, and retires the flag.  No / ambiguous
        match -> the template stays flagged for the AI layer.
        """
        templates = [n for n in result.nodes if n.kind == NodeKind.FILE
                     and n.attributes.get("ftp_unresolved")]
        if not templates:
            return
        concrete = [n for n in result.nodes if n.kind == NodeKind.FILE
                    and "*" not in n.id and not n.attributes.get("ftp_unresolved")]
        for tmpl in templates:
            rx = re.compile("^" + re.escape(tmpl.name).replace(r"\*", "(.+)") + "$")
            matches = [(n, m) for n in concrete if (m := rx.match(n.name))]
            if len(matches) != 1:
                continue                  # absent / ambiguous -> stays flagged
            target, m = matches[0]
            resolved = dict(zip(tmpl.attributes.get("ftp_symbols") or [], m.groups()))
            self._absorb_file_node(result, tmpl, target)
            self._carry_ftp_record_copy(
                result, tmpl.attributes.get("ftp_source"), target, resolved)
            snippet = (f"put '{tmpl.attributes.get('ftp_source')}' "
                       f"{tmpl.attributes.get('ftp_template')}")
            result.dynamic_constructs = [
                d for d in result.dynamic_constructs if d.snippet != snippet]

    @staticmethod
    def _absorb_file_node(result: ParseResult, src: EntityNode,
                          dst: EntityNode) -> None:
        """Merge file node ``src`` into ``dst``: re-point every edge and column
        ref, fold in attributes, and drop ``src``."""
        old, new = src.id, dst.id
        for e in result.edges:
            if e.source_id == old:
                e.source_id = new
            if e.target_id == old:
                e.target_id = new
            for cm in e.column_mappings:
                cm.source_columns = [c.replace(f"{old}|", f"{new}|")
                                     for c in cm.source_columns]
                if cm.target_column.startswith(f"{old}|"):
                    cm.target_column = f"{new}|{cm.target_column.split('|', 1)[1]}"
        for k, v in src.attributes.items():
            dst.attributes.setdefault(k, v)
        dst.attributes.pop("ftp_unresolved", None)
        result.nodes = [n for n in result.nodes if n.id != old]

    @staticmethod
    def _carry_ftp_record_copy(result: ParseResult, source_name: str | None,
                               target: EntityNode, resolved: dict) -> None:
        """FTP is a byte-identity copy: give the remote file the source
        dataset's record schema and emit field-by-field identity column
        lineage on the transfer edge, recording the resolved symbol."""
        # the JCL parser clobbers the per-put transformation with the whole
        # INPUT deck (flush_sysin), so match the transfer edge by endpoint
        edge = next((e for e in result.edges
                     if e.target_id == target.id
                     and e.edge_type == EdgeType.WRITES_TO), None)
        if edge is not None:
            note = (" " + ", ".join(f"&{k}={v}" for k, v in resolved.items())
                    if resolved else "")
            edge.transformation = ("FTP transfer (ascii, byte-identity record "
                                   f"copy); remote name resolved from downstream "
                                   f"consumer{note}")
        if not source_name:
            return
        src_id = f"{NodeKind.FILE.value}:{source_name}".upper()
        src = next((n for n in result.nodes if n.id == src_id), None)
        if src is None or not src.columns or edge is None or edge.column_mappings:
            return
        if not target.columns:
            # remote has no schema of its own: it IS the source record, so give
            # it the source field names and field-by-field identity lineage
            target.columns = list(src.columns)
            if "record_layout" in src.attributes:
                target.attributes.setdefault(
                    "record_layout", src.attributes["record_layout"])
            edge.column_mappings = [
                ColumnMapping(source_columns=[f"{src.id}|{f}"],
                              target_column=f"{target.id}|{f}",
                              transformation="FTP record copy (byte-identity)")
                for f in src.columns]
        elif src.attributes.get("record_layout") and target.attributes.get("record_layout"):
            # remote carries its own schema under different names (e.g. an
            # Oracle external table's positional columns), but it is the same
            # physical record.  Pair by BYTE START POSITION - never by list
            # order, which need not match the byte layout - so the rename is
            # field-precise.  A target field with no source field at the same
            # offset falls back to record-level (no guessing).
            src_by_start = {f["start"]: f["field"]
                            for f in src.attributes["record_layout"]}
            cms = []
            for tf in target.attributes["record_layout"]:
                sf = src_by_start.get(tf["start"])
                if sf:
                    cms.append(ColumnMapping(
                        source_columns=[f"{src.id}|{sf}"],
                        target_column=f"{target.id}|{tf['field']}",
                        transformation="FTP record copy (byte-identity; "
                                       "renamed by downstream loader)"))
                else:
                    cms.append(ColumnMapping(
                        source_columns=[f"{src.id}|*"],
                        target_column=f"{target.id}|{tf['field']}",
                        transformation="FTP record copy (record-level)"))
            edge.column_mappings = cms
        else:
            # name sets differ and there is no byte layout to pair on (e.g. XML
            # tags re-parsed from one text blob): assert record-level provenance
            edge.column_mappings = [
                ColumnMapping(source_columns=[f"{src.id}|*"],
                              target_column=f"{target.id}|{tcol}",
                              transformation="FTP record copy (record-level; "
                                             "downstream re-parses the bytes)")
                for tcol in target.columns]

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
