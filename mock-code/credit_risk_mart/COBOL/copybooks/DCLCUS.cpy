      *================================================================
      * DCLGEN  : DCLCUS
      * TABLE   : CRDB2.CUSTOMER_MASTER
      * SYSTEM  : Credit Risk Data Mart - Customers pipeline
      * PURPOSE : DB2 DCLGEN for the customer master table. Declared
      *           table definition plus the host-variable structure
      *           used by CCUSDAO for cursor FETCH.
      *================================================================
      * DB2 TABLE DEFINITION (CRDB2.CUSTOMER_MASTER):
      *   CUST_ID              CHAR(15)  NOT NULL
      *   TITLE                CHAR(4)
      *   FORENAME             CHAR(20)
      *   SURNAME              CHAR(30)
      *   DATE_OF_BIRTH        DATE      NOT NULL
      *   SORT_CODE            CHAR(6)   NOT NULL
      *   KYC_STATUS_CD        CHAR(2)   NOT NULL
      *   CR_SCORE_RAW         SMALLINT  NOT NULL
      *   PEP_FLAG             CHAR(1)   NOT NULL
      *   RESIDENCY_CD         CHAR(2)
      *   FCA_VULNERABLE_FLAG  CHAR(1)   NOT NULL
      *----------------------------------------------------------------
      * HOST VARIABLE STRUCTURE FOR CRDB2.CUSTOMER_MASTER
      *----------------------------------------------------------------
       01  DCLCUS-CUSTOMER-MASTER.
           10  HV-CUST-ID            PIC X(15).
           10  HV-TITLE              PIC X(4).
           10  HV-FORENAME           PIC X(20).
           10  HV-SURNAME            PIC X(30).
           10  HV-DATE-OF-BIRTH      PIC X(10).
           10  HV-SORT-CODE          PIC X(6).
           10  HV-KYC-STATUS-CD      PIC X(2).
           10  HV-CR-SCORE-RAW       PIC S9(4) COMP.
           10  HV-PEP-FLAG           PIC X(1).
           10  HV-RESIDENCY-CD       PIC X(2).
           10  HV-FCA-VULN-FLAG      PIC X(1).
