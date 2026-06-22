      *================================================================
      * DCLGEN  : DCLEMP
      * TABLE   : CRDB2.EMPLOYEE_MASTER
      * SYSTEM  : Credit Risk Data Mart - Employees (RM) pipeline
      * PURPOSE : DB2 DCLGEN for the relationship-manager employee
      *           master table. Declared table definition plus the
      *           host-variable structure used by CEMPDAO.
      *================================================================
      * DB2 TABLE DEFINITION (CRDB2.EMPLOYEE_MASTER):
      *   EMP_ID               CHAR(8)       NOT NULL
      *   EMP_NAME             CHAR(40)      NOT NULL
      *   BRANCH_SORT_CODE     CHAR(6)       NOT NULL
      *   ROLE_CD              CHAR(4)       NOT NULL
      *   RM_TIER              CHAR(2)
      *   PORTFOLIO_GBP_THOU   DECIMAL(11,0) NOT NULL
      *   FCA_CERTIFIED_FLAG   CHAR(1)       NOT NULL
      *   START_DATE           DATE          NOT NULL
      *----------------------------------------------------------------
      * HOST VARIABLE STRUCTURE FOR CRDB2.EMPLOYEE_MASTER
      *----------------------------------------------------------------
       01  DCLEMP-EMPLOYEE-MASTER.
           10  HV-EMP-ID             PIC X(8).
           10  HV-EMP-NAME           PIC X(40).
           10  HV-BRANCH-SORT-CODE   PIC X(6).
           10  HV-ROLE-CD            PIC X(4).
           10  HV-RM-TIER            PIC X(2).
           10  HV-PORTFOLIO-THOU     PIC S9(11) COMP-3.
           10  HV-FCA-CERT-FLAG      PIC X(1).
           10  HV-START-DATE         PIC X(10).
