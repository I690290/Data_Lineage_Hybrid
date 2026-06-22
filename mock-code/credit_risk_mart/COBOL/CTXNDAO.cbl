      *================================================================
      * PROGRAM  : CTXNDAO  (Layer 4 - Data Access)
      * SYSTEM   : Credit Risk Data Mart - Transactions pipeline
      * PURPOSE  : DB2 data-access object. Owns the cursor on
      *            CRDB2.CUST_TRANSACTIONS. On each CALL it fetches the
      *            next eligible transaction row into the shared
      *            communication area (TXNCOMM). The first call opens
      *            the cursor; end-of-cursor is signalled to the caller
      *            through TXC-RETURN-CODE = 4.
      *
      * CALLED BY: CTXNBIZ (CALL 'CTXNDAO' USING WS-TXN-COMM)
      * CALLS    : None
      *
      * DB2 TABLES ACCESSED:
      *   READ   : CRDB2.CUST_TRANSACTIONS
      *================================================================
       IDENTIFICATION DIVISION.
       PROGRAM-ID. CTXNDAO.
       AUTHOR. CREDIT-RISK-BATCH.

       ENVIRONMENT DIVISION.

       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01  WS-CURSOR-FLAGS.
           05  WS-CURSOR-OPEN      PIC X    VALUE 'N'.
               88  CURSOR-IS-OPEN  VALUE 'Y'.

       COPY DCLTXN.

           EXEC SQL
               INCLUDE SQLCA
           END-EXEC.

       LINKAGE SECTION.
       01  LK-TXN-COMM.
       COPY TXNCOMM.

       PROCEDURE DIVISION USING LK-TXN-COMM.
      *================================================================
       MAIN-PARA.
           IF NOT CURSOR-IS-OPEN
               PERFORM OPEN-CURSOR-PARA
           END-IF.
           PERFORM FETCH-NEXT-PARA.
           GOBACK.

      *================================================================
       OPEN-CURSOR-PARA.
      *    Eligible daily transactions for credit risk behaviour
           EXEC SQL
               DECLARE CSR_TXN CURSOR FOR
               SELECT
                   T.TXN_ID,
                   T.ACCOUNT_NUMBER,
                   T.SORT_CODE,
                   T.TXN_AMT_PENCE,
                   T.TXN_CCY,
                   T.TXN_TYPE_CD,
                   T.MERCHANT_CAT_CD,
                   VARCHAR_FORMAT(T.POSTING_TS, 'YYYY-MM-DD'),
                   T.FCA_REPORTABLE_FLAG
               FROM CRDB2.CUST_TRANSACTIONS T
               WHERE T.TXN_STATUS = 'P'
                 AND T.TXN_CCY = 'GBP'
               ORDER BY T.ACCOUNT_NUMBER, T.POSTING_TS
           END-EXEC.
           EXEC SQL
               OPEN CSR_TXN
           END-EXEC.
           MOVE 'Y' TO WS-CURSOR-OPEN.

      *================================================================
       FETCH-NEXT-PARA.
           EXEC SQL
               FETCH CSR_TXN
               INTO  :HV-TXN-ID,
                     :HV-ACCOUNT-NUMBER,
                     :HV-SORT-CODE,
                     :HV-TXN-AMT-PENCE,
                     :HV-TXN-CCY,
                     :HV-TXN-TYPE-CD,
                     :HV-MERCHANT-CAT-CD,
                     :HV-POSTING-DATE,
                     :HV-FCA-REPORT-FLAG
           END-EXEC.
           IF SQLCODE = 0
               PERFORM MAP-ROW-PARA
               MOVE ZERO TO TXC-RETURN-CODE
           ELSE
               PERFORM CLOSE-CURSOR-PARA
               MOVE 4 TO TXC-RETURN-CODE
           END-IF.

      *================================================================
       MAP-ROW-PARA.
      *    Hand the raw DB2 columns to the shared communication area
           MOVE HV-TXN-ID          TO TXC-TXN-ID.
           MOVE HV-ACCOUNT-NUMBER  TO TXC-ACCOUNT-NUMBER.
           MOVE HV-SORT-CODE       TO TXC-SORT-CODE.
           MOVE HV-TXN-AMT-PENCE   TO TXC-AMT-PENCE.
           MOVE HV-TXN-CCY         TO TXC-CCY.
           MOVE HV-TXN-TYPE-CD     TO TXC-TXN-TYPE.
           MOVE HV-MERCHANT-CAT-CD TO TXC-MCC.
           MOVE HV-POSTING-DATE    TO TXC-POSTING-DATE.
           MOVE HV-FCA-REPORT-FLAG TO TXC-FCA-FLAG.

      *================================================================
       CLOSE-CURSOR-PARA.
           EXEC SQL
               CLOSE CSR_TXN
           END-EXEC.
           MOVE 'N' TO WS-CURSOR-OPEN.
