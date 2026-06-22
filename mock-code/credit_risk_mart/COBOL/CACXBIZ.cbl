      *================================================================
      * PROGRAM  : CACXBIZ  (Layer 3 - Business Logic)
      * SYSTEM   : Credit Risk Data Mart - Accounts/Exposure pipeline
      * PURPOSE  : Derives the GBP exposure measures from the raw pence
      *            balances supplied by CACXDAO:
      *              AXC-BALANCE-GBP      = AXC-BALANCE-PENCE     / 100
      *              AXC-LIMIT-GBP        = AXC-LIMIT-PENCE       / 100
      *              AXC-COLLATERAL-GBP   = AXC-COLLATERAL-PENCE  / 100
      *              AXC-NET-EXPOSURE-GBP = BALANCE-GBP - COLLATERAL-GBP
      *              AXC-UTILISATION-PCT  = BALANCE-GBP / LIMIT-GBP * 100
      *
      * CALLED BY: CACXCTL (CALL 'CACXBIZ' USING WS-ACX-COMM)
      * CALLS    : CACXDAO (DB2 fetch)
      *================================================================
       IDENTIFICATION DIVISION.
       PROGRAM-ID. CACXBIZ.
       AUTHOR. CREDIT-RISK-BATCH.

       ENVIRONMENT DIVISION.

       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01  WS-ACX-COMM.
       COPY ACXCOMM.

       LINKAGE SECTION.
       01  LK-ACX-COMM.
       COPY ACXCOMM.

       PROCEDURE DIVISION USING LK-ACX-COMM.
      *================================================================
       MAIN-PARA.
           MOVE LK-ACX-COMM TO WS-ACX-COMM.
           CALL 'CACXDAO' USING WS-ACX-COMM.
           IF AXC-RETURN-CODE = ZERO
               PERFORM DERIVE-EXPOSURE-PARA
           END-IF.
           MOVE WS-ACX-COMM TO LK-ACX-COMM.
           GOBACK.

      *================================================================
       DERIVE-EXPOSURE-PARA.
           COMPUTE AXC-BALANCE-GBP    = AXC-BALANCE-PENCE    / 100.
           COMPUTE AXC-LIMIT-GBP      = AXC-LIMIT-PENCE      / 100.
           COMPUTE AXC-COLLATERAL-GBP = AXC-COLLATERAL-PENCE / 100.
           COMPUTE AXC-NET-EXPOSURE-GBP =
               AXC-BALANCE-GBP - AXC-COLLATERAL-GBP.
           IF AXC-LIMIT-GBP > ZERO
               COMPUTE AXC-UTILISATION-PCT ROUNDED =
                   AXC-BALANCE-GBP / AXC-LIMIT-GBP * 100
           ELSE
               MOVE ZERO TO AXC-UTILISATION-PCT
           END-IF.
