      *================================================================
      * DCLGEN  : DCLTXN
      * TABLE   : CRDB2.CUST_TRANSACTIONS
      * SYSTEM  : Credit Risk Data Mart - Transactions pipeline
      * PURPOSE : DB2 DCLGEN for the daily customer transaction table.
      *           Declared table definition plus the host-variable
      *           structure used by CTXNDAO for cursor FETCH.
      *================================================================
      * DB2 TABLE DEFINITION (CRDB2.CUST_TRANSACTIONS):
      *   TXN_ID               CHAR(18)      NOT NULL
      *   ACCOUNT_NUMBER       CHAR(8)       NOT NULL
      *   SORT_CODE            CHAR(6)       NOT NULL
      *   TXN_AMT_PENCE        DECIMAL(15,0) NOT NULL
      *   TXN_CCY              CHAR(3)       NOT NULL
      *   TXN_TYPE_CD          CHAR(4)       NOT NULL
      *   MERCHANT_CAT_CD      CHAR(4)
      *   POSTING_TS           TIMESTAMP     NOT NULL
      *   FCA_REPORTABLE_FLAG  CHAR(1)       NOT NULL
      *----------------------------------------------------------------
      * HOST VARIABLE STRUCTURE FOR CRDB2.CUST_TRANSACTIONS
      *----------------------------------------------------------------
       01  DCLTXN-CUST-TRANSACTIONS.
           10  HV-TXN-ID             PIC X(18).
           10  HV-ACCOUNT-NUMBER     PIC X(8).
           10  HV-SORT-CODE          PIC X(6).
           10  HV-TXN-AMT-PENCE      PIC S9(15) COMP-3.
           10  HV-TXN-CCY            PIC X(3).
           10  HV-TXN-TYPE-CD        PIC X(4).
           10  HV-MERCHANT-CAT-CD    PIC X(4).
           10  HV-POSTING-DATE       PIC X(10).
           10  HV-FCA-REPORT-FLAG    PIC X(1).
