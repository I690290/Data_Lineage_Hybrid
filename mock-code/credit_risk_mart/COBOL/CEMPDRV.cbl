      *================================================================
      * PROGRAM  : CEMPDRV  (Layer 1 - Driver)
      * SYSTEM   : Credit Risk Data Mart - Employees (RM) pipeline
      * PURPOSE  : Top-level driver invoked by JCL CRJEMP01 STEP040.
      *            Owns the processed-RM feed file and the batch loop,
      *            calling CEMPCTL which drives the business and data-
      *            access layers, then writing each surviving RM to the
      *            feed (EMPFEED layout).
      *
      * CALLED BY: JCL CRJEMP01 STEP040 (EXEC PGM=CEMPDRV)
      * CALLS    : CEMPCTL (controller)
      * OUTPUT   : CRDM.EMP.PROCESSED.FEED (EMPFEED, FB/LRECL=85)
      *================================================================
       IDENTIFICATION DIVISION.
       PROGRAM-ID. CEMPDRV.
       AUTHOR. CREDIT-RISK-BATCH.

       ENVIRONMENT DIVISION.
       INPUT-OUTPUT SECTION.
       FILE-CONTROL.
           SELECT FEED-FILE
               ASSIGN TO EMPFEED
               ORGANIZATION IS SEQUENTIAL
               ACCESS MODE  IS SEQUENTIAL
               FILE STATUS  IS WS-FEED-STATUS.

       DATA DIVISION.
       FILE SECTION.
       FD  FEED-FILE
           RECORDING MODE F
           BLOCK CONTAINS 0 RECORDS
           RECORD CONTAINS 85 CHARACTERS.
       01  EMP-FEED-REC.
       COPY EMPFEED.

       WORKING-STORAGE SECTION.
       01  WS-FILE-STATUS.
           05  WS-FEED-STATUS      PIC XX   VALUE SPACES.

       01  WS-FLAGS.
           05  WS-EOF-FLAG         PIC X    VALUE 'N'.
               88  END-OF-DATA     VALUE 'Y'.

       01  WS-COUNTERS.
           05  WS-ROWS-WRITTEN     PIC 9(9) VALUE ZEROS.

       01  WS-EMP-COMM.
       COPY EMPCOMM.

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
           CALL 'CEMPCTL' USING WS-EMP-COMM.
           EVALUATE EMC-RETURN-CODE
               WHEN 0
                   PERFORM WRITE-FEED-PARA
               WHEN 8
                   CONTINUE
               WHEN OTHER
                   MOVE 'Y' TO WS-EOF-FLAG
           END-EVALUATE.

      *================================================================
       WRITE-FEED-PARA.
           MOVE EMC-EMP-ID           TO EMD-EMP-ID.
           MOVE EMC-EMP-NAME         TO EMD-EMP-NAME.
           MOVE EMC-BRANCH-SORT-CODE TO EMD-BRANCH-SORT-CODE.
           MOVE EMC-ROLE             TO EMD-ROLE.
           MOVE EMC-RM-TIER          TO EMD-RM-TIER.
           MOVE EMC-PORTFOLIO-GBP    TO EMD-PORTFOLIO-GBP.
           MOVE EMC-FCA-CERT-FLAG    TO EMD-FCA-CERT-FLAG.
           MOVE EMC-START-DATE       TO EMD-START-DATE.
           WRITE EMP-FEED-REC.
           ADD 1 TO WS-ROWS-WRITTEN.

      *================================================================
       WRAP-UP-PARA.
           CLOSE FEED-FILE.
           DISPLAY 'CEMPDRV: ROWS WRITTEN=' WS-ROWS-WRITTEN.
