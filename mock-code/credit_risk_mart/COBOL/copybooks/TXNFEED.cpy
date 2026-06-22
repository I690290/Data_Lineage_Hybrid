      *================================================================
      * COPYBOOK : TXNFEED
      * SYSTEM   : Credit Risk Data Mart - Transactions pipeline
      * PURPOSE  : Processed transaction feed record. Written by
      *            CTXNDRV (RECFM=FB), read by the data-quality
      *            program CTXNDQA which splits it into the valid
      *            .dat, error and metrics feeds.
      *================================================================
           05  TXD-TXN-ID             PIC X(18).
           05  TXD-ACCOUNT-NUMBER     PIC X(8).
           05  TXD-SORT-CODE          PIC X(6).
           05  TXD-TXN-TYPE           PIC X(4).
           05  TXD-MCC                PIC X(4).
           05  TXD-POSTING-DATE       PIC X(10).
           05  TXD-CCY                PIC X(3).
           05  TXD-AMOUNT-GBP         PIC -9(11).99.
           05  TXD-RISK-WEIGHT        PIC 9.9(4).
           05  TXD-FCA-FLAG           PIC X(1).
