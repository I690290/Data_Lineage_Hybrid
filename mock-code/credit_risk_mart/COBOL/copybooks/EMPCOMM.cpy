      *================================================================
      * COPYBOOK : EMPCOMM
      * SYSTEM   : Credit Risk Data Mart - Employees (RM) pipeline
      * PURPOSE  : Shared communication area for the MVC chain
      *            CEMPDRV -> CEMPCTL -> CEMPBIZ -> CEMPDAO.
      *            CEMPDAO fills the raw DB2 columns; CEMPBIZ converts
      *            the portfolio value held in thousands of GBP into
      *            an absolute GBP figure.
      *================================================================
           05  EMC-RETURN-CODE        PIC S9(4) COMP.
           05  EMC-EMP-ID             PIC X(8).
           05  EMC-EMP-NAME           PIC X(40).
           05  EMC-BRANCH-SORT-CODE   PIC X(6).
           05  EMC-ROLE               PIC X(4).
           05  EMC-RM-TIER            PIC X(2).
           05  EMC-PORTFOLIO-THOU     PIC S9(11) COMP-3.
           05  EMC-FCA-CERT-FLAG      PIC X(1).
           05  EMC-START-DATE         PIC X(10).
      *    Derived by the business layer (CEMPBIZ)
           05  EMC-PORTFOLIO-GBP      PIC S9(14) COMP-3.
