      *================================================================
      * COPYBOOK : CUSFEED
      * SYSTEM   : Credit Risk Data Mart - Customers pipeline
      * PURPOSE  : Processed customer feed record written by CCUSDRV
      *            and consumed by the data-quality program CCUSDQA.
      *================================================================
           05  CUD-CUST-ID            PIC X(15).
           05  CUD-FULL-NAME          PIC X(51).
           05  CUD-DOB                PIC X(10).
           05  CUD-SORT-CODE          PIC X(6).
           05  CUD-KYC-STATUS         PIC X(2).
           05  CUD-CREDIT-RISK-TIER   PIC X(1).
           05  CUD-PEP-FLAG           PIC X(1).
           05  CUD-VULN-FLAG          PIC X(1).
