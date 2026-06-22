      *================================================================
      * COPYBOOK : TXNCOMM
      * SYSTEM   : Credit Risk Data Mart - Transactions pipeline
      * PURPOSE  : Shared communication area passed on every
      *            CALL ... USING boundary of the MVC chain
      *            CTXNDRV -> CTXNCTL -> CTXNBIZ -> CTXNDAO.
      *            Raw DB2 columns are filled by the data-access layer
      *            (CTXNDAO); derived GBP amount and risk weight are
      *            filled by the business layer (CTXNBIZ).
      *================================================================
           05  TXC-RETURN-CODE        PIC S9(4) COMP.
           05  TXC-TXN-ID             PIC X(18).
           05  TXC-ACCOUNT-NUMBER     PIC X(8).
           05  TXC-SORT-CODE          PIC X(6).
           05  TXC-AMT-PENCE          PIC S9(15) COMP-3.
           05  TXC-CCY                PIC X(3).
           05  TXC-TXN-TYPE           PIC X(4).
           05  TXC-MCC                PIC X(4).
           05  TXC-POSTING-DATE       PIC X(10).
           05  TXC-FCA-FLAG           PIC X(1).
      *    Derived by the business layer (CTXNBIZ)
           05  TXC-AMT-GBP            PIC S9(13)V99 COMP-3.
           05  TXC-RISK-WEIGHT        PIC S9(1)V9(4) COMP-3.
