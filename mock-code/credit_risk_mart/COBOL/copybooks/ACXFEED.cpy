      *================================================================
      * COPYBOOK : ACXFEED
      * SYSTEM   : Credit Risk Data Mart - Accounts/Exposure pipeline
      * PURPOSE  : Processed account-exposure feed record written by
      *            CACXDRV and consumed by CACXDQA.
      *================================================================
           05  AXD-ACCOUNT-NUMBER     PIC X(8).
           05  AXD-SORT-CODE          PIC X(6).
           05  AXD-CUST-ID            PIC X(15).
           05  AXD-PRODUCT            PIC X(4).
           05  AXD-BALANCE-GBP        PIC -9(13).99.
           05  AXD-LIMIT-GBP          PIC -9(13).99.
           05  AXD-COLLATERAL-GBP     PIC -9(13).99.
           05  AXD-NET-EXPOSURE-GBP   PIC -9(13).99.
           05  AXD-UTILISATION-PCT    PIC 9(3).99.
           05  AXD-ARREARS-DAYS       PIC 9(4).
           05  AXD-DEFAULT-FLAG       PIC X(1).
