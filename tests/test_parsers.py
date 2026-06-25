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


def test_transform_steps_ordered_source_to_target(result):
    """The transformation chain must be stored as ordered steps reading
    source -> target (the SQL/host-var step that fills the host variable
    BEFORE the COBOL MOVE that lands it in the output field), so the UI can
    show every WS hop in flow order - not just a 'direct' / 'OPEN' line."""
    edge = _edge(result, "PROGRAM:CRDB2EXT", EdgeType.WRITES_TO, CUST_EXTRACT)
    cm = _mapping(edge, "CRA-EXTERNAL-ACCT-NUM")
    assert cm.transform_steps == [
        "TRIM(A.EXTERNAL_ACCOUNT_NUMBER)",
        "MOVE HV-EXT-ACCT-NUM TO CRA-EXTERNAL-ACCT-NUM",
    ]
    # the joined string is the same content, same order
    assert cm.transformation == "; ".join(cm.transform_steps)


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
    """Only genuinely unresolvable constructs are flagged estate-wide.

    The FTP `&DATE` remote names (MI4014's XML put and the four credit_risk_mart
    CRJXFER .dat puts) are deterministic byte-identity copies whose symbolic is
    reconciled against the concrete filename a downstream Oracle external table
    already names (`_bridge_ftp_remote_alias`) - so they are resolved, not
    flagged. The only construct left for the AI layer is MI5021's
    month-partitioned dynamic INSERT (`EXECUTE IMMEDIATE`)."""
    flagged = sorted((d.language, d.construct_type)
                     for d in result.dynamic_constructs)
    assert flagged == [("COBOL", "DYNAMIC_SQL")]
    assert all(e.provenance == Provenance.DETERMINISTIC for e in result.edges)


def test_group_move_record_copy_column_lineage(result):
    """`MOVE EMP-FEED-REC TO EMP-VALID-REC` is a whole-record copy (both FD
    records expand the same copybook): it must produce field-by-field identity
    lineage from the feed file to the valid file, not a disconnected box."""
    edge = _edge(result, "PROGRAM:CEMPDQA", EdgeType.WRITES_TO,
                 "FILE:CRDM.EMP.VALID.DAT")
    assert edge is not None and edge.column_mappings
    cm = _mapping(edge, "EMD-EMP-ID")
    assert cm.source_columns == ["FILE:CRDM.EMP.PROCESSED.FEED|EMD-EMP-ID"]
    assert "group move" in cm.transformation.lower()


def test_ftp_symbolic_reconciled_to_oracle_file(result):
    """FTP `put <dsn> CR_ACX_VALID_&DATE..dat` is reconciled against the Oracle
    external-table LOCATION `CR_ACX_VALID_20260622.dat`: the symbolic remote and
    the concrete file are one node, &DATE is resolved, and the mainframe->Oracle
    copy is a single connected chain with byte-identity column lineage."""
    ids = {n.id for n in result.nodes}
    resolved = "FILE:CR_ACX_VALID_20260622.DAT"
    assert resolved in ids
    # no wildcard / double-prefixed fragments survive
    assert not any("*" in i or i.count("FILE:") > 1 for i in ids)
    # deterministic FTP transfer edge: byte-identity copy paired field-for-field
    # by byte position onto the remote's own (Oracle) column names
    ftp = _edge(result, "PROGRAM:FTP.STEP010", EdgeType.WRITES_TO, resolved)
    assert ftp is not None and ftp.provenance == Provenance.DETERMINISTIC
    assert any(m.source_columns == ["FILE:CRDM.ACX.VALID.DAT|AXD-ACCOUNT-NUMBER"]
               and m.target_column == f"{resolved}|ACCOUNT_NUMBER"
               for m in ftp.column_mappings)
    # chain continues into the Oracle loader
    assert _edge(result, resolved, EdgeType.READS_FROM,
                 "PROGRAM:ORACLE_LOADER.ACCOUNT_EXPOSURE_EXT") is not None


def test_positional_external_table_column_lineage(result):
    """An ORACLE_LOADER external table with fixed POSITION fields must map the
    loader file's columns to the table columns (not just XML ENCLOSED BY), so
    the mainframe->Oracle chain stays column-connected through staging."""
    loader = "PROGRAM:ORACLE_LOADER.ACCOUNT_EXPOSURE_EXT"
    edge = _edge(result, loader, EdgeType.WRITES_TO,
                 "TABLE:CR_STAGE.ACCOUNT_EXPOSURE_EXT")
    assert edge is not None and len(edge.column_mappings) == 17
    cm = _mapping(edge, "ACCOUNT_NUMBER")
    assert cm.source_columns == ["FILE:CR_ACX_VALID_20260622.DAT|ACCOUNT_NUMBER"]
    assert "POSITION(1:8)" in cm.transformation
    # the EAD metric column lands at byte offset 113:129 of the .dat feed
    cm_ead = _mapping(edge, "EAD_GBP")
    assert "POSITION(113:129)" in cm_ead.transformation


def test_end_to_end_column_chain_mainframe_to_oracle_mart(result):
    """One DB2 column is traceable, hop by hop, from the source table through
    COBOL, the FTP transfer, the Oracle external table and staging, into the
    final mart - across all three languages with no break."""
    def col_targets(src):
        return {m.target_column for e in result.edges
                for m in e.column_mappings if src in m.source_columns}
    hops = [
        ("TABLE:CRDB2.ACCOUNT_EXPOSURE|ACCOUNT_NUMBER",
         "FILE:CRDM.ACX.PROCESSED.FEED|AXD-ACCOUNT-NUMBER"),
        ("FILE:CRDM.ACX.PROCESSED.FEED|AXD-ACCOUNT-NUMBER",
         "FILE:CRDM.ACX.VALID.DAT|AXD-ACCOUNT-NUMBER"),
        ("FILE:CRDM.ACX.VALID.DAT|AXD-ACCOUNT-NUMBER",
         "FILE:CR_ACX_VALID_20260622.DAT|ACCOUNT_NUMBER"),
        ("FILE:CR_ACX_VALID_20260622.DAT|ACCOUNT_NUMBER",
         "TABLE:CR_STAGE.ACCOUNT_EXPOSURE_EXT|ACCOUNT_NUMBER"),
        ("TABLE:CR_STAGE.ACCOUNT_EXPOSURE_EXT|ACCOUNT_NUMBER",
         "TABLE:CR_STAGE.ACCOUNT_EXPOSURE_STG|ACCOUNT_NUMBER_STG"),
        ("TABLE:CR_STAGE.ACCOUNT_EXPOSURE_STG|ACCOUNT_NUMBER_STG",
         "TABLE:CR_MART.TMP_ACCOUNT_EXPOSURE|ACCOUNT_NUMBER"),
        ("TABLE:CR_MART.TMP_ACCOUNT_EXPOSURE|ACCOUNT_NUMBER",
         "TABLE:CR_MART.CREDIT_RISK_MODEL|ACCOUNT_NUMBER"),
    ]
    for src, nxt in hops:
        assert nxt in col_targets(src), f"broken hop: {src} -> {nxt}"


def _feed_mapping(result, target_col):
    edge = _edge(result, "PROGRAM:CACXDRV", EdgeType.WRITES_TO,
                 "FILE:CRDM.ACX.PROCESSED.FEED")
    return _mapping(edge, target_col)


def test_cobol_ead_compute_lineage(result):
    """EAD = DRAWN + (UNDRAWN * CCF) + ACCRUED is captured across the nested
    CACXDRV->CACXCTL->CACXBIZ->CACXDAO CALL chain: the feed column traces back
    to exactly the DB2 columns that feed the COMPUTE (the CCF being looked up by
    PRODUCT_CD via SEARCH ALL)."""
    cm = _feed_mapping(result, "AXD-EAD-GBP")
    assert set(cm.source_columns) == {
        "TABLE:CRDB2.ACCOUNT_EXPOSURE|DRAWN_BALANCE_PENCE",
        "TABLE:CRDB2.ACCOUNT_EXPOSURE|UNDRAWN_LIMIT_PENCE",
        "TABLE:CRDB2.ACCOUNT_EXPOSURE|ACCRUED_INT_PENCE",
        "TABLE:CRDB2.ACCOUNT_EXPOSURE|PRODUCT_CD"}
    chain = " ".join(cm.transform_steps)
    assert "COMPUTE AXC-DRAWN-GBP" in chain and "SEARCH ALL WS-CCF-ENTRY" in chain


def test_cobol_pd_evaluate_bucketing_lineage(result):
    """PD bucketing (EVALUATE on delinquency + bureau score) links both drivers
    to the bucketed RISK STATUS and PD RATE feed columns."""
    drivers = {"TABLE:CRDB2.ACCOUNT_EXPOSURE|DAYS_PAST_DUE",
               "TABLE:CRDB2.ACCOUNT_EXPOSURE|BUREAU_SCORE"}
    for fld in ("AXD-PD-RATE", "AXD-RISK-STATUS"):
        cm = _feed_mapping(result, fld)
        assert set(cm.source_columns) == drivers
        assert "EVALUATE bucketing" in " ".join(cm.transform_steps)


def test_cobol_lgd_search_and_giving_lineage(result):
    """LGD base rate comes from a SEARCH ALL on the collateral code; final LGD
    scales it by the macro adjustment; net exposure uses SUBTRACT ... GIVING."""
    cm_lgd = _feed_mapping(result, "AXD-FINAL-LGD")
    assert set(cm_lgd.source_columns) == {
        "TABLE:CRDB2.ACCOUNT_EXPOSURE|COLLATERAL_CODE",
        "TABLE:CRDB2.ACCOUNT_EXPOSURE|MACRO_ADJ_BPS"}
    assert "SEARCH ALL WS-LGD-ENTRY" in " ".join(cm_lgd.transform_steps)
    cm_net = _feed_mapping(result, "AXD-NET-EXPOSURE-GBP")
    assert set(cm_net.source_columns) == {
        "TABLE:CRDB2.ACCOUNT_EXPOSURE|BALANCE_PENCE",
        "TABLE:CRDB2.ACCOUNT_EXPOSURE|COLLATERAL_PENCE"}
    assert "GIVING" in " ".join(cm_net.transform_steps)


def test_cobol_expected_loss_composes_all_risk_drivers(result):
    """Expected Loss = EAD * PD * LGD composes every upstream risk driver, so the
    feed column traces back to all eight DB2 source columns."""
    cm = _feed_mapping(result, "AXD-EXPECTED-LOSS-GBP")
    assert set(cm.source_columns) == {
        "TABLE:CRDB2.ACCOUNT_EXPOSURE|DRAWN_BALANCE_PENCE",
        "TABLE:CRDB2.ACCOUNT_EXPOSURE|UNDRAWN_LIMIT_PENCE",
        "TABLE:CRDB2.ACCOUNT_EXPOSURE|ACCRUED_INT_PENCE",
        "TABLE:CRDB2.ACCOUNT_EXPOSURE|PRODUCT_CD",
        "TABLE:CRDB2.ACCOUNT_EXPOSURE|DAYS_PAST_DUE",
        "TABLE:CRDB2.ACCOUNT_EXPOSURE|BUREAU_SCORE",
        "TABLE:CRDB2.ACCOUNT_EXPOSURE|COLLATERAL_CODE",
        "TABLE:CRDB2.ACCOUNT_EXPOSURE|MACRO_ADJ_BPS"}


def test_plsql_window_function_and_case_captured(result):
    """The mart's portfolio analytics (window functions + CASE) render their
    full expression text on the column edges and resolve their sources."""
    edge = _edge(result, "PROGRAM:CR_MART.PRC_BUILD_CREDIT_RISK_MODEL",
                 EdgeType.WRITES_TO, "TABLE:CR_MART.CREDIT_RISK_MODEL")
    assert edge is not None
    cm_rank = _mapping(edge, "BRANCH_EL_RANK")
    assert "RANK() OVER" in cm_rank.transformation
    cm_tot = _mapping(edge, "CUSTOMER_TOTAL_EAD_GBP")
    assert "SUM(x.EAD_GBP) OVER" in cm_tot.transformation
    assert "TABLE:CR_MART.TMP_ACCOUNT_EXPOSURE|EAD_GBP" in cm_tot.source_columns
    cm_band = _mapping(edge, "EXPOSURE_RISK_BAND")
    assert "CASE" in cm_band.transformation
