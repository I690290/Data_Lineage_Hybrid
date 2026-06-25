      *================================================================
      * PROGRAM  : CRRSKMST
      * SYSTEM   : Credit Risk - MI5021 Counterparty Default Risk
      * PURPOSE  : Master driver for the default risk aggregation.
      *            Reads the DSNTIAUL counterparty ratings unload
      *            (RATINGIN), calls CRRSKSUB once per counterparty
      *            to fetch the aggregated DB2 exposure position
      *            (nested CALL - the sub-program performs the actual
      *            DB2 I/O), derives net and PD-weighted exposure and
      *            writes the default risk report (RISKRPT).
      *
      *            The monthly summary INSERT targets a partition
      *            table whose name is assembled at run time
      *            (CRISK.MI5021_RISK_SUMMARY_YYYYMM) - dynamic SQL
      *            that static parsing cannot resolve.
      *
      * CALLED BY: JCL CRJMI521 STEP020
      * CALLS    : CRRSKSUB (DB2 exposure reader)
      *
      * DB2 TABLES ACCESSED:
      *   WRITE  : CRISK.MI5021_RISK_SUMMARY_YYYYMM (dynamic)
      *================================================================
       IDENTIFICATION DIVISION.
       PROGRAM-ID. CRRSKMST.
       AUTHOR. CREDIT-RISK-BATCH.

       ENVIRONMENT DIVISION.
       INPUT-OUTPUT SECTION.
       FILE-CONTROL.
           SELECT RATING-FILE
               ASSIGN TO RATINGIN
               ORGANIZATION IS SEQUENTIAL
               ACCESS MODE  IS SEQUENTIAL
               FILE STATUS  IS WS-RATING-STATUS.
           SELECT REPORT-FILE
               ASSIGN TO RISKRPT
               ORGANIZATION IS SEQUENTIAL
               ACCESS MODE  IS SEQUENTIAL
               FILE STATUS  IS WS-REPORT-STATUS.

       DATA DIVISION.
       FILE SECTION.
       FD  RATING-FILE
           RECORDING MODE F
           BLOCK CONTAINS 0 RECORDS
           RECORD CONTAINS 80 CHARACTERS.
       01  CPTY-RATING-REC.
           05  CRR-COUNTERPARTY-ID     PIC X(15).
           05  CRR-LEGAL-NAME          PIC X(40).
           05  CRR-RATING-GRADE        PIC X(4).
           05  CRR-PD-PERCENT          PIC 9(3)V9(4).
           05  CRR-REVIEW-DATE         PIC X(10).
           05  FILLER                  PIC X(4).

       FD  REPORT-FILE
           RECORDING MODE F
           BLOCK CONTAINS 0 RECORDS
           RECORD CONTAINS 132 CHARACTERS.
       01  RISK-REPORT-REC.
           05  RPT-COUNTERPARTY-ID     PIC X(15).
           05  RPT-LEGAL-NAME          PIC X(40).
           05  RPT-RATING-GRADE        PIC X(4).
           05  RPT-TOTAL-EXPOSURE      PIC S9(13)V99.
           05  RPT-COLLATERAL-VALUE    PIC S9(13)V99.
           05  RPT-NET-EXPOSURE        PIC S9(13)V99.
           05  RPT-WEIGHTED-RISK       PIC S9(13)V99.
           05  RPT-EXPOSURE-CCY        PIC X(3).
           05  RPT-REVIEW-DATE         PIC X(10).

       WORKING-STORAGE SECTION.
       01  WS-FILE-STATUS.
           05  WS-RATING-STATUS    PIC XX   VALUE SPACES.
           05  WS-REPORT-STATUS    PIC XX   VALUE SPACES.

       01  WS-FLAGS.
           05  WS-RATING-EOF       PIC X    VALUE 'N'.
               88  RATING-EOF      VALUE 'Y'.

       01  WS-WORK-AREAS.
           05  WS-NET-EXPOSURE     PIC S9(13)V99 COMP-3.
           05  WS-WEIGHTED-RISK    PIC S9(13)V99 COMP-3.
           05  WS-RUN-YYYYMM       PIC X(6).

       01  WS-DYNAMIC-SQL.
           05  WS-SQL-PREFIX       PIC X(38)
               VALUE 'INSERT INTO CRISK.MI5021_RISK_SUMMARY_'.
           05  WS-SQL-SUFFIX       PIC X(20)
               VALUE ' VALUES (?, ?, ?, ?)'.
           05  WS-SQL-TEXT         PIC X(256).

       01  WS-EXPOSURE-AREA.
       COPY CREXPOSR.

           EXEC SQL
               INCLUDE SQLCA
           END-EXEC.

       PROCEDURE DIVISION.
      *================================================================
       MAIN-PARA.
           PERFORM INIT-PARA.
           PERFORM PROCESS-PARA UNTIL RATING-EOF.
           PERFORM WRAP-UP-PARA.
           STOP RUN.

      *================================================================
       INIT-PARA.
           ACCEPT WS-RUN-YYYYMM FROM DATE.
           OPEN INPUT  RATING-FILE.
           OPEN OUTPUT REPORT-FILE.

      *================================================================
       PROCESS-PARA.
           READ RATING-FILE
               AT END MOVE 'Y' TO WS-RATING-EOF
               NOT AT END PERFORM SCORE-CPTY-PARA
           END-READ.

      *================================================================
       SCORE-CPTY-PARA.
      *    CRRSKSUB owns the DB2 I/O: it fills the shared exposure
      *    communication area from CRISK.COUNTERPARTY_EXPOSURES.
           MOVE CRR-COUNTERPARTY-ID TO EXP-CPTY-ID.
           CALL 'CRRSKSUB' USING WS-EXPOSURE-AREA.
           IF EXP-RETURN-CODE = ZERO
               PERFORM WRITE-REPORT-PARA
               PERFORM INSERT-SUMMARY-PARA
           END-IF.

      *================================================================
       WRITE-REPORT-PARA.
           COMPUTE WS-NET-EXPOSURE =
               EXP-TOTAL-EXPOSURE - EXP-COLLATERAL-VALUE.
           COMPUTE WS-WEIGHTED-RISK =
               WS-NET-EXPOSURE * CRR-PD-PERCENT / 100.
           MOVE CRR-COUNTERPARTY-ID  TO RPT-COUNTERPARTY-ID.
           MOVE CRR-LEGAL-NAME       TO RPT-LEGAL-NAME.
           MOVE CRR-RATING-GRADE     TO RPT-RATING-GRADE.
           MOVE EXP-TOTAL-EXPOSURE   TO RPT-TOTAL-EXPOSURE.
           MOVE EXP-COLLATERAL-VALUE TO RPT-COLLATERAL-VALUE.
           MOVE WS-NET-EXPOSURE      TO RPT-NET-EXPOSURE.
           MOVE WS-WEIGHTED-RISK     TO RPT-WEIGHTED-RISK.
           MOVE EXP-EXPOSURE-CCY     TO RPT-EXPOSURE-CCY.
           MOVE CRR-REVIEW-DATE      TO RPT-REVIEW-DATE.
           WRITE RISK-REPORT-REC.

      *================================================================
       INSERT-SUMMARY-PARA.
      *    Month-partitioned summary table: the physical table name is
      *    only known at run time. Static parsing cannot resolve it -
      *    the construct is flagged for the AI edge-resolution layer.
           STRING WS-SQL-PREFIX WS-RUN-YYYYMM WS-SQL-SUFFIX
                  DELIMITED BY SIZE
                  INTO WS-SQL-TEXT
           END-STRING.
           EXEC SQL
               EXECUTE IMMEDIATE :WS-SQL-TEXT
           END-EXEC.

      *================================================================
       WRAP-UP-PARA.
           CLOSE RATING-FILE.
           CLOSE REPORT-FILE.
