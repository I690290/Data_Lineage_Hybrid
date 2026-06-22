      *================================================================
      * PROGRAM  : CTXNDRV  (Layer 1 - Driver)
      * SYSTEM   : Credit Risk Data Mart - Transactions pipeline
      * PURPOSE  : Top-level driver invoked by JCL CRJTXN01 STEP040.
      *            Owns the processed-transaction feed file and the
      *            batch loop. Repeatedly calls the controller
      *            (CTXNCTL), which drives the business and data-access
      *            layers, and writes each surviving transaction to the
      *            feed (TXNFEED layout). Control returns when the
      *            data-access layer signals end-of-cursor (RC=4).
      *
      * CALLED BY: JCL CRJTXN01 STEP040 (EXEC PGM=CTXNDRV)
      * CALLS    : CTXNCTL (controller)
      * OUTPUT   : CRDM.TXN.PROCESSED.FEED (TXNFEED, FB/LRECL=80)
      *================================================================
       IDENTIFICATION DIVISION.
       PROGRAM-ID. CTXNDRV.
       AUTHOR. CREDIT-RISK-BATCH.

       ENVIRONMENT DIVISION.
       INPUT-OUTPUT SECTION.
       FILE-CONTROL.
           SELECT FEED-FILE
               ASSIGN TO TXNFEED
               ORGANIZATION IS SEQUENTIAL
               ACCESS MODE  IS SEQUENTIAL
               FILE STATUS  IS WS-FEED-STATUS.

       DATA DIVISION.
       FILE SECTION.
       FD  FEED-FILE
           RECORDING MODE F
           BLOCK CONTAINS 0 RECORDS
           RECORD CONTAINS 80 CHARACTERS.
       01  TXN-FEED-REC.
       COPY TXNFEED.

       WORKING-STORAGE SECTION.
       01  WS-FILE-STATUS.
           05  WS-FEED-STATUS      PIC XX   VALUE SPACES.

       01  WS-FLAGS.
           05  WS-EOF-FLAG         PIC X    VALUE 'N'.
               88  END-OF-DATA     VALUE 'Y'.

       01  WS-COUNTERS.
           05  WS-ROWS-READ        PIC 9(9) VALUE ZEROS.
           05  WS-ROWS-WRITTEN     PIC 9(9) VALUE ZEROS.

       01  WS-TXN-COMM.
       COPY TXNCOMM.

       PROCEDURE DIVISION.
      *================================================================
       MAIN-PARA.
           PERFORM INIT-PARA.
           PERFORM PROCESS-PARA UNTIL END-OF-DATA.
           PERFORM WRAP-UP-PARA.
           STOP RUN.

      *================================================================
       INIT-PARA.
           OPEN OUTPUT FEED-FILE.

      *================================================================
       PROCESS-PARA.
           CALL 'CTXNCTL' USING WS-TXN-COMM.
           EVALUATE TXC-RETURN-CODE
               WHEN 0
                   ADD 1 TO WS-ROWS-READ
                   PERFORM WRITE-FEED-PARA
               WHEN 8
                   ADD 1 TO WS-ROWS-READ
               WHEN OTHER
                   MOVE 'Y' TO WS-EOF-FLAG
           END-EVALUATE.

      *================================================================
       WRITE-FEED-PARA.
      *    Map the enriched communication area onto the feed record
           MOVE TXC-TXN-ID         TO TXD-TXN-ID.
           MOVE TXC-ACCOUNT-NUMBER TO TXD-ACCOUNT-NUMBER.
           MOVE TXC-SORT-CODE      TO TXD-SORT-CODE.
           MOVE TXC-TXN-TYPE       TO TXD-TXN-TYPE.
           MOVE TXC-MCC            TO TXD-MCC.
           MOVE TXC-POSTING-DATE   TO TXD-POSTING-DATE.
           MOVE TXC-CCY            TO TXD-CCY.
           MOVE TXC-AMT-GBP        TO TXD-AMOUNT-GBP.
           MOVE TXC-RISK-WEIGHT    TO TXD-RISK-WEIGHT.
           MOVE TXC-FCA-FLAG       TO TXD-FCA-FLAG.
           WRITE TXN-FEED-REC.
           ADD 1 TO WS-ROWS-WRITTEN.

      *================================================================
       WRAP-UP-PARA.
           CLOSE FEED-FILE.
           DISPLAY 'CTXNDRV: ROWS READ=' WS-ROWS-READ
                   ' WRITTEN=' WS-ROWS-WRITTEN.
