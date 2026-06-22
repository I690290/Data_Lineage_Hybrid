      *================================================================
      * DCLGEN  : DCLACX
      * TABLE   : CRDB2.ACCOUNT_EXPOSURE
      * SYSTEM  : Credit Risk Data Mart - Accounts/Exposure pipeline
      * PURPOSE : DB2 DCLGEN for the account exposure table. Declared
      *           table definition plus the host-variable structure
      *           used by CACXDAO for cursor FETCH.
      *================================================================
      * DB2 TABLE DEFINITION (CRDB2.ACCOUNT_EXPOSURE):
      *   ACCOUNT_NUMBER       CHAR(8)       NOT NULL
      *   SORT_CODE            CHAR(6)       NOT NULL
      *   CUST_ID              CHAR(15)      NOT NULL
      *   PRODUCT_CD           CHAR(4)       NOT NULL
      *   BALANCE_PENCE        DECIMAL(15,0) NOT NULL
      *   CREDIT_LIMIT_PENCE   DECIMAL(15,0) NOT NULL
      *   COLLATERAL_PENCE     DECIMAL(15,0) NOT NULL
      *   ARREARS_DAYS         SMALLINT      NOT NULL
      *   DEFAULT_FLAG         CHAR(1)       NOT NULL
      *----------------------------------------------------------------
      * HOST VARIABLE STRUCTURE FOR CRDB2.ACCOUNT_EXPOSURE
      *----------------------------------------------------------------
       01  DCLACX-ACCOUNT-EXPOSURE.
           10  HV-ACCOUNT-NUMBER     PIC X(8).
           10  HV-SORT-CODE          PIC X(6).
           10  HV-CUST-ID            PIC X(15).
           10  HV-PRODUCT-CD         PIC X(4).
           10  HV-BALANCE-PENCE      PIC S9(15) COMP-3.
           10  HV-CREDIT-LIMIT-PENCE PIC S9(15) COMP-3.
           10  HV-COLLATERAL-PENCE   PIC S9(15) COMP-3.
           10  HV-ARREARS-DAYS       PIC S9(4) COMP.
           10  HV-DEFAULT-FLAG       PIC X(1).
