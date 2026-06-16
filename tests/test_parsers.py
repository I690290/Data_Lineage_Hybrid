"""Regression tests for the deterministic core against the MI4014 corpus."""

from pathlib import Path

import pytest

from parsers import EdgeType, ParserOrchestrator, Provenance

SOURCE = Path(__file__).resolve().parent.parent / "mock-code"

CUST_EXTRACT = "FILE:CRISK.BATCH.CUST.BHSCORE.EXTRACT"
TRANS_EXTRACT = "FILE:CRISK.BATCH.TRANS.BHSCORE.EXTRACT"
MERGED_EXTRACT = "FILE:CRISK.BATCH.MERGED.BHSCORE.EXTRACT"
MAINFRAME_XML = "FILE:NEPTUNE.FILES.LOAD.MI4014.XML"
ORACLE_XML = "FILE:MI4014_TRANSACTION_EXTRACT_TSB_NAM65_20260514.XML"
EXT_TABLE = "TABLE:BDD_NEPTUNE_DICC.MI4014_TRANSACCIONES_DIARIAS"
STG_TABLE = "TABLE:BDD_NEPTUNE_DICC.MI4014_TRANSACCIONES_STG"


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


def test_end_to_end_chain(result):
    """DB2 -> COBOL -> SORT -> XML gen -> FTP / Oracle loader -> proc -> view."""
    chain = [
        ("TABLE:CRISK.CUST_ACCOUNT_MASTER", EdgeType.READS_FROM, "PROGRAM:CRDB2EXT"),
        ("PROGRAM:CRDB2EXT", EdgeType.WRITES_TO, CUST_EXTRACT),
        (CUST_EXTRACT, EdgeType.READS_FROM, "PROGRAM:CRTXNEXT"),
        ("TABLE:CRISK.DAILY_TRANSACTIONS", EdgeType.READS_FROM, "PROGRAM:CRTXNEXT"),
        ("PROGRAM:CRTXNEXT", EdgeType.WRITES_TO, TRANS_EXTRACT),
        (CUST_EXTRACT, EdgeType.READS_FROM, "PROGRAM:SORT.STEP030"),
        (TRANS_EXTRACT, EdgeType.READS_FROM, "PROGRAM:SORT.STEP030"),
        ("PROGRAM:SORT.STEP030", EdgeType.WRITES_TO, MERGED_EXTRACT),
        (MERGED_EXTRACT, EdgeType.READS_FROM, "PROGRAM:CRXMLGEN"),
        ("PROGRAM:CRXMLGEN", EdgeType.WRITES_TO, MAINFRAME_XML),
        (MAINFRAME_XML, EdgeType.READS_FROM, "PROGRAM:FTP.STEP050"),
        (ORACLE_XML, EdgeType.READS_FROM,
         "PROGRAM:ORACLE_LOADER.MI4014_TRANSACCIONES_DIARIAS"),
        ("PROGRAM:ORACLE_LOADER.MI4014_TRANSACCIONES_DIARIAS",
         EdgeType.WRITES_TO, EXT_TABLE),
        (EXT_TABLE, EdgeType.READS_FROM,
         "PROGRAM:BDD_NEPTUNE_DICC.PRC_MI4014_STAGE_LOAD"),
        ("PROGRAM:BDD_NEPTUNE_DICC.PRC_MI4014_STAGE_LOAD",
         EdgeType.WRITES_TO, STG_TABLE),
        (STG_TABLE, EdgeType.TRANSFORMS_TO,
         "TABLE:BDD_NEPTUNE_DICC.V_MI4014_TRANSACCIONES_VALIDAS"),
    ]
    for src, rel, tgt in chain:
        assert _edge(result, src, rel, tgt) is not None, f"{src} -{rel}-> {tgt}"


def test_dd_cross_linking(result):
    """COBOL logical DD names re-pointed onto physical JCL datasets."""
    ids = {n.id for n in result.nodes}
    assert CUST_EXTRACT in ids and "FILE:BHSCOEXT" not in ids
    assert TRANS_EXTRACT in ids and "FILE:BHSCOTXN" not in ids


def test_db2_cursor_column_lineage(result):
    """DECLARE CURSOR + FETCH INTO + MOVE chain -> column-level lineage."""
    edge = _edge(result, "PROGRAM:CRDB2EXT", EdgeType.WRITES_TO, CUST_EXTRACT)
    cm = _mapping(edge, "CRA-EXTERNAL-ACCT-NUM")
    assert cm.source_columns == [
        "TABLE:CRISK.CUST_ACCOUNT_MASTER|EXTERNAL_ACCOUNT_NUMBER"]
    assert "TRIM(A.EXTERNAL_ACCOUNT_NUMBER)" in cm.transformation


def test_conditional_move_merges_both_branches(result):
    """IF/ELSE MOVE: new-account number descends from DB2 txn AND the
    customer driving file (record-level)."""
    edge = _edge(result, "PROGRAM:CRTXNEXT", EdgeType.WRITES_TO, TRANS_EXTRACT)
    cm = _mapping(edge, "CTR-NEW-MAIN-ACCT-NUM")
    assert "TABLE:CRISK.DAILY_TRANSACTIONS|NEW_MAIN_ACCOUNT_NUMBER" in cm.source_columns
    assert f"{CUST_EXTRACT}|*" in cm.source_columns          # READ INTO fallback


def test_dfsort_joinkeys_captured_as_logic(result):
    edge = _edge(result, "PROGRAM:SORT.STEP030", EdgeType.WRITES_TO, MERGED_EXTRACT)
    assert "JOINKEYS" in edge.transformation
    assert "JOIN UNPAIRED,F2,ONLY" in edge.transformation


def test_dfsort_copybook_record_layouts(result):
    """PIC clauses -> 1-based byte offsets on the physical FILE nodes."""
    trans = next(n for n in result.nodes if n.id == TRANS_EXTRACT)
    layout = {f["field"]: (f["start"], f["length"])
              for f in trans.attributes["record_layout"]}
    assert layout["CTR-EXTERNAL-ACCT-NUM"] == (1, 20)
    assert layout["CTR-SUB-ACCOUNT-NUM"] == (21, 10)
    assert layout["CTR-TRANSACTION-AMT"] == (47, 8)      # S9(13)V99 COMP-3
    assert layout["CTR-TRAN-AMT-DISPLAY"] == (55, 17)    # -9(13).99 edited


def test_dfsort_join_column_lineage(result):
    """JOINKEYS + REFORMAT + OUTFIL BUILD resolved to column mappings:
    data bytes flow from F2 (TRANS); join-key columns also descend from
    F1 (CUST) - the join itself is visible at column level."""
    edge = _edge(result, "PROGRAM:SORT.STEP030", EdgeType.WRITES_TO, MERGED_EXTRACT)

    key = _mapping(edge, "CTR-EXTERNAL-ACCT-NUM")
    assert set(key.source_columns) == {
        f"{TRANS_EXTRACT}|CTR-EXTERNAL-ACCT-NUM",
        f"{CUST_EXTRACT}|CRA-EXTERNAL-ACCT-NUM"}
    assert "JOINKEYS" in key.transformation

    sub = _mapping(edge, "CTR-SUB-ACCOUNT-NUM")
    assert f"{CUST_EXTRACT}|CRA-SUB-ACCOUNT-NUM" in sub.source_columns

    # non-key data columns come from the transaction file only (REFORMAT F2)
    posted = _mapping(edge, "CTR-POSTED-DATE")
    assert posted.source_columns == [f"{TRANS_EXTRACT}|CTR-POSTED-DATE"]


def test_external_table_xml_tag_mappings(result):
    edge = _edge(result, "PROGRAM:ORACLE_LOADER.MI4014_TRANSACCIONES_DIARIAS",
                 EdgeType.WRITES_TO, EXT_TABLE)
    cm = _mapping(edge, "MAIN_ACCOUNT_NUMBER")
    assert cm.source_columns == [f"{ORACLE_XML}|EXTERNAL_ACCOUNT_NUMBER"]
    assert "<external_account_number>" in cm.transformation


def test_stored_procedure_type_casting(result):
    edge = _edge(result, "PROGRAM:BDD_NEPTUNE_DICC.PRC_MI4014_STAGE_LOAD",
                 EdgeType.WRITES_TO, STG_TABLE)
    cm = _mapping(edge, "TRANSACTION_AMOUNT")
    assert cm.source_columns == [f"{EXT_TABLE}|TRANSACTION_AMOUNT"]
    assert "TO_NUMBER" in cm.transformation


def test_view_column_lineage(result):
    edge = _edge(result, STG_TABLE, EdgeType.TRANSFORMS_TO,
                 "TABLE:BDD_NEPTUNE_DICC.V_MI4014_LOAD_AUDIT")
    cm = _mapping(edge, "PASSED_ROWS")
    assert cm.source_columns == [f"{STG_TABLE}|LOAD_STATUS"]
    assert "SUM(CASE WHEN LOAD_STATUS = 'P'" in cm.transformation


def test_only_known_constructs_flagged_nothing_guessed(result):
    """Exactly two dynamic constructs estate-wide (FTP &DATE remote name +
    the MI5021 month-partitioned dynamic INSERT); zero invented edges."""
    flagged = sorted((d.language, d.construct_type)
                     for d in result.dynamic_constructs)
    assert flagged == [("COBOL", "DYNAMIC_SQL"), ("JCL", "JCL_SYMBOLIC")]
    symbolic = next(d for d in result.dynamic_constructs
                    if d.construct_type == "JCL_SYMBOLIC")
    assert "&DATE" in symbolic.snippet
    assert all(e.provenance == Provenance.DETERMINISTIC for e in result.edges)
