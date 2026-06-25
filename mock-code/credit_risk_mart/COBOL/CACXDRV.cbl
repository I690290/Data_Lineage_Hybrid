      *================================================================
      * PROGRAM  : CACXDRV  (Layer 1 - Driver)
      * SYSTEM   : Credit Risk Data Mart - Accounts/Exposure pipeline
      * PURPOSE  : Top-level driver invoked by JCL CRJACX01 STEP040.
      *            Owns the processed-exposure feed file and the batch
      *            loop, calling CACXCTL which drives the business and
      *            data-access layers, then writing each surviving
      *            exposure to the feed (ACXFEED layout).
      *
      * CALLED BY: JCL CRJACX01 STEP040 (EXEC PGM=CACXDRV)
      * CALLS    : CACXCTL (controller)
      * OUTPUT   : CRDM.ACX.PROCESSED.FEED (ACXFEED, FB/LRECL=172)
      *================================================================
       IDENTIFICATION DIVISION.
       PROGRAM-ID. CACXDRV.
       AUTHOR. CREDIT-RISK-BATCH.

       ENVIRONMENT DIVISION.
       INPUT-OUTPUT SECTION.
       FILE-CONTROL.
           SELECT FEED-FILE
               ASSIGN TO ACXFEED
               ORGANIZATION IS SEQUENTIAL
               ACCESS MODE  IS SEQUENTIAL
               FILE STATUS  IS WS-FEED-STATUS.

       DATA DIVISION.
       FILE SECTION.
       FD  FEED-FILE
           RECORDING MODE F
           BLOCK CONTAINS 0 RECORDS
           RECORD CONTAINS 172 CHARACTERS.
       01  ACX-FEED-REC.
       COPY ACXFEED.

       WORKING-STORAGE SECTION.
       01  WS-FILE-STATUS.
           05  WS-FEED-STATUS      PIC XX   VALUE SPACES.

       01  WS-FLAGS.
           05  WS-EOF-FLAG         PIC X    VALUE 'N'.
               88  END-OF-DATA     VALUE 'Y'.

       01  WS-COUNTERS.
           05  WS-ROWS-WRITTEN     PIC 9(9) VALUE ZEROS.

       01  WS-ACX-COMM.
       COPY ACXCOMM.

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
           CALL 'CACXCTL' USING WS-ACX-COMM.
           EVALUATE AXC-RETURN-CODE
               WHEN 0
                   PERFORM WRITE-FEED-PARA
               WHEN 8
                   CONTINUE
               WHEN OTHER
                   MOVE 'Y' TO WS-EOF-FLAG
           END-EVALUATE.

      *================================================================
       WRITE-FEED-PARA.
           MOVE AXC-ACCOUNT-NUMBER   TO AXD-ACCOUNT-NUMBER.
           MOVE AXC-SORT-CODE        TO AXD-SORT-CODE.
           MOVE AXC-CUST-ID          TO AXD-CUST-ID.
           MOVE AXC-PRODUCT          TO AXD-PRODUCT.
           MOVE AXC-BALANCE-GBP      TO AXD-BALANCE-GBP.
           MOVE AXC-LIMIT-GBP        TO AXD-LIMIT-GBP.
           MOVE AXC-COLLATERAL-GBP   TO AXD-COLLATERAL-GBP.
           MOVE AXC-NET-EXPOSURE-GBP TO AXD-NET-EXPOSURE-GBP.
           MOVE AXC-UTILISATION-PCT  TO AXD-UTILISATION-PCT.
           MOVE AXC-ARREARS-DAYS     TO AXD-ARREARS-DAYS.
           MOVE AXC-DEFAULT-FLAG     TO AXD-DEFAULT-FLAG.
           MOVE AXC-EAD-GBP          TO AXD-EAD-GBP.
           MOVE AXC-LGD-BASE-RATE    TO AXD-LGD-BASE-RATE.
           MOVE AXC-FINAL-LGD        TO AXD-FINAL-LGD.
           MOVE AXC-PD-RATE          TO AXD-PD-RATE.
           MOVE AXC-RISK-STATUS      TO AXD-RISK-STATUS.
           MOVE AXC-EXPECTED-LOSS-GBP TO AXD-EXPECTED-LOSS-GBP.
           WRITE ACX-FEED-REC.
           ADD 1 TO WS-ROWS-WRITTEN.

      *================================================================
       WRAP-UP-PARA.
           CLOSE FEED-FILE.
           DISPLAY 'CACXDRV: ROWS WRITTEN=' WS-ROWS-WRITTEN.
