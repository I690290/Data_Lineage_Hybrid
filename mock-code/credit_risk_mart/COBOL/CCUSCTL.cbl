      *================================================================
      * PROGRAM  : CCUSCTL  (Layer 2 - Controller)
      * SYSTEM   : Credit Risk Data Mart - Customers pipeline
      * PURPOSE  : Flow-control layer. Requests the next enriched
      *            customer from CCUSBIZ and applies the batch control
      *            rule that suppresses PEP-flagged customers from the
      *            standard feed (routed to a separate enhanced-due-
      *            diligence stream, RC=8 => skip here).
      *
      * CALLED BY: CCUSDRV (CALL 'CCUSCTL' USING WS-CUS-COMM)
      * CALLS    : CCUSBIZ (business logic)
      *================================================================
       IDENTIFICATION DIVISION.
       PROGRAM-ID. CCUSCTL.
       AUTHOR. CREDIT-RISK-BATCH.

       ENVIRONMENT DIVISION.

       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01  WS-CUS-COMM.
       COPY CUSCOMM.

       LINKAGE SECTION.
       01  LK-CUS-COMM.
       COPY CUSCOMM.

       PROCEDURE DIVISION USING LK-CUS-COMM.
      *================================================================
       MAIN-PARA.
           MOVE LK-CUS-COMM TO WS-CUS-COMM.
           CALL 'CCUSBIZ' USING WS-CUS-COMM.
           IF CUC-RETURN-CODE = ZERO
               PERFORM CONTROL-RULE-PARA
           END-IF.
           MOVE WS-CUS-COMM TO LK-CUS-COMM.
           GOBACK.

      *================================================================
       CONTROL-RULE-PARA.
           IF CUC-PEP-FLAG = 'Y'
               MOVE 8 TO CUC-RETURN-CODE
           END-IF.
