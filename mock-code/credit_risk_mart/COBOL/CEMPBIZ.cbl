      *================================================================
      * PROGRAM  : CEMPBIZ  (Layer 3 - Business Logic)
      * SYSTEM   : Credit Risk Data Mart - Employees (RM) pipeline
      * PURPOSE  : Converts the relationship-manager portfolio value,
      *            stored on DB2 in thousands of GBP, into an absolute
      *            GBP figure used by the data mart:
      *              EMC-PORTFOLIO-GBP = EMC-PORTFOLIO-THOU * 1000
      *
      * CALLED BY: CEMPCTL (CALL 'CEMPBIZ' USING WS-EMP-COMM)
      * CALLS    : CEMPDAO (DB2 fetch)
      *================================================================
       IDENTIFICATION DIVISION.
       PROGRAM-ID. CEMPBIZ.
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
           CALL 'CEMPDAO' USING WS-EMP-COMM.
           IF EMC-RETURN-CODE = ZERO
               PERFORM DERIVE-PORTFOLIO-PARA
           END-IF.
           MOVE WS-EMP-COMM TO LK-EMP-COMM.
           GOBACK.

      *================================================================
       DERIVE-PORTFOLIO-PARA.
           COMPUTE EMC-PORTFOLIO-GBP = EMC-PORTFOLIO-THOU * 1000.
