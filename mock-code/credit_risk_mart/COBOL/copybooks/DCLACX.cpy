      *================================================================
      * DCLGEN  : DCLACX
      * TABLE   : CRDB2.ACCOUNT_EXPOSURE
      * SYSTEM  : Credit Risk Data Mart - Accounts/Exposure pipeline
      * PURPOSE : DB2 DCLGEN for the account exposure table. Declared
      *           table definition plus the host-variable structure
      *           used by CACXDAO for cursor FETCH. Carries the raw
      *           Basel risk drivers (drawn/undrawn/accrued balances,
      *           delinquency, bureau score, collateral type and the
      *           macro downturn adjustment) from which CACXBIZ derives
      *           EAD, LGD and PD.
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
      *   DRAWN_BALANCE_PENCE  DECIMAL(15,0) NOT NULL
      *   UNDRAWN_LIMIT_PENCE  DECIMAL(15,0) NOT NULL
      *   ACCRUED_INT_PENCE    DECIMAL(15,0) NOT NULL
      *   DAYS_PAST_DUE        SMALLINT      NOT NULL
      *   BUREAU_SCORE         SMALLINT      NOT NULL
      *   COLLATERAL_CODE      CHAR(2)       NOT NULL
      *   MACRO_ADJ_BPS        SMALLINT      NOT NULL
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
           10  HV-DRAWN-PENCE        PIC S9(15) COMP-3.
           10  HV-UNDRAWN-PENCE      PIC S9(15) COMP-3.
           10  HV-ACCRUED-PENCE      PIC S9(15) COMP-3.
           10  HV-DAYS-PAST-DUE      PIC S9(4) COMP.
           10  HV-BUREAU-SCORE       PIC S9(4) COMP.
           10  HV-COLLATERAL-CODE    PIC X(2).
           10  HV-MACRO-ADJ-BPS      PIC S9(4) COMP.
