      *================================================================
      * PROGRAM  : CEMPDQA  (Data Quality)
      * SYSTEM   : Credit Risk Data Mart - Employees (RM) pipeline
      * PURPOSE  : Quality assurance over the processed RM feed.
      *            Reads CRDM.EMP.PROCESSED.FEED and routes records to:
      *              1. Valid  -> CRDM.EMP.VALID.DAT  (.dat)
      *              2. Error  -> CRDM.EMP.ERROR
      *              3. Metrics-> CRDM.EMP.METRICS
      *            FCA rule: a blank employee id or a non-positive
      *            portfolio value is rejected.
      *
      * CALLED BY: JCL CRJEMPQA STEP010 (EXEC PGM=CEMPDQA)
      *================================================================
       IDENTIFICATION DIVISION.
       PROGRAM-ID. CEMPDQA.
       AUTHOR. CREDIT-RISK-BATCH.

       ENVIRONMENT DIVISION.
       INPUT-OUTPUT SECTION.
       FILE-CONTROL.
           SELECT FEED-FILE
               ASSIGN TO EMPFEED
               FILE STATUS IS WS-FEED-STATUS.
           SELECT VALID-FILE
               ASSIGN TO EMPVALID
               FILE STATUS IS WS-VALID-STATUS.
           SELECT ERROR-FILE
               ASSIGN TO EMPERROR
               FILE STATUS IS WS-ERROR-STATUS.
           SELECT METRIC-FILE
               ASSIGN TO EMPMETR
               FILE STATUS IS WS-METRIC-STATUS.

       DATA DIVISION.
       FILE SECTION.
       FD  FEED-FILE
           RECORDING MODE F
           RECORD CONTAINS 85 CHARACTERS.
       01  EMP-FEED-REC.
       COPY EMPFEED.

       FD  VALID-FILE
           RECORDING MODE F
           RECORD CONTAINS 85 CHARACTERS.
       01  EMP-VALID-REC.
       COPY EMPFEED.

       FD  ERROR-FILE
           RECORDING MODE F
           RECORD CONTAINS 125 CHARACTERS.
       01  EMP-ERROR-REC.
           05  EME-RECORD          PIC X(85).
           05  EME-REJECT-REASON   PIC X(40).

       FD  METRIC-FILE
           RECORDING MODE F
           RECORD CONTAINS 80 CHARACTERS.
       01  EMP-METRIC-REC          PIC X(80).

       WORKING-STORAGE SECTION.
       01  WS-FILE-STATUS.
           05  WS-FEED-STATUS      PIC XX VALUE SPACES.
           05  WS-VALID-STATUS     PIC XX VALUE SPACES.
           05  WS-ERROR-STATUS     PIC XX VALUE SPACES.
           05  WS-METRIC-STATUS    PIC XX VALUE SPACES.

       01  WS-FLAGS.
           05  WS-EOF-FLAG         PIC X VALUE 'N'.
               88  END-OF-FEED     VALUE 'Y'.

       01  WS-COUNTERS.
           05  WS-READ-CNT         PIC 9(9) VALUE ZEROS.
           05  WS-VALID-CNT        PIC 9(9) VALUE ZEROS.
           05  WS-ERROR-CNT        PIC 9(9) VALUE ZEROS.

       01  WS-METRIC-LINE.
           05  FILLER              PIC X(20) VALUE 'EMP RECORDS READ  :'.
           05  WS-MET-READ         PIC ZZZ,ZZZ,ZZ9.
           05  FILLER              PIC X(20) VALUE ' VALID:'.
           05  WS-MET-VALID        PIC ZZZ,ZZZ,ZZ9.
           05  FILLER              PIC X(08) VALUE ' ERROR:'.
           05  WS-MET-ERROR        PIC ZZZ,ZZZ,ZZ9.

       PROCEDURE DIVISION.
      *================================================================
       MAIN-PARA.
           PERFORM INIT-PARA.
           PERFORM PROCESS-PARA UNTIL END-OF-FEED.
           PERFORM WRITE-METRICS-PARA.
           PERFORM WRAP-UP-PARA.
           STOP RUN.

      *================================================================
       INIT-PARA.
           OPEN INPUT  FEED-FILE.
           OPEN OUTPUT VALID-FILE.
           OPEN OUTPUT ERROR-FILE.
           OPEN OUTPUT METRIC-FILE.

      *================================================================
       PROCESS-PARA.
           READ FEED-FILE
               AT END MOVE 'Y' TO WS-EOF-FLAG
               NOT AT END PERFORM VALIDATE-PARA
           END-READ.

      *================================================================
       VALIDATE-PARA.
           ADD 1 TO WS-READ-CNT.
           IF EMD-EMP-ID NOT = SPACES AND EMD-PORTFOLIO-GBP > ZERO
               PERFORM WRITE-VALID-PARA
           ELSE
               PERFORM WRITE-ERROR-PARA
           END-IF.

      *================================================================
       WRITE-VALID-PARA.
           MOVE EMP-FEED-REC TO EMP-VALID-REC.
           WRITE EMP-VALID-REC.
           ADD 1 TO WS-VALID-CNT.

      *================================================================
       WRITE-ERROR-PARA.
           MOVE EMP-FEED-REC TO EME-RECORD.
           MOVE 'MISSING EMP ID OR NON-POSITIVE PORTFOLIO'
                                  TO EME-REJECT-REASON.
           WRITE EMP-ERROR-REC.
           ADD 1 TO WS-ERROR-CNT.

      *================================================================
       WRITE-METRICS-PARA.
           MOVE WS-READ-CNT  TO WS-MET-READ.
           MOVE WS-VALID-CNT TO WS-MET-VALID.
           MOVE WS-ERROR-CNT TO WS-MET-ERROR.
           MOVE WS-METRIC-LINE TO EMP-METRIC-REC.
           WRITE EMP-METRIC-REC.

      *================================================================
       WRAP-UP-PARA.
           CLOSE FEED-FILE VALID-FILE ERROR-FILE METRIC-FILE.
