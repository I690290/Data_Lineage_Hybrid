"""Coverage telemetry: unsupported-but-detected statements must fail loud."""

import textwrap
from pathlib import Path

import pytest

from parsers import ParserOrchestrator
from parsers.base import EdgeType
from parsers.cobol_parser import CobolParser
from parsers.jcl_parser import JclParser
from parsers.plsql_parser import PlsqlParser

SOURCE = Path(__file__).resolve().parent.parent / "mock-code"


def _cobol(tmp_path: Path, body: str) -> Path:
    """Wrap procedure-division statements in a minimal fixed-format program."""
    src = [
        "       IDENTIFICATION DIVISION.",
        "       PROGRAM-ID. TESTPGM.",
        "       PROCEDURE DIVISION.",
        "       MAIN-PARA.",
    ] + [f"           {line}" for line in textwrap.dedent(body).strip().splitlines()]
    path = tmp_path / "TESTPGM.cbl"
    path.write_text("\n".join(src) + "\n")
    return path


def test_corpus_self_reports_unmapped_constructs():
    """Estate-wide coverage telemetry is exactly the known, documented gaps:

      - 3x COBOL_MOVE: reference-modified CURRENT-DATE(1:8) moves in the
        three MI4014 extract/XML programs.
      - 1x JCL_SORT_CONTROL: the credit_risk_mart CRJACX01 DFSORT JOINKEYS
        whose enriched output (CRDM.ACX.ENRICHED.UNLOAD) has no recoverable
        record layout, so the join cannot be mapped to columns.

    No other movement-shaped statement is silently dropped."""
    result = ParserOrchestrator().parse_tree(SOURCE)
    assert len(result.unparsed) == 4

    moves = [u for u in result.unparsed if u.statement_type == "COBOL_MOVE"]
    assert len(moves) == 3
    assert all("CURRENT-DATE(1:8)" in u.snippet for u in moves)
    assert {u.program for u in moves} == {"CRDB2EXT", "CRTXNEXT", "CRXMLGEN"}

    sort_gaps = [u for u in result.unparsed
                 if u.statement_type == "JCL_SORT_CONTROL"]
    assert len(sort_gaps) == 1
    assert "no record layout" in sort_gaps[0].reason


@pytest.mark.parametrize("statement,expected_type", [
    ("CALL 'SUBPGM1' USING WS-AREA.", "COBOL_CALL"),
    ("UNSTRING WS-IN DELIMITED BY ',' INTO WS-A WS-B.", "COBOL_UNSTRING"),
    ("MOVE CORRESPONDING WS-GRP-A TO WS-GRP-B.", "COBOL_MOVE_CORRESPONDING"),
    ("ADD WS-A WS-B GIVING WS-TOTAL.", "COBOL_ARITHMETIC_GIVING"),
    ("WRITE OUT-REC FROM WS-WORK-REC.", "COBOL_WRITE_FROM"),
    ("MOVE WS-FULL(1:8) TO WS-PART.", "COBOL_MOVE"),
])
def test_cobol_detectors(tmp_path, statement, expected_type):
    result = CobolParser().parse(_cobol(tmp_path, statement))
    assert expected_type in {u.statement_type for u in result.unparsed}, \
        f"{statement!r} should be flagged as {expected_type}"


def test_cobol_unhandled_exec_sql_verb(tmp_path):
    result = CobolParser().parse(_cobol(tmp_path, """\
        EXEC SQL
            UPDATE CRISK.ACCOUNTS SET BAL = :WS-BAL
            WHERE ID = :WS-ID
        END-EXEC.
    """))
    types = {u.statement_type for u in result.unparsed}
    assert "EXEC_SQL_UPDATE" in types


def test_cobol_plain_moves_not_flagged(tmp_path):
    """Mapped MOVEs and literal MOVEs must produce zero noise."""
    result = CobolParser().parse(_cobol(tmp_path, """\
        MOVE WS-A TO WS-B.
        MOVE 'Y' TO WS-EOF-FLAG.
        MOVE SPACES TO WS-OUT.
    """))
    assert result.unparsed == []


def _cobol_program(tmp_path: Path, name: str, body: str) -> Path:
    """Write a whole COBOL program in fixed format (code in area A/B at col 8+;
    `_normalize` keeps only columns 8-72)."""
    lines = textwrap.dedent(body).strip().splitlines()
    path = tmp_path / f"{name}.cbl"
    path.write_text("\n".join("       " + ln for ln in lines) + "\n")
    return path


def test_group_move_chains_through_ws_intermediary(tmp_path):
    """Generic whole-record move: a record copied through a WORKING-STORAGE
    intermediary (`READ INTO WS-REC` then `MOVE WS-REC TO OUT-REC`) must
    resolve transitively, field-by-field, back to the input file - even though
    the records use different field names (paired by byte offset, not name).
    The narrow FD->FD-only handler could not see this; the generic one must."""
    prog = _cobol_program(tmp_path, "GMWS", """
        IDENTIFICATION DIVISION.
        PROGRAM-ID. GMWS.
        ENVIRONMENT DIVISION.
        INPUT-OUTPUT SECTION.
        FILE-CONTROL.
            SELECT IN-FILE  ASSIGN TO INDD.
            SELECT OUT-FILE ASSIGN TO OUTDD.
        DATA DIVISION.
        FILE SECTION.
        FD  IN-FILE.
        01  IN-REC.
            05  IN-A   PIC X(5).
            05  IN-B   PIC X(3).
        FD  OUT-FILE.
        01  OUT-REC.
            05  OUT-A  PIC X(5).
            05  OUT-B  PIC X(3).
        WORKING-STORAGE SECTION.
        01  WS-REC.
            05  WS-A   PIC X(5).
            05  WS-B   PIC X(3).
        PROCEDURE DIVISION.
        MAIN-PARA.
            OPEN INPUT IN-FILE.
            OPEN OUTPUT OUT-FILE.
            READ IN-FILE INTO WS-REC.
            MOVE WS-REC TO OUT-REC.
            WRITE OUT-REC.
    """)
    result = CobolParser().parse(prog)
    edge = next(e for e in result.edges
                if e.edge_type == EdgeType.WRITES_TO and e.target_id == "FILE:OUTDD")
    cols = {m.target_column.rsplit("|", 1)[-1]: m.source_columns
            for m in edge.column_mappings}
    # OUT-A/OUT-B trace back through WS-REC to the input file (record-level READ)
    assert cols.get("OUT-A") == ["FILE:INDD|*"]
    assert cols.get("OUT-B") == ["FILE:INDD|*"]
    assert not [u for u in result.unparsed if u.statement_type == "COBOL_GROUP_MOVE"]


def test_unalignable_group_move_flagged_not_dropped(tmp_path):
    """A group move whose records cannot be aligned deterministically (OCCURS
    breaks the byte layout and the field counts differ) must surface as
    COVERAGE telemetry - never silently dropped, never guessed."""
    prog = _cobol_program(tmp_path, "GMBAD", """
        IDENTIFICATION DIVISION.
        PROGRAM-ID. GMBAD.
        DATA DIVISION.
        WORKING-STORAGE SECTION.
        01  SRC-REC.
            05  S-A    PIC X(4).
            05  S-B    PIC X(4).
            05  S-C    REDEFINES S-B PIC X(4).
        01  DST-REC.
            05  D-A    PIC X(4).
            05  D-B    PIC X(4).
        PROCEDURE DIVISION.
        MAIN-PARA.
            MOVE SRC-REC TO DST-REC.
    """)
    result = CobolParser().parse(prog)
    flagged = [u for u in result.unparsed if u.statement_type == "COBOL_GROUP_MOVE"]
    assert len(flagged) == 1 and "SRC-REC" in flagged[0].snippet


def test_jcl_detectors(tmp_path):
    path = tmp_path / "TESTJOB.jcl"
    path.write_text("\n".join([
        "//TESTJOB  JOB (ACCT),'TEST',CLASS=A",
        "//STEP010  EXEC DAILYPRC",                            # cataloged proc
        "//STEP020  EXEC PGM=MYPGM",
        "//IN1      DD DSN=*.STEP010.SYSUT2,DISP=SHR",         # referback
        "//IN2      DD DSN=PROD.DAILY.GDG(+1),DISP=SHR",       # GDG
        "//IN3      DD DSN=PROD.CTLLIB(CARDS),DISP=SHR",       # PDS member
    ]) + "\n")
    result = JclParser().parse(path)
    types = sorted(u.statement_type for u in result.unparsed)
    assert types == ["JCL_GDG", "JCL_PDS_MEMBER", "JCL_PROC", "JCL_REFERBACK"]


def test_sort_control_cards_without_layout_flagged(tmp_path):
    """A SORT step whose cards are movement-shaped but unresolvable (no
    copybook layout for the datasets) must land in telemetry, not vanish."""
    (tmp_path / "SORTJOB.jcl").write_text("\n".join([
        "//SORTJOB  JOB (ACCT),'TEST',CLASS=A",
        "//STEP010  EXEC PGM=SORT",
        "//SORTIN   DD DSN=PROD.UNKNOWN.INPUT,DISP=SHR",
        "//SORTOUT  DD DSN=PROD.UNKNOWN.OUTPUT,DISP=(NEW,CATLG)",
        "//SYSIN    DD *",
        " SORT FIELDS=(1,10,CH,A)",
        "/*",
    ]) + "\n")
    result = ParserOrchestrator().parse_tree(tmp_path)
    flagged = [u for u in result.unparsed
               if u.statement_type == "JCL_SORT_CONTROL"]
    assert len(flagged) == 1
    assert "no record layout" in flagged[0].reason


def test_plsql_cte_insert_flagged(tmp_path):
    path = tmp_path / "cte_load.sql"
    path.write_text("""
        CREATE OR REPLACE PROCEDURE LOAD_X AS
        BEGIN
            INSERT INTO TARGET_T
            WITH RECENT AS (SELECT * FROM SRC_T WHERE DT > SYSDATE - 1)
            SELECT * FROM RECENT;
            COMMIT;
        END;
        /
    """)
    result = PlsqlParser().parse(path)
    assert any(u.statement_type == "SQL_DML_UNMAPPED" and "TARGET_T" in u.snippet
               for u in result.unparsed)


def test_plsql_mapped_dml_not_flagged():
    """Every DML in the MI4014 SQL files is mapped -> zero SQL telemetry."""
    for f in (SOURCE / "SQL").glob("*.sql"):
        result = PlsqlParser().parse(f)
        assert result.unparsed == [], \
            f"{f.name}: {[u.snippet for u in result.unparsed]}"
