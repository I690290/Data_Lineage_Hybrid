      *================================================================
      * COPYBOOK : EMPFEED
      * SYSTEM   : Credit Risk Data Mart - Employees (RM) pipeline
      * PURPOSE  : Processed relationship-manager feed record written
      *            by CEMPDRV and consumed by CEMPDQA.
      *================================================================
           05  EMD-EMP-ID             PIC X(8).
           05  EMD-EMP-NAME           PIC X(40).
           05  EMD-BRANCH-SORT-CODE   PIC X(6).
           05  EMD-ROLE               PIC X(4).
           05  EMD-RM-TIER            PIC X(2).
           05  EMD-PORTFOLIO-GBP      PIC -9(14).
           05  EMD-FCA-CERT-FLAG      PIC X(1).
           05  EMD-START-DATE         PIC X(10).
