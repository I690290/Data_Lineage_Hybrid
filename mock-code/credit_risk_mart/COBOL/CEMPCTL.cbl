      *================================================================
      * PROGRAM  : CEMPCTL  (Layer 2 - Controller)
      * SYSTEM   : Credit Risk Data Mart - Employees (RM) pipeline
      * PURPOSE  : Flow-control layer. Requests the next enriched
      *            relationship manager from CEMPBIZ and applies the
      *            control rule that excludes non-FCA-certified RMs
      *            from the regulated attribution feed (RC=8 => skip).
      *
      * CALLED BY: CEMPDRV (CALL 'CEMPCTL' USING WS-EMP-COMM)
      * CALLS    : CEMPBIZ (business logic)
      *================================================================
       IDENTIFICATION DIVISION.
       PROGRAM-ID. CEMPCTL.
       AUTHOR. CREDIT-RISK-BATCH.

       ENVIRONMENT DIVISION.

       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01  WS-EMP-COMM.
       COPY EMPCOMM.

       LINKAGE SECTION.
       01  LK-EMP-COMM.
       COPY EMPCOMM.

       PROCEDURE DIVISION USING LK-EMP-COMM.
      *================================================================
       MAIN-PARA.
           MOVE LK-EMP-COMM TO WS-EMP-COMM.
           CALL 'CEMPBIZ' USING WS-EMP-COMM.
           IF EMC-RETURN-CODE = ZERO
               PERFORM CONTROL-RULE-PARA
           END-IF.
           MOVE WS-EMP-COMM TO LK-EMP-COMM.
           GOBACK.

      *================================================================
       CONTROL-RULE-PARA.
           IF EMC-FCA-CERT-FLAG NOT = 'Y'
               MOVE 8 TO EMC-RETURN-CODE
           END-IF.
