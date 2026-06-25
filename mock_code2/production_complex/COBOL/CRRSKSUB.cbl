      *================================================================
      * PROGRAM  : CRRSKSUB
      * SYSTEM   : Credit Risk - MI5021 Counterparty Default Risk
      * PURPOSE  : DB2 exposure reader sub-program.  Receives the
      *            shared exposure communication area (CREXPOSR) from
      *            CRRSKMST and fills it with the aggregated open
      *            exposure position of one counterparty.
      *
      *            This program owns the DB2 I/O: the calling master
      *            program never touches CRISK.COUNTERPARTY_EXPOSURES
      *            directly (nested-CALL lineage pattern).
      *
      * CALLED BY: CRRSKMST (CALL 'CRRSKSUB' USING WS-EXPOSURE-AREA)
      * CALLS    : None
      *
      * DB2 TABLES ACCESSED:
      *   READ   : CRISK.COUNTERPARTY_EXPOSURES
      *================================================================
       IDENTIFICATION DIVISION.
       PROGRAM-ID. CRRSKSUB.
       AUTHOR. CREDIT-RISK-BATCH.

       ENVIRONMENT DIVISION.

       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01  WS-SUB-FLAGS.
           05  WS-EXPO-FOUND       PIC X    VALUE 'N'.

           EXEC SQL
               INCLUDE SQLCA
           END-EXEC.

       LINKAGE SECTION.
       01  LK-EXPOSURE-AREA.
       COPY CREXPOSR.

       PROCEDURE DIVISION USING LK-EXPOSURE-AREA.
      *================================================================
       MAIN-PARA.
           PERFORM FETCH-EXPOSURE-PARA.
           GOBACK.

      *================================================================
       FETCH-EXPOSURE-PARA.
      *    Aggregate all open exposures for the requested counterparty
           EXEC SQL
               DECLARE CSR_EXPO CURSOR FOR
               SELECT
                   SUM(E.EXPOSURE_AMOUNT),
                   SUM(E.COLLATERAL_VALUE),
                   MAX(E.CURRENCY_CODE)
               FROM CRISK.COUNTERPARTY_EXPOSURES E
               WHERE E.COUNTERPARTY_ID = :EXP-CPTY-ID
                 AND E.EXPOSURE_STATUS = 'OPEN'
           END-EXEC.

           EXEC SQL
               OPEN CSR_EXPO
           END-EXEC.

           EXEC SQL
               FETCH CSR_EXPO
               INTO  :EXP-TOTAL-EXPOSURE,
                     :EXP-COLLATERAL-VALUE,
                     :EXP-EXPOSURE-CCY
           END-EXEC.

           IF SQLCODE = 0
               MOVE ZERO TO EXP-RETURN-CODE
           ELSE
               MOVE 8 TO EXP-RETURN-CODE
           END-IF.

           EXEC SQL
               CLOSE CSR_EXPO
           END-EXEC.
