      *================================================================
      * PROGRAM  : CTXNCTL  (Layer 2 - Controller)
      * SYSTEM   : Credit Risk Data Mart - Transactions pipeline
      * PURPOSE  : Flow-control layer between the driver and the
      *            business logic. Requests the next processed
      *            transaction from CTXNBIZ and applies the batch
      *            control rule that suppresses zero-value postings.
      *            The end-of-data signal from the lower layers is
      *            relayed to the driver via TXC-RETURN-CODE.
      *
      * CALLED BY: CTXNDRV (CALL 'CTXNCTL' USING WS-TXN-COMM)
      * CALLS    : CTXNBIZ (business logic)
      *================================================================
       IDENTIFICATION DIVISION.
       PROGRAM-ID. CTXNCTL.
       AUTHOR. CREDIT-RISK-BATCH.

       ENVIRONMENT DIVISION.

       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01  WS-TXN-COMM.
       COPY TXNCOMM.

       LINKAGE SECTION.
       01  LK-TXN-COMM.
       COPY TXNCOMM.

       PROCEDURE DIVISION USING LK-TXN-COMM.
      *================================================================
       MAIN-PARA.
           MOVE LK-TXN-COMM TO WS-TXN-COMM.
           CALL 'CTXNBIZ' USING WS-TXN-COMM.
           IF TXC-RETURN-CODE = ZERO
               PERFORM CONTROL-RULE-PARA
           END-IF.
           MOVE WS-TXN-COMM TO LK-TXN-COMM.
           GOBACK.

      *================================================================
       CONTROL-RULE-PARA.
      *    Suppress zero-value postings from the feed (RC=8 => skip)
           IF TXC-AMT-GBP = ZERO
               MOVE 8 TO TXC-RETURN-CODE
           END-IF.
