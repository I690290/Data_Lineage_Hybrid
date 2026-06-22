"""End-to-end validation of the MI5021 production-complex scenario:
IKJEFT01/DSNTIAUL hidden-SQL unload, nested CALL lineage (the sub-program
owns the DB2 I/O), and the dynamic-SQL construct reserved for AI inference.
"""

import textwrap
from pathlib import Path

import pytest

from ai_engine.base import AIProvider
from ai_engine.resolver import EdgeResolver
from parsers import EdgeType, ParserOrchestrator, Provenance
from parsers.base import DynamicConstruct, EdgeStatus
from parsers.jcl_parser import JclParser

SOURCE = Path(__file__).resolve().parent.parent / "mock-code"

RATINGS_TABLE = "TABLE:CRISK.COUNTERPARTY_RATINGS"
EXPOSURES_TABLE = "TABLE:CRISK.COUNTERPARTY_EXPOSURES"
UNLOAD_FILE = "FILE:CRISK.MI5021.CPTY.RATINGS.UNLOAD"
REPORT_FILE = "FILE:CRISK.MI5021.DEFAULT.RISK.REPORT"
UNLOAD_STEP = "PROGRAM:DSNTIAUL.STEP010"


@pytest.fixture(scope="module")
def result():
    return ParserOrchestrator().parse_tree(SOURCE)


def _edge(result, src, rel, tgt):
    return next((e for e in result.edges
                 if e.source_id == src and e.target_id == tgt
                 and e.edge_type == rel), None)


def _mapping(edge, target_col):
    return next(m for m in edge.column_mappings
                if m.target_column.endswith(f"|{target_col}"))


# ---------------------------------------------------------------------------
# IKJEFT01 / DSNTIAUL: SQL hidden in SYSTSIN+SYSIN becomes real lineage
# ---------------------------------------------------------------------------
def test_mi5021_end_to_end_chain(result):
    """DB2 unload -> master program -> (nested CALL DB2 read) -> report."""
    chain = [
        ("JOB:CRJMI521", EdgeType.EXECUTES, UNLOAD_STEP),
        (RATINGS_TABLE, EdgeType.READS_FROM, UNLOAD_STEP),
        (UNLOAD_STEP, EdgeType.WRITES_TO, UNLOAD_FILE),
        ("JOB:CRJMI521", EdgeType.EXECUTES, "PROGRAM:CRRSKMST"),
        (UNLOAD_FILE, EdgeType.READS_FROM, "PROGRAM:CRRSKMST"),
        ("PROGRAM:CRRSKMST", EdgeType.EXECUTES, "PROGRAM:CRRSKSUB"),
        (EXPOSURES_TABLE, EdgeType.READS_FROM, "PROGRAM:CRRSKSUB"),
        ("PROGRAM:CRRSKMST", EdgeType.WRITES_TO, REPORT_FILE),
    ]
    for src, rel, tgt in chain:
        assert _edge(result, src, rel, tgt) is not None, f"{src} -{rel}-> {tgt}"


def test_dsntiaul_unload_column_lineage(result):
    edge = _edge(result, UNLOAD_STEP, EdgeType.WRITES_TO, UNLOAD_FILE)
    cm = _mapping(edge, "RATING_GRADE")
    assert cm.source_columns == [f"{RATINGS_TABLE}|RATING_GRADE"]
    assert "DSNTIAUL UNLOAD" in cm.transformation
    assert "SELECT" in edge.transformation     # the hidden SQL is the logic


def test_unload_fd_names_unified_onto_unload_columns(result):
    """The unload writes SELECT-list names; CRRSKMST's FD names the same
    bytes. The file must expose ONE schema (the 5 unload columns); the
    reader's FD refs are canonicalised, the alias kept in attributes."""
    node = next(n for n in result.nodes if n.id == UNLOAD_FILE)
    assert set(node.columns) == {"COUNTERPARTY_ID", "LEGAL_NAME",
                                 "RATING_GRADE", "PD_PERCENT", "REVIEW_DATE"}
    assert node.attributes["fd_aliases_resolved"]["CRR-RATING-GRADE"] \
        == "RATING_GRADE"
    # the record layout follows the canonical names too
    assert {f["field"] for f in node.attributes["record_layout"]} \
        == set(node.columns)

    # reader lineage references the canonical name, keeping the chain
    # connected: TABLE|RATING_GRADE -> FILE|RATING_GRADE -> RPT-RATING-GRADE
    edge = _edge(result, "PROGRAM:CRRSKMST", EdgeType.WRITES_TO, REPORT_FILE)
    cm = _mapping(edge, "RPT-RATING-GRADE")
    assert cm.source_columns == [f"{UNLOAD_FILE}|RATING_GRADE"]
    # no CRR-* refs survive anywhere on the unload file
    refs = {r for e in result.edges for m in e.column_mappings
            for r in m.source_columns + [m.target_column]
            if r.startswith(f"{UNLOAD_FILE}|")}
    assert all("|CRR-" not in r for r in refs)
    assert not [u for u in result.unparsed
                if u.statement_type == "UNLOAD_FD_ALIAS"]


def test_unload_fd_mismatch_is_telemetry_not_guess(tmp_path):
    """Reader FD with a different field count cannot be aligned -> loud."""
    cobol = textwrap.dedent("""\
           IDENTIFICATION DIVISION.
           PROGRAM-ID. RDRPGM.
           ENVIRONMENT DIVISION.
           INPUT-OUTPUT SECTION.
           FILE-CONTROL.
               SELECT IN-FILE ASSIGN TO INDD
                   FILE STATUS IS WS-ST.
           DATA DIVISION.
           FILE SECTION.
           FD  IN-FILE.
           01  IN-REC.
               05  FLD-ONE     PIC X(5).
               05  FLD-TWO     PIC X(5).
               05  FLD-THREE   PIC X(5).
           WORKING-STORAGE SECTION.
           01  WS-ST           PIC XX.
           PROCEDURE DIVISION.
           MAIN-PARA.
               OPEN INPUT IN-FILE.
               CLOSE IN-FILE.
               STOP RUN.
    """)
    (tmp_path / "RDRPGM.cbl").write_text(
        "\n".join("       " + l for l in cobol.splitlines()) + "\n")
    (tmp_path / "UNLJOB.jcl").write_text("\n".join([
        "//UNLJOB   JOB (ACCT),'TEST',CLASS=A",
        "//STEP010  EXEC PGM=IKJEFT01",
        "//SYSTSIN  DD *",
        "  DSN SYSTEM(DBCR)",
        "  RUN PROGRAM(DSNTIAUL) PLAN(DSNTIAUL) PARMS('SQL')",
        "  END",
        "/*",
        "//SYSIN    DD *",
        "  SELECT COL_A, COL_B FROM CRISK.SOMETBL;",
        "/*",
        "//SYSREC00 DD DSN=PROD.SOME.UNLOAD,DISP=(NEW,CATLG)",
        "//STEP020  EXEC PGM=RDRPGM",
        "//INDD     DD DSN=PROD.SOME.UNLOAD,DISP=SHR",
    ]) + "\n")
    result = ParserOrchestrator().parse_tree(tmp_path)
    flagged = [u for u in result.unparsed
               if u.statement_type == "UNLOAD_FD_ALIAS"]
    assert len(flagged) == 1 and flagged[0].program == "RDRPGM"
    # and no invented alias mappings on the unload edge
    edge = next(e for e in result.edges
                if e.target_id == "FILE:PROD.SOME.UNLOAD"
                and e.edge_type == EdgeType.WRITES_TO)
    assert all(not m.target_column.endswith(("FLD-ONE", "FLD-TWO", "FLD-THREE"))
               for m in edge.column_mappings)


# ---------------------------------------------------------------------------
# Nested CALL: the callee's DB2 columns surface in the caller's output file
# ---------------------------------------------------------------------------
def test_nested_call_db2_column_lineage(result):
    edge = _edge(result, "PROGRAM:CRRSKMST", EdgeType.WRITES_TO, REPORT_FILE)

    total = _mapping(edge, "RPT-TOTAL-EXPOSURE")
    assert total.source_columns == [f"{EXPOSURES_TABLE}|EXPOSURE_AMOUNT"]
    assert "CALL 'CRRSKSUB'" in total.transformation

    # derived field merges both call-returned DB2 columns AND the unload
    # file (via its canonical unload column name, not the local FD alias)
    weighted = _mapping(edge, "RPT-WEIGHTED-RISK")
    assert set(weighted.source_columns) == {
        f"{EXPOSURES_TABLE}|EXPOSURE_AMOUNT",
        f"{EXPOSURES_TABLE}|COLLATERAL_VALUE",
        f"{UNLOAD_FILE}|PD_PERCENT"}


def test_call_sources_connected_at_entity_level(result):
    """The callee reads DB2, the caller writes the report: the source table
    must still reach the caller entity-level, or the Entity Lineage view
    shows less than the Column Lineage view."""
    edge = _edge(result, EXPOSURES_TABLE, EdgeType.READS_FROM,
                 "PROGRAM:CRRSKMST")
    assert edge is not None
    assert "derived from column-level mappings" in edge.transformation


def test_entity_view_never_smaller_than_column_view(result):
    """Estate-wide invariant: every deterministic column-mapping source
    owner has an entity-level READS_FROM edge to the writing program."""
    ids = {n.id for n in result.nodes}
    reads = {(e.source_id, e.target_id) for e in result.edges
             if e.edge_type == EdgeType.READS_FROM}
    for e in result.edges:
        if e.edge_type != EdgeType.WRITES_TO:
            continue
        for cm in e.column_mappings:
            for ref in cm.source_columns:
                owner = ref.rsplit("|", 1)[0]
                if owner in (e.source_id, e.target_id) or owner not in ids:
                    continue
                assert (owner, e.source_id) in reads, \
                    f"{owner} feeds {cm.target_column} but has no " \
                    f"entity-level edge to {e.source_id}"


def test_resolved_call_retired_from_telemetry(result):
    """The static CALL was mapped, so it must no longer be coverage noise."""
    assert not [u for u in result.unparsed if u.statement_type == "COBOL_CALL"]


def test_unresolvable_call_stays_in_telemetry(tmp_path):
    """A static CALL whose callee source is absent must still fail loud."""
    src = textwrap.dedent("""\
           IDENTIFICATION DIVISION.
           PROGRAM-ID. LONEPGM.
           PROCEDURE DIVISION.
           MAIN-PARA.
               CALL 'MISSING1' USING WS-AREA.
    """)
    (tmp_path / "LONEPGM.cbl").write_text(
        "\n".join("       " + l for l in src.splitlines()) + "\n")
    result = ParserOrchestrator().parse_tree(tmp_path)
    calls = [u for u in result.unparsed if u.statement_type == "COBOL_CALL"]
    assert len(calls) == 1
    assert "not in scan scope" in calls[0].reason


# ---------------------------------------------------------------------------
# Dynamic SQL: flagged for AI, never guessed by the deterministic layer
# ---------------------------------------------------------------------------
def test_dynamic_insert_flagged_for_ai(result):
    dyn = [d for d in result.dynamic_constructs
           if d.construct_type == "DYNAMIC_SQL"]
    assert len(dyn) == 1
    assert dyn[0].program == "CRRSKMST"
    assert "EXECUTE IMMEDIATE" in dyn[0].snippet
    # the AI gets the table-name assembly as context
    assert "MI5021_RISK_SUMMARY_" in dyn[0].context
    assert all(e.provenance == Provenance.DETERMINISTIC for e in result.edges)


# ---------------------------------------------------------------------------
# TSO detector telemetry: unsupported IKJEFT shapes fail loud, never silent
# ---------------------------------------------------------------------------
def _parse_jcl(tmp_path, lines):
    path = tmp_path / "TSOJOB.jcl"
    path.write_text("\n".join(lines) + "\n")
    return JclParser().parse(path)


def test_tso_systsin_not_inline_flagged(tmp_path):
    result = _parse_jcl(tmp_path, [
        "//TSOJOB   JOB (ACCT),'TEST',CLASS=A",
        "//STEP010  EXEC PGM=IKJEFT01",
        "//SYSTSPRT DD SYSOUT=*",
        "//SYSTSIN  DD DSN=PROD.CTLLIB.TSOCMDS,DISP=SHR",
    ])
    assert [u.statement_type for u in result.unparsed] == ["JCL_TSO_SYSTSIN"]


def test_tso_no_run_program_flagged(tmp_path):
    result = _parse_jcl(tmp_path, [
        "//TSOJOB   JOB (ACCT),'TEST',CLASS=A",
        "//STEP010  EXEC PGM=IKJEFT01",
        "//SYSTSIN  DD *",
        "  DSN SYSTEM(DBCR)",
        "  END",
        "/*",
    ])
    assert [u.statement_type for u in result.unparsed] == ["JCL_TSO_RUN"]


def test_tso_dsntep2_dml_flagged(tmp_path):
    result = _parse_jcl(tmp_path, [
        "//TSOJOB   JOB (ACCT),'TEST',CLASS=A",
        "//STEP010  EXEC PGM=IKJEFT01",
        "//SYSTSIN  DD *",
        "  DSN SYSTEM(DBCR)",
        "  RUN PROGRAM(DSNTEP2) PLAN(DSNTEP2)",
        "  END",
        "/*",
        "//SYSIN    DD *",
        "  UPDATE CRISK.ACCOUNTS SET BAL = 0;",
        "/*",
    ])
    flagged = [u for u in result.unparsed if u.statement_type == "JCL_TSO_SQL"]
    assert len(flagged) == 1 and "DSNTEP2" in flagged[0].reason


def test_dsntiaul_select_star_is_record_level(tmp_path):
    """SELECT * unload -> record-level |* mapping, no positional guessing."""
    result = _parse_jcl(tmp_path, [
        "//TSOJOB   JOB (ACCT),'TEST',CLASS=A",
        "//STEP010  EXEC PGM=IKJEFT01",
        "//SYSTSIN  DD *",
        "  DSN SYSTEM(DBCR)",
        "  RUN PROGRAM(DSNTIAUL) PLAN(DSNTIAUL) PARMS('SQL')",
        "  END",
        "/*",
        "//SYSIN    DD *",
        "  SELECT * FROM CRISK.LIMITS;",
        "/*",
        "//SYSREC00 DD DSN=PROD.LIMITS.UNLOAD,DISP=(NEW,CATLG)",
    ])
    edge = next(e for e in result.edges
                if e.target_id == "FILE:PROD.LIMITS.UNLOAD")
    assert [m.target_column for m in edge.column_mappings] \
        == ["FILE:PROD.LIMITS.UNLOAD|*"]
    assert edge.column_mappings[0].source_columns == ["TABLE:CRISK.LIMITS|*"]
    assert result.unparsed == []


def test_tso_application_run_binds_dds(tmp_path):
    """RUN PROGRAM(<app>) behaves like EXEC PGM= for DD bindings."""
    result = _parse_jcl(tmp_path, [
        "//TSOJOB   JOB (ACCT),'TEST',CLASS=A",
        "//STEP010  EXEC PGM=IKJEFT01",
        "//SYSTSIN  DD *",
        "  DSN SYSTEM(DBCR)",
        "  RUN PROGRAM(MYAPPPGM) PLAN(MYAPPPGM)",
        "  END",
        "/*",
        "//CUSTIN   DD DSN=PROD.CUSTOMER.DAILY,DISP=SHR",
    ])
    job = next(n for n in result.nodes if n.kind.value == "Job")
    assert job.attributes["dd_bindings"] == [{
        "job": "TSOJOB", "step": "STEP010", "program": "MYAPPPGM",
        "dd_name": "CUSTIN", "dsn": "PROD.CUSTOMER.DAILY"}]
    assert _edge(result, "JOB:TSOJOB", EdgeType.EXECUTES,
                 "PROGRAM:MYAPPPGM") is not None


# ---------------------------------------------------------------------------
# AI engine: structured payload contract + auditability (no network)
# ---------------------------------------------------------------------------
class FakeProvider(AIProvider):
    name = "fake"
    model_id = "fake-model-1"

    def __init__(self, payloads):
        self._payloads = list(payloads)
        self.call_count = 0

    def embed(self, texts):
        return [[0.0] for _ in texts]

    def complete(self, system, user, max_tokens=1024):
        return ""

    def complete_json(self, system, user, max_tokens=2048):
        self.call_count += 1
        return self._payloads.pop(0)


def _construct():
    return DynamicConstruct(
        program="CRRSKMST", language="COBOL", construct_type="DYNAMIC_SQL",
        snippet="EXEC SQL EXECUTE IMMEDIATE :WS-SQL-TEXT END-EXEC",
        context="STRING WS-SQL-PREFIX WS-RUN-YYYYMM WS-SQL-SUFFIX ... "
                "VALUE 'INSERT INTO CRISK.MI5021_RISK_SUMMARY_'",
        path="CRRSKMST.cbl", line=156)


def test_ai_structured_payload_becomes_provisional_edge():
    payloads = [
        {   # resolver: the new structured contract
            "lineage": [{
                "source_entity": "CRISK.MI5021_RISK_SUMMARY_*",
                "source_kind": "Table",
                "target_entity": "CRISK.MI5021_RISK_SUMMARY_*",
                "target_kind": "Table",
                "edge_type": "WRITES_TO",
                "column_mappings": [{
                    "source_column": "WS-WEIGHTED-RISK",
                    "target_column": "WEIGHTED_RISK",
                    "transformation": "dynamic INSERT parameter"}],
                "reasoning": "INSERT INTO month-partitioned summary table",
            }],
            "confidence_score": 0.82,
            "reasoning": "Table name is a static prefix plus run YYYYMM",
        },
        {   # judge: independent gate
            "confidence": 0.9, "verdict": "ACCEPT",
            "rationale": "table prefix is explicit in the code",
        },
    ]
    resolver = EdgeResolver(FakeProvider(payloads), threshold=0.6)
    nodes, edges = resolver.resolve_all([_construct()],
                                        known_entities=["PROGRAM:CRRSKMST"])
    assert len(edges) == 1
    edge = edges[0]
    assert edge.provenance == Provenance.AI_INFERRED
    assert edge.status == EdgeStatus.PROVISIONAL
    assert edge.confidence == 0.9
    assert edge.reasoning == "INSERT INTO month-partitioned summary table"
    # auditability: model + prompt context recorded for compliance
    md = edge.ai_metadata
    assert md["provider"] == "fake" and md["model"] == "fake-model-1"
    assert md["self_confidence"] == 0.82
    assert md["judge_rationale"] == "table prefix is explicit in the code"
    assert "EXECUTE IMMEDIATE" in md["prompt_context"]
    assert nodes and nodes[0].attributes["model"] == "fake-model-1"


def test_ai_malformed_and_duplicate_proposals_filtered():
    """Junk observed from live models: null entity names, '?' parameter
    markers echoed as column names, the same edge proposed twice. None of
    it may reach the judge or the graph."""
    payloads = [
        {"lineage": [
            {"source_entity": "CRRSKMST", "target_entity": "None",
             "edge_type": "WRITES_TO", "reasoning": "junk entity"},
            {"source_entity": "X", "target_entity": "CRISK.MI5021_RISK_SUMMARY_*",
             "edge_type": "WRITES_TO",
             "column_mappings": [
                 {"source_column": "WS-NET-EXPOSURE", "target_column": "?"},
                 {"source_column": "WS-WEIGHTED-RISK",
                  "target_column": "WEIGHTED_RISK"}],
             "reasoning": "dynamic INSERT"},
            {"source_entity": "X", "target_entity": "CRISK.MI5021_RISK_SUMMARY_*",
             "edge_type": "WRITES_TO", "reasoning": "same edge, reworded"},
        ], "confidence_score": 0.8, "reasoning": "overall"},
        # judge runs ONCE: only the single valid, deduped proposal survives
        {"confidence": 0.9, "verdict": "ACCEPT", "rationale": "ok"},
    ]
    resolver = EdgeResolver(FakeProvider(payloads), threshold=0.6)
    nodes, edges = resolver.resolve_all([_construct()], known_entities=[])
    assert len(edges) == 1
    assert edges[0].target_id == "TABLE:CRISK.MI5021_RISK_SUMMARY_*"
    # the '?' mapping is gone, the real one kept
    assert [m.target_column for m in edges[0].column_mappings] == ["WEIGHTED_RISK"]


def test_ai_prefixed_entity_name_not_double_prefixed():
    """Models sometimes echo the kind prefix into the entity name
    (`FILE:CR_ACX_VALID_*`). emit must not re-prefix it into
    `FILE:FILE:...`, and the bare/prefixed variants must dedupe to one edge."""
    payloads = [
        {"lineage": [
            {"source_entity": "PROGRAM:FTP.STEP010",
             "target_entity": "FILE:CR_ACX_VALID_*", "target_kind": "File",
             "edge_type": "WRITES_TO", "reasoning": "ftp put"},
            {"source_entity": "FTP.STEP010",          # same edge, bare names
             "target_entity": "CR_ACX_VALID_*", "target_kind": "File",
             "edge_type": "WRITES_TO", "reasoning": "ftp put dup"},
        ], "confidence_score": 0.8, "reasoning": "overall"},
        {"confidence": 0.9, "verdict": "ACCEPT", "rationale": "ok"},
    ]
    resolver = EdgeResolver(FakeProvider(payloads), threshold=0.6)
    nodes, edges = resolver.resolve_all([_construct()], known_entities=[])
    assert len(edges) == 1                       # deduped to one
    assert edges[0].target_id == "FILE:CR_ACX_VALID_*"   # not FILE:FILE:...
    assert all(n.id.count(":") == 1 for n in nodes)


def test_ai_edge_below_judge_threshold_is_dropped():
    payloads = [
        {"lineage": [{"source_entity": "X", "target_entity": "X",
                      "edge_type": "WRITES_TO", "reasoning": "weak"}],
         "confidence_score": 0.9, "reasoning": "guess"},
        {"confidence": 0.2, "verdict": "REJECT", "rationale": "no evidence"},
    ]
    resolver = EdgeResolver(FakeProvider(payloads), threshold=0.6)
    nodes, edges = resolver.resolve_all([_construct()], known_entities=[])
    assert edges == [] and nodes == []


# ---------------------------------------------------------------------------
# Column-level retry: missing column_mappings trigger a third LLM pass
# ---------------------------------------------------------------------------
def test_ai_column_retry_fills_mappings():
    """When the first pass returns no column_mappings for a WRITES_TO edge,
    a third targeted call must be made and its mappings used."""
    provider = FakeProvider([
        {   # resolver: WRITES_TO accepted but column_mappings empty
            "lineage": [{
                "source_entity": "CRISK.MI5021_RISK_SUMMARY_*",
                "source_kind": "Table",
                "target_entity": "CRISK.MI5021_RISK_SUMMARY_*",
                "target_kind": "Table",
                "edge_type": "WRITES_TO",
                "column_mappings": [],
                "reasoning": "INSERT INTO month-partitioned summary table",
            }],
            "confidence_score": 0.82,
            "reasoning": "Table name is a static prefix plus run YYYYMM",
        },
        {   # judge: accepts the edge
            "confidence": 0.9, "verdict": "ACCEPT",
            "rationale": "table prefix is explicit in the code",
        },
        {   # column retry: returns column detail
            "column_mappings": [{
                "source_column": "WS-WEIGHTED-RISK",
                "target_column": "WEIGHTED_RISK",
                "transformation": "direct from working-storage variable",
            }],
            "reasoning": "INSERT selects WS variable into summary table column",
        },
    ])
    resolver = EdgeResolver(provider, threshold=0.6)
    _, edges = resolver.resolve_all([_construct()], known_entities=["PROGRAM:CRRSKMST"])
    assert len(edges) == 1
    assert provider.call_count == 3          # resolver + judge + column retry
    assert len(edges[0].column_mappings) == 1
    assert edges[0].column_mappings[0].target_column == "WEIGHTED_RISK"
    assert edges[0].column_mappings[0].source_columns == ["WS-WEIGHTED-RISK"]
    assert "working-storage" in edges[0].column_mappings[0].transformation


def test_ai_column_retry_graceful_on_empty_response():
    """If the column retry also returns no mappings, the entity-level edge is
    still kept — Column Lineage will be empty for this edge but nothing breaks."""
    provider = FakeProvider([
        {
            "lineage": [{
                "source_entity": "CRISK.MI5021_RISK_SUMMARY_*",
                "source_kind": "Table",
                "target_entity": "CRISK.MI5021_RISK_SUMMARY_*",
                "target_kind": "Table",
                "edge_type": "WRITES_TO",
                "column_mappings": [],
                "reasoning": "INSERT",
            }],
            "confidence_score": 0.8, "reasoning": "dynamic SQL",
        },
        {"confidence": 0.85, "verdict": "ACCEPT", "rationale": "ok"},
        {"column_mappings": [], "reasoning": "cannot determine columns from code"},
    ])
    resolver = EdgeResolver(provider, threshold=0.6)
    _, edges = resolver.resolve_all([_construct()], known_entities=[])
    assert len(edges) == 1
    assert provider.call_count == 3
    assert edges[0].column_mappings == []    # empty but edge itself kept


def test_ai_reads_from_no_column_retry():
    """READS_FROM edges do not trigger a column retry even when column_mappings
    is empty — exactly 2 LLM calls (resolver + judge), never a third."""
    provider = FakeProvider([
        {
            "lineage": [{
                "source_entity": "CRISK.COUNTERPARTY_RATINGS",
                "source_kind": "Table",
                "target_entity": "CRRSKMST",
                "target_kind": "Program",
                "edge_type": "READS_FROM",
                "column_mappings": [],
                "reasoning": "program reads the ratings table",
            }],
            "confidence_score": 0.9, "reasoning": "reads",
        },
        {"confidence": 0.88, "verdict": "ACCEPT", "rationale": "evident from code"},
    ])
    resolver = EdgeResolver(provider, threshold=0.6)
    _, edges = resolver.resolve_all([_construct()], known_entities=[])
    assert len(edges) == 1
    assert provider.call_count == 2          # no column retry for READS_FROM
    assert edges[0].column_mappings == []


# ---------------------------------------------------------------------------
# Estate-wide: write-target FILE columns must be present in node.columns
# ---------------------------------------------------------------------------
def test_write_target_file_columns_in_node_columns(result):
    """Every FILE that is a WRITES_TO target must expose all its target
    column names in node.columns (derived from the FD layout).  Source TABLE
    columns (e.g. DB2 cursor refs) need not be in node.columns at parse
    time — they are written to Neo4j via the edge writer's HAS_COLUMN path."""
    from parsers.base import NodeKind
    file_cols = {n.id: set(n.columns) for n in result.nodes
                 if n.kind == NodeKind.FILE}
    missing = []
    for edge in result.edges:
        if edge.edge_type != EdgeType.WRITES_TO:
            continue
        tgt = edge.target_id
        if tgt not in file_cols:
            continue
        for cm in edge.column_mappings:
            if "|" not in cm.target_column or cm.target_column.endswith("|*"):
                continue
            owner, col = cm.target_column.rsplit("|", 1)
            if owner == tgt and col not in file_cols[tgt]:
                missing.append(f"{tgt} missing target column {col}")
    assert not missing, (
        f"Write-target FILE columns absent from node.columns: {missing[:10]}")


def test_all_column_mapping_refs_are_well_formed(result):
    """Every column ref in every edge must be either 'ENTITY_ID|COL' or
    'ENTITY_ID|*' (record-level).  Bare unqualified refs would break the
    Neo4j writer's _col_ref fallback and the column path highlighter."""
    bare = []
    for edge in result.edges:
        for cm in edge.column_mappings:
            for ref in cm.source_columns + [cm.target_column]:
                if ref and "|" not in ref:
                    bare.append(f"{edge.source_id}->{edge.target_id}: {ref!r}")
    assert not bare, f"Bare (unqualified) column refs found: {bare[:10]}"
