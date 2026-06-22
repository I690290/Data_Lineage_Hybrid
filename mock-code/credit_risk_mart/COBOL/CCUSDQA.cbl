      *================================================================
      * PROGRAM  : CCUSDQA  (Data Quality)
      * SYSTEM   : Credit Risk Data Mart - Customers pipeline
      * PURPOSE  : Quality assurance over the processed customer feed.
      *            Reads CRDM.CUS.PROCESSED.FEED and routes records to:
      *              1. Valid  -> CRDM.CUS.VALID.DAT  (.dat)
      *              2. Error  -> CRDM.CUS.ERROR
      *              3. Metrics-> CRDM.CUS.METRICS
      *            FCA rule: a blank customer id or an unmapped risk
      *            tier (space) is rejected.
      *
      * CALLED BY: JCL CRJCUSQA STEP010 (EXEC PGM=CCUSDQA)
      *================================================================
       IDENTIFICATION DIVISION.
       PROGRAM-ID. CCUSDQA.
       AUTHOR. CREDIT-RISK-BATCH.

       ENVIRONMENT DIVISION.
       INPUT-OUTPUT SECTION.
       FILE-CONTROL.
           SELECT FEED-FILE
               ASSIGN TO CUSFEED
               FILE STATUS IS WS-FEED-STATUS.
           SELECT VALID-FILE
               ASSIGN TO CUSVALID
               FILE STATUS IS WS-VALID-STATUS.
           SELECT ERROR-FILE
               ASSIGN TO CUSERROR
               FILE STATUS IS WS-ERROR-STATUS.
           SELECT METRIC-FILE
               ASSIGN TO CUSMETR
               FILE STATUS IS WS-METRIC-STATUS.

       DATA DIVISION.
       FILE SECTION.
       FD  FEED-FILE
           RECORDING MODE F
           RECORD CONTAINS 86 CHARACTERS.
       01  CUS-FEED-REC.
       COPY CUSFEED.

       FD  VALID-FILE
           RECORDING MODE F
           RECORD CONTAINS 86 CHARACTERS.
       01  CUS-VALID-REC.
       COPY CUSFEED.

       FD  ERROR-FILE
           RECORDING MODE F
           RECORD CONTAINS 126 CHARACTERS.
       01  CUS-ERROR-REC.
           05  CUE-RECORD          PIC X(86).
           05  CUE-REJECT-REASON   PIC X(40).

       FD  METRIC-FILE
           RECORDING MODE F
           RECORD CONTAINS 80 CHARACTERS.
       01  CUS-METRIC-REC          PIC X(80).

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
           05  FILLER              PIC X(20) VALUE 'CUS RECORDS READ  :'.
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
           IF CUD-CUST-ID NOT = SPACES
                   AND CUD-CREDIT-RISK-TIER NOT = SPACE
               PERFORM WRITE-VALID-PARA
           ELSE
               PERFORM WRITE-ERROR-PARA
           END-IF.

      *================================================================
       WRITE-VALID-PARA.
           MOVE CUS-FEED-REC TO CUS-VALID-REC.
           WRITE CUS-VALID-REC.
           ADD 1 TO WS-VALID-CNT.

      *================================================================
       WRITE-ERROR-PARA.
           MOVE CUS-FEED-REC TO CUE-RECORD.
           MOVE 'MISSING CUST ID OR UNMAPPED RISK TIER'
                                  TO CUE-REJECT-REASON.
           WRITE CUS-ERROR-REC.
           ADD 1 TO WS-ERROR-CNT.

      *================================================================
       WRITE-METRICS-PARA.
           MOVE WS-READ-CNT  TO WS-MET-READ.
           MOVE WS-VALID-CNT TO WS-MET-VALID.
           MOVE WS-ERROR-CNT TO WS-MET-ERROR.
           MOVE WS-METRIC-LINE TO CUS-METRIC-REC.
           WRITE CUS-METRIC-REC.

      *================================================================
       WRAP-UP-PARA.
           CLOSE FEED-FILE VALID-FILE ERROR-FILE METRIC-FILE.
