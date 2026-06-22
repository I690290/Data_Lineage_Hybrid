      *================================================================
      * PROGRAM  : CACXCTL  (Layer 2 - Controller)
      * SYSTEM   : Credit Risk Data Mart - Accounts/Exposure pipeline
      * PURPOSE  : Flow-control layer. Requests the next enriched
      *            account exposure from CACXBIZ and applies the
      *            control rule that suppresses fully collateralised
      *            zero-net-exposure accounts (RC=8 => skip).
      *
      * CALLED BY: CACXDRV (CALL 'CACXCTL' USING WS-ACX-COMM)
      * CALLS    : CACXBIZ (business logic)
      *================================================================
       IDENTIFICATION DIVISION.
       PROGRAM-ID. CACXCTL.
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
           CALL 'CACXBIZ' USING WS-ACX-COMM.
           IF AXC-RETURN-CODE = ZERO
               PERFORM CONTROL-RULE-PARA
           END-IF.
           MOVE WS-ACX-COMM TO LK-ACX-COMM.
           GOBACK.

      *================================================================
       CONTROL-RULE-PARA.
           IF AXC-NET-EXPOSURE-GBP <= ZERO AND AXC-DEFAULT-FLAG = 'N'
               MOVE 8 TO AXC-RETURN-CODE
           END-IF.
