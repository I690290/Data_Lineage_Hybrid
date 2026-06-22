      *================================================================
      * COPYBOOK : ACXCOMM
      * SYSTEM   : Credit Risk Data Mart - Accounts/Exposure pipeline
      * PURPOSE  : Shared communication area for the MVC chain
      *            CACXDRV -> CACXCTL -> CACXBIZ -> CACXDAO.
      *            CACXDAO fills raw pence balances from DB2; CACXBIZ
      *            converts pence to GBP and derives net exposure and
      *            credit-limit utilisation percentage.
      *================================================================
           05  AXC-RETURN-CODE        PIC S9(4) COMP.
           05  AXC-ACCOUNT-NUMBER     PIC X(8).
           05  AXC-SORT-CODE          PIC X(6).
           05  AXC-CUST-ID            PIC X(15).
           05  AXC-PRODUCT            PIC X(4).
           05  AXC-BALANCE-PENCE      PIC S9(15) COMP-3.
           05  AXC-LIMIT-PENCE        PIC S9(15) COMP-3.
           05  AXC-COLLATERAL-PENCE   PIC S9(15) COMP-3.
           05  AXC-ARREARS-DAYS       PIC S9(4) COMP.
           05  AXC-DEFAULT-FLAG       PIC X(1).
      *    Derived by the business layer (CACXBIZ)
           05  AXC-BALANCE-GBP        PIC S9(13)V99 COMP-3.
           05  AXC-LIMIT-GBP          PIC S9(13)V99 COMP-3.
           05  AXC-COLLATERAL-GBP     PIC S9(13)V99 COMP-3.
           05  AXC-NET-EXPOSURE-GBP   PIC S9(13)V99 COMP-3.
           05  AXC-UTILISATION-PCT    PIC S9(3)V99 COMP-3.
