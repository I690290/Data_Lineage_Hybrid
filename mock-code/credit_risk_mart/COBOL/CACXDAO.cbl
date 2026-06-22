      *================================================================
      * PROGRAM  : CACXDAO  (Layer 4 - Data Access)
      * SYSTEM   : Credit Risk Data Mart - Accounts/Exposure pipeline
      * PURPOSE  : DB2 data-access object for CRDB2.ACCOUNT_EXPOSURE.
      *            Fetches the next open account exposure into the
      *            shared communication area (ACXCOMM). End-of-cursor
      *            reported via AXC-RETURN-CODE = 4.
      *
      * CALLED BY: CACXBIZ (CALL 'CACXDAO' USING WS-ACX-COMM)
      * DB2 TABLES ACCESSED:
      *   READ   : CRDB2.ACCOUNT_EXPOSURE
      *================================================================
       IDENTIFICATION DIVISION.
       PROGRAM-ID. CACXDAO.
       AUTHOR. CREDIT-RISK-BATCH.

       ENVIRONMENT DIVISION.

       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01  WS-CURSOR-FLAGS.
           05  WS-CURSOR-OPEN      PIC X    VALUE 'N'.
               88  CURSOR-IS-OPEN  VALUE 'Y'.

       COPY DCLACX.

           EXEC SQL
               INCLUDE SQLCA
           END-EXEC.

       LINKAGE SECTION.
       01  LK-ACX-COMM.
       COPY ACXCOMM.

       PROCEDURE DIVISION USING LK-ACX-COMM.
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
               DECLARE CSR_ACX CURSOR FOR
               SELECT
                   A.ACCOUNT_NUMBER,
                   A.SORT_CODE,
                   A.CUST_ID,
                   A.PRODUCT_CD,
                   A.BALANCE_PENCE,
                   A.CREDIT_LIMIT_PENCE,
                   A.COLLATERAL_PENCE,
                   A.ARREARS_DAYS,
                   A.DEFAULT_FLAG
               FROM CRDB2.ACCOUNT_EXPOSURE A
               WHERE A.EXPOSURE_STATUS = 'OPEN'
               ORDER BY A.SORT_CODE, A.ACCOUNT_NUMBER
           END-EXEC.
           EXEC SQL
               OPEN CSR_ACX
           END-EXEC.
           MOVE 'Y' TO WS-CURSOR-OPEN.

      *================================================================
       FETCH-NEXT-PARA.
           EXEC SQL
               FETCH CSR_ACX
               INTO  :HV-ACCOUNT-NUMBER,
                     :HV-SORT-CODE,
                     :HV-CUST-ID,
                     :HV-PRODUCT-CD,
                     :HV-BALANCE-PENCE,
                     :HV-CREDIT-LIMIT-PENCE,
                     :HV-COLLATERAL-PENCE,
                     :HV-ARREARS-DAYS,
                     :HV-DEFAULT-FLAG
           END-EXEC.
           IF SQLCODE = 0
               PERFORM MAP-ROW-PARA
               MOVE ZERO TO AXC-RETURN-CODE
           ELSE
               PERFORM CLOSE-CURSOR-PARA
               MOVE 4 TO AXC-RETURN-CODE
           END-IF.

      *================================================================
       MAP-ROW-PARA.
           MOVE HV-ACCOUNT-NUMBER     TO AXC-ACCOUNT-NUMBER.
           MOVE HV-SORT-CODE          TO AXC-SORT-CODE.
           MOVE HV-CUST-ID            TO AXC-CUST-ID.
           MOVE HV-PRODUCT-CD         TO AXC-PRODUCT.
           MOVE HV-BALANCE-PENCE      TO AXC-BALANCE-PENCE.
           MOVE HV-CREDIT-LIMIT-PENCE TO AXC-LIMIT-PENCE.
           MOVE HV-COLLATERAL-PENCE   TO AXC-COLLATERAL-PENCE.
           MOVE HV-ARREARS-DAYS       TO AXC-ARREARS-DAYS.
           MOVE HV-DEFAULT-FLAG       TO AXC-DEFAULT-FLAG.

      *================================================================
       CLOSE-CURSOR-PARA.
           EXEC SQL
               CLOSE CSR_ACX
           END-EXEC.
           MOVE 'N' TO WS-CURSOR-OPEN.
