      *================================================================
      * PROGRAM  : CCUSDRV  (Layer 1 - Driver)
      * SYSTEM   : Credit Risk Data Mart - Customers pipeline
      * PURPOSE  : Top-level driver invoked by JCL CRJCUS01 STEP040.
      *            Owns the processed-customer feed file and the batch
      *            loop, calling CCUSCTL which drives the business and
      *            data-access layers, then writing each surviving
      *            customer to the feed (CUSFEED layout).
      *
      * CALLED BY: JCL CRJCUS01 STEP040 (EXEC PGM=CCUSDRV)
      * CALLS    : CCUSCTL (controller)
      * OUTPUT   : CRDM.CUS.PROCESSED.FEED (CUSFEED, FB/LRECL=86)
      *================================================================
       IDENTIFICATION DIVISION.
       PROGRAM-ID. CCUSDRV.
       AUTHOR. CREDIT-RISK-BATCH.

       ENVIRONMENT DIVISION.
       INPUT-OUTPUT SECTION.
       FILE-CONTROL.
           SELECT FEED-FILE
               ASSIGN TO CUSFEED
               ORGANIZATION IS SEQUENTIAL
               ACCESS MODE  IS SEQUENTIAL
               FILE STATUS  IS WS-FEED-STATUS.

       DATA DIVISION.
       FILE SECTION.
       FD  FEED-FILE
           RECORDING MODE F
           BLOCK CONTAINS 0 RECORDS
           RECORD CONTAINS 86 CHARACTERS.
       01  CUS-FEED-REC.
       COPY CUSFEED.

       WORKING-STORAGE SECTION.
       01  WS-FILE-STATUS.
           05  WS-FEED-STATUS      PIC XX   VALUE SPACES.

       01  WS-FLAGS.
           05  WS-EOF-FLAG         PIC X    VALUE 'N'.
               88  END-OF-DATA     VALUE 'Y'.

       01  WS-COUNTERS.
           05  WS-ROWS-WRITTEN     PIC 9(9) VALUE ZEROS.

       01  WS-CUS-COMM.
       COPY CUSCOMM.

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
           CALL 'CCUSCTL' USING WS-CUS-COMM.
           EVALUATE CUC-RETURN-CODE
               WHEN 0
                   PERFORM WRITE-FEED-PARA
               WHEN 8
                   CONTINUE
               WHEN OTHER
                   MOVE 'Y' TO WS-EOF-FLAG
           END-EVALUATE.

      *================================================================
       WRITE-FEED-PARA.
           MOVE CUC-CUST-ID    TO CUD-CUST-ID.
           MOVE CUC-FULL-NAME  TO CUD-FULL-NAME.
           MOVE CUC-DOB        TO CUD-DOB.
           MOVE CUC-SORT-CODE  TO CUD-SORT-CODE.
           MOVE CUC-KYC-STATUS TO CUD-KYC-STATUS.
           MOVE CUC-RISK-TIER  TO CUD-CREDIT-RISK-TIER.
           MOVE CUC-PEP-FLAG   TO CUD-PEP-FLAG.
           MOVE CUC-VULN-FLAG  TO CUD-VULN-FLAG.
           WRITE CUS-FEED-REC.
           ADD 1 TO WS-ROWS-WRITTEN.

      *================================================================
       WRAP-UP-PARA.
           CLOSE FEED-FILE.
           DISPLAY 'CCUSDRV: ROWS WRITTEN=' WS-ROWS-WRITTEN.
