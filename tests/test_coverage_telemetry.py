"""Coverage telemetry: unsupported-but-detected statements must fail loud."""

import textwrap
from pathlib import Path

import pytest

from parsers import ParserOrchestrator
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


def test_mi4014_corpus_self_reports_unmapped_moves():
    """The known gap: reference-modified CURRENT-DATE moves in all 3 programs."""
    result = ParserOrchestrator().parse_tree(SOURCE)
    assert len(result.unparsed) == 3
    assert {u.statement_type for u in result.unparsed} == {"COBOL_MOVE"}
    assert all("CURRENT-DATE(1:8)" in u.snippet for u in result.unparsed)
    assert {u.program for u in result.unparsed} == \
        {"CRDB2EXT", "CRTXNEXT", "CRXMLGEN"}


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
