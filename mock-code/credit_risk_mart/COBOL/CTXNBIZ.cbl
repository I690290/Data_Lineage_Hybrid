      *================================================================
      * PROGRAM  : CTXNBIZ  (Layer 3 - Business Logic)
      * SYSTEM   : Credit Risk Data Mart - Transactions pipeline
      * PURPOSE  : Business-rule layer. Requests the next transaction
      *            from the data-access layer (CTXNDAO) and derives the
      *            reporting values used downstream:
      *              - TXC-AMT-GBP    = TXC-AMT-PENCE / 100
      *              - TXC-RISK-WEIGHT from the transaction type code
      *            EOF from CTXNDAO is propagated up through
      *            TXC-RETURN-CODE.
      *
      * CALLED BY: CTXNCTL (CALL 'CTXNBIZ' USING WS-TXN-COMM)
      * CALLS    : CTXNDAO (DB2 fetch)
      *================================================================
       IDENTIFICATION DIVISION.
       PROGRAM-ID. CTXNBIZ.
       AUTHOR. CREDIT-RISK-BATCH.

       ENVIRONMENT DIVISION.

       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01  WS-RISK-WEIGHTS.
           05  WS-RW-CASH      PIC S9(1)V9(4) VALUE 1.5000.
           05  WS-RW-GAMBLING  PIC S9(1)V9(4) VALUE 2.0000.
           05  WS-RW-RETAIL    PIC S9(1)V9(4) VALUE 1.0000.
           05  WS-RW-DEFAULT   PIC S9(1)V9(4) VALUE 1.2500.

       01  WS-TXN-COMM.
       COPY TXNCOMM.

       LINKAGE SECTION.
       01  LK-TXN-COMM.
       COPY TXNCOMM.

       PROCEDURE DIVISION USING LK-TXN-COMM.
      *================================================================
       MAIN-PARA.
      *    Pass the working copy down to the data-access layer
           MOVE LK-TXN-COMM TO WS-TXN-COMM.
           CALL 'CTXNDAO' USING WS-TXN-COMM.
           IF TXC-RETURN-CODE = ZERO
               PERFORM DERIVE-VALUES-PARA
           END-IF.
           MOVE WS-TXN-COMM TO LK-TXN-COMM.
           GOBACK.

      *================================================================
       DERIVE-VALUES-PARA.
      *    Convert pence to GBP and assign a credit-risk weight
           COMPUTE TXC-AMT-GBP = TXC-AMT-PENCE / 100.
           EVALUATE TXC-TXN-TYPE
               WHEN 'CASH'
                   MOVE WS-RW-CASH     TO TXC-RISK-WEIGHT
               WHEN 'GAMB'
                   MOVE WS-RW-GAMBLING TO TXC-RISK-WEIGHT
               WHEN 'RETL'
                   MOVE WS-RW-RETAIL   TO TXC-RISK-WEIGHT
               WHEN OTHER
                   MOVE WS-RW-DEFAULT  TO TXC-RISK-WEIGHT
           END-EVALUATE.
