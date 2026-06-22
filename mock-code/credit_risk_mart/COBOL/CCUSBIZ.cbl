      *================================================================
      * PROGRAM  : CCUSBIZ  (Layer 3 - Business Logic)
      * SYSTEM   : Credit Risk Data Mart - Customers pipeline
      * PURPOSE  : Derives the reporting attributes from the raw
      *            customer columns supplied by CCUSDAO:
      *              - CUC-FULL-NAME : FORENAME + SURNAME (STRING)
      *              - CUC-RISK-TIER : FCA credit risk band A-E mapped
      *                                from the raw bureau score.
      *            Banding: >=800 A, >=700 B, >=600 C, >=500 D, else E.
      *
      * CALLED BY: CCUSCTL (CALL 'CCUSBIZ' USING WS-CUS-COMM)
      * CALLS    : CCUSDAO (DB2 fetch)
      *================================================================
       IDENTIFICATION DIVISION.
       PROGRAM-ID. CCUSBIZ.
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
           CALL 'CCUSDAO' USING WS-CUS-COMM.
           IF CUC-RETURN-CODE = ZERO
               PERFORM BUILD-NAME-PARA
               PERFORM ASSIGN-TIER-PARA
           END-IF.
           MOVE WS-CUS-COMM TO LK-CUS-COMM.
           GOBACK.

      *================================================================
       BUILD-NAME-PARA.
           STRING FUNCTION TRIM(CUC-FORENAME) DELIMITED BY SIZE
                  ' '                         DELIMITED BY SIZE
                  FUNCTION TRIM(CUC-SURNAME)  DELIMITED BY SIZE
                  INTO CUC-FULL-NAME
           END-STRING.

      *================================================================
       ASSIGN-TIER-PARA.
           EVALUATE TRUE
               WHEN CUC-SCORE-RAW >= 800
                   MOVE 'A' TO CUC-RISK-TIER
               WHEN CUC-SCORE-RAW >= 700
                   MOVE 'B' TO CUC-RISK-TIER
               WHEN CUC-SCORE-RAW >= 600
                   MOVE 'C' TO CUC-RISK-TIER
               WHEN CUC-SCORE-RAW >= 500
                   MOVE 'D' TO CUC-RISK-TIER
               WHEN OTHER
                   MOVE 'E' TO CUC-RISK-TIER
           END-EVALUATE.
