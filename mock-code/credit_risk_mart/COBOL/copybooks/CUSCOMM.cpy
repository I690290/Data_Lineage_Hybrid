      *================================================================
      * COPYBOOK : CUSCOMM
      * SYSTEM   : Credit Risk Data Mart - Customers pipeline
      * PURPOSE  : Shared communication area for the MVC chain
      *            CCUSDRV -> CCUSCTL -> CCUSBIZ -> CCUSDAO.
      *            CCUSDAO fills the raw DB2 columns; CCUSBIZ derives
      *            the concatenated full name and the FCA credit risk
      *            tier (A-E) from the raw bureau score.
      *================================================================
           05  CUC-RETURN-CODE        PIC S9(4) COMP.
           05  CUC-CUST-ID            PIC X(15).
           05  CUC-TITLE              PIC X(4).
           05  CUC-FORENAME           PIC X(20).
           05  CUC-SURNAME            PIC X(30).
           05  CUC-DOB                PIC X(10).
           05  CUC-SORT-CODE          PIC X(6).
           05  CUC-KYC-STATUS         PIC X(2).
           05  CUC-SCORE-RAW          PIC S9(4) COMP.
           05  CUC-PEP-FLAG           PIC X(1).
           05  CUC-RESIDENCY          PIC X(2).
           05  CUC-VULN-FLAG          PIC X(1).
      *    Derived by the business layer (CCUSBIZ)
           05  CUC-FULL-NAME          PIC X(51).
           05  CUC-RISK-TIER          PIC X(1).
