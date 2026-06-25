      *================================================================
      * PROGRAM  : CACXDQA  (Data Quality)
      * SYSTEM   : Credit Risk Data Mart - Accounts/Exposure pipeline
      * PURPOSE  : Quality assurance over the processed exposure feed.
      *            Reads CRDM.ACX.PROCESSED.FEED and routes records to:
      *              1. Valid  -> CRDM.ACX.VALID.DAT  (.dat)
      *              2. Error  -> CRDM.ACX.ERROR
      *              3. Metrics-> CRDM.ACX.METRICS
      *            FCA rule: a blank account number or a utilisation
      *            over 150% (data integrity breach) is rejected.
      *
      * CALLED BY: JCL CRJACXQA STEP010 (EXEC PGM=CACXDQA)
      *================================================================
       IDENTIFICATION DIVISION.
       PROGRAM-ID. CACXDQA.
       AUTHOR. CREDIT-RISK-BATCH.

       ENVIRONMENT DIVISION.
       INPUT-OUTPUT SECTION.
       FILE-CONTROL.
           SELECT FEED-FILE
               ASSIGN TO ACXFEED
               FILE STATUS IS WS-FEED-STATUS.
           SELECT VALID-FILE
               ASSIGN TO ACXVALID
               FILE STATUS IS WS-VALID-STATUS.
           SELECT ERROR-FILE
               ASSIGN TO ACXERROR
               FILE STATUS IS WS-ERROR-STATUS.
           SELECT METRIC-FILE
               ASSIGN TO ACXMETR
               FILE STATUS IS WS-METRIC-STATUS.

       DATA DIVISION.
       FILE SECTION.
       FD  FEED-FILE
           RECORDING MODE F
           RECORD CONTAINS 172 CHARACTERS.
       01  ACX-FEED-REC.
       COPY ACXFEED.

       FD  VALID-FILE
           RECORDING MODE F
           RECORD CONTAINS 172 CHARACTERS.
       01  ACX-VALID-REC.
       COPY ACXFEED.

       FD  ERROR-FILE
           RECORDING MODE F
           RECORD CONTAINS 212 CHARACTERS.
       01  ACX-ERROR-REC.
           05  AXE-RECORD          PIC X(172).
           05  AXE-REJECT-REASON   PIC X(40).

       FD  METRIC-FILE
           RECORDING MODE F
           RECORD CONTAINS 80 CHARACTERS.
       01  ACX-METRIC-REC          PIC X(80).

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
           05  FILLER              PIC X(20) VALUE 'ACX RECORDS READ  :'.
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
           IF AXD-ACCOUNT-NUMBER NOT = SPACES
                   AND AXD-UTILISATION-PCT <= 150.00
               PERFORM WRITE-VALID-PARA
           ELSE
               PERFORM WRITE-ERROR-PARA
           END-IF.

      *================================================================
       WRITE-VALID-PARA.
           MOVE ACX-FEED-REC TO ACX-VALID-REC.
           WRITE ACX-VALID-REC.
           ADD 1 TO WS-VALID-CNT.

      *================================================================
       WRITE-ERROR-PARA.
           MOVE ACX-FEED-REC TO AXE-RECORD.
           MOVE 'MISSING ACCOUNT OR UTILISATION OUT OF RANGE'
                                  TO AXE-REJECT-REASON.
           WRITE ACX-ERROR-REC.
           ADD 1 TO WS-ERROR-CNT.

      *================================================================
       WRITE-METRICS-PARA.
           MOVE WS-READ-CNT  TO WS-MET-READ.
           MOVE WS-VALID-CNT TO WS-MET-VALID.
           MOVE WS-ERROR-CNT TO WS-MET-ERROR.
           MOVE WS-METRIC-LINE TO ACX-METRIC-REC.
           WRITE ACX-METRIC-REC.

      *================================================================
       WRAP-UP-PARA.
           CLOSE FEED-FILE VALID-FILE ERROR-FILE METRIC-FILE.
