      *================================================================
      * PROGRAM  : CCUSDAO  (Layer 4 - Data Access)
      * SYSTEM   : Credit Risk Data Mart - Customers pipeline
      * PURPOSE  : DB2 data-access object for CRDB2.CUSTOMER_MASTER.
      *            Fetches the next KYC-cleared customer into the
      *            shared communication area (CUSCOMM). End-of-cursor
      *            is reported via CUC-RETURN-CODE = 4.
      *
      * CALLED BY: CCUSBIZ (CALL 'CCUSDAO' USING WS-CUS-COMM)
      * DB2 TABLES ACCESSED:
      *   READ   : CRDB2.CUSTOMER_MASTER
      *================================================================
       IDENTIFICATION DIVISION.
       PROGRAM-ID. CCUSDAO.
       AUTHOR. CREDIT-RISK-BATCH.

       ENVIRONMENT DIVISION.

       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01  WS-CURSOR-FLAGS.
           05  WS-CURSOR-OPEN      PIC X    VALUE 'N'.
               88  CURSOR-IS-OPEN  VALUE 'Y'.

       COPY DCLCUS.

           EXEC SQL
               INCLUDE SQLCA
           END-EXEC.

       LINKAGE SECTION.
       01  LK-CUS-COMM.
       COPY CUSCOMM.

       PROCEDURE DIVISION USING LK-CUS-COMM.
      *================================================================
       MAIN-PARA.
           IF NOT CURSOR-IS-OPEN
               PERFORM OPEN-CURSOR-PARA
           END-IF.
           PERFORM FETCH-NEXT-PARA.
           GOBACK.

      *================================================================
       OPEN-CURSOR-PARA.
           EXEC SQL
               DECLARE CSR_CUS CURSOR FOR
               SELECT
                   C.CUST_ID,
                   C.TITLE,
                   C.FORENAME,
                   C.SURNAME,
                   VARCHAR_FORMAT(C.DATE_OF_BIRTH, 'YYYY-MM-DD'),
                   C.SORT_CODE,
                   C.KYC_STATUS_CD,
                   C.CR_SCORE_RAW,
                   C.PEP_FLAG,
                   C.RESIDENCY_CD,
                   C.FCA_VULNERABLE_FLAG
               FROM CRDB2.CUSTOMER_MASTER C
               WHERE C.KYC_STATUS_CD IN ('PA', 'EN')
               ORDER BY C.CUST_ID
           END-EXEC.
           EXEC SQL
               OPEN CSR_CUS
           END-EXEC.
           MOVE 'Y' TO WS-CURSOR-OPEN.

      *================================================================
       FETCH-NEXT-PARA.
           EXEC SQL
               FETCH CSR_CUS
               INTO  :HV-CUST-ID,
                     :HV-TITLE,
                     :HV-FORENAME,
                     :HV-SURNAME,
                     :HV-DATE-OF-BIRTH,
                     :HV-SORT-CODE,
                     :HV-KYC-STATUS-CD,
                     :HV-CR-SCORE-RAW,
                     :HV-PEP-FLAG,
                     :HV-RESIDENCY-CD,
                     :HV-FCA-VULN-FLAG
           END-EXEC.
           IF SQLCODE = 0
               PERFORM MAP-ROW-PARA
               MOVE ZERO TO CUC-RETURN-CODE
           ELSE
               PERFORM CLOSE-CURSOR-PARA
               MOVE 4 TO CUC-RETURN-CODE
           END-IF.

      *================================================================
       MAP-ROW-PARA.
           MOVE HV-CUST-ID         TO CUC-CUST-ID.
           MOVE HV-TITLE           TO CUC-TITLE.
           MOVE HV-FORENAME        TO CUC-FORENAME.
           MOVE HV-SURNAME         TO CUC-SURNAME.
           MOVE HV-DATE-OF-BIRTH   TO CUC-DOB.
           MOVE HV-SORT-CODE       TO CUC-SORT-CODE.
           MOVE HV-KYC-STATUS-CD   TO CUC-KYC-STATUS.
           MOVE HV-CR-SCORE-RAW    TO CUC-SCORE-RAW.
           MOVE HV-PEP-FLAG        TO CUC-PEP-FLAG.
           MOVE HV-RESIDENCY-CD    TO CUC-RESIDENCY.
           MOVE HV-FCA-VULN-FLAG   TO CUC-VULN-FLAG.

      *================================================================
       CLOSE-CURSOR-PARA.
           EXEC SQL
               CLOSE CSR_CUS
           END-EXEC.
           MOVE 'N' TO WS-CURSOR-OPEN.
