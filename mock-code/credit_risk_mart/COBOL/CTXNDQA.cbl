      *================================================================
      * PROGRAM  : CTXNDQA  (Data Quality)
      * SYSTEM   : Credit Risk Data Mart - Transactions pipeline
      * PURPOSE  : Quality assurance over the processed transaction
      *            feed. Reads CRDM.TXN.PROCESSED.FEED and routes each
      *            record to exactly one of three outputs:
      *              1. Valid records  -> CRDM.TXN.VALID.DAT  (.dat)
      *              2. Error records  -> CRDM.TXN.ERROR
      *              3. Quality metrics-> CRDM.TXN.METRICS
      *            FCA rule: a posting with a non-positive GBP amount or
      *            a blank sort code is rejected.
      *
      * CALLED BY: JCL CRJTXNQA STEP010 (EXEC PGM=CTXNDQA)
      *================================================================
       IDENTIFICATION DIVISION.
       PROGRAM-ID. CTXNDQA.
       AUTHOR. CREDIT-RISK-BATCH.

       ENVIRONMENT DIVISION.
       INPUT-OUTPUT SECTION.
       FILE-CONTROL.
           SELECT FEED-FILE
               ASSIGN TO TXNFEED
               FILE STATUS IS WS-FEED-STATUS.
           SELECT VALID-FILE
               ASSIGN TO TXNVALID
               FILE STATUS IS WS-VALID-STATUS.
           SELECT ERROR-FILE
               ASSIGN TO TXNERROR
               FILE STATUS IS WS-ERROR-STATUS.
           SELECT METRIC-FILE
               ASSIGN TO TXNMETR
               FILE STATUS IS WS-METRIC-STATUS.

       DATA DIVISION.
       FILE SECTION.
       FD  FEED-FILE
           RECORDING MODE F
           RECORD CONTAINS 80 CHARACTERS.
       01  TXN-FEED-REC.
       COPY TXNFEED.

       FD  VALID-FILE
           RECORDING MODE F
           RECORD CONTAINS 80 CHARACTERS.
       01  TXN-VALID-REC.
       COPY TXNFEED.

       FD  ERROR-FILE
           RECORDING MODE F
           RECORD CONTAINS 120 CHARACTERS.
       01  TXN-ERROR-REC.
           05  TXE-RECORD          PIC X(80).
           05  TXE-REJECT-REASON   PIC X(40).

       FD  METRIC-FILE
           RECORDING MODE F
           RECORD CONTAINS 80 CHARACTERS.
       01  TXN-METRIC-REC          PIC X(80).

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
           05  FILLER              PIC X(20) VALUE 'TXN RECORDS READ  :'.
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
           IF TXD-AMOUNT-GBP > ZERO AND TXD-SORT-CODE NOT = SPACES
               PERFORM WRITE-VALID-PARA
           ELSE
               PERFORM WRITE-ERROR-PARA
           END-IF.

      *================================================================
       WRITE-VALID-PARA.
           MOVE TXN-FEED-REC TO TXN-VALID-REC.
           WRITE TXN-VALID-REC.
           ADD 1 TO WS-VALID-CNT.

      *================================================================
       WRITE-ERROR-PARA.
           MOVE TXN-FEED-REC TO TXE-RECORD.
           MOVE 'INVALID AMOUNT OR MISSING SORT CODE'
                                  TO TXE-REJECT-REASON.
           WRITE TXN-ERROR-REC.
           ADD 1 TO WS-ERROR-CNT.

      *================================================================
       WRITE-METRICS-PARA.
           MOVE WS-READ-CNT  TO WS-MET-READ.
           MOVE WS-VALID-CNT TO WS-MET-VALID.
           MOVE WS-ERROR-CNT TO WS-MET-ERROR.
           MOVE WS-METRIC-LINE TO TXN-METRIC-REC.
           WRITE TXN-METRIC-REC.

      *================================================================
       WRAP-UP-PARA.
           CLOSE FEED-FILE VALID-FILE ERROR-FILE METRIC-FILE.
