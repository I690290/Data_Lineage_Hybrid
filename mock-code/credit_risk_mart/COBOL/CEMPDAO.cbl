      *================================================================
      * PROGRAM  : CEMPDAO  (Layer 4 - Data Access)
      * SYSTEM   : Credit Risk Data Mart - Employees (RM) pipeline
      * PURPOSE  : DB2 data-access object for CRDB2.EMPLOYEE_MASTER.
      *            Fetches the next active relationship manager into
      *            the shared communication area (EMPCOMM). End-of-
      *            cursor reported via EMC-RETURN-CODE = 4.
      *
      * CALLED BY: CEMPBIZ (CALL 'CEMPDAO' USING WS-EMP-COMM)
      * DB2 TABLES ACCESSED:
      *   READ   : CRDB2.EMPLOYEE_MASTER
      *================================================================
       IDENTIFICATION DIVISION.
       PROGRAM-ID. CEMPDAO.
       AUTHOR. CREDIT-RISK-BATCH.

       ENVIRONMENT DIVISION.

       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01  WS-CURSOR-FLAGS.
           05  WS-CURSOR-OPEN      PIC X    VALUE 'N'.
               88  CURSOR-IS-OPEN  VALUE 'Y'.

       COPY DCLEMP.

           EXEC SQL
               INCLUDE SQLCA
           END-EXEC.

       LINKAGE SECTION.
       01  LK-EMP-COMM.
       COPY EMPCOMM.

       PROCEDURE DIVISION USING LK-EMP-COMM.
      *================================================================
       MAIN-PARA.
           IF NOT CURSOR-IS-OPEN
               PERFORM OPEN-CURSOR-PARA
           END-IF.
           PERFORM FETCH-NEXT-PARA.
           GOBACK.

      *================================================================
       OPEN-CURSOR-PARA.
           EXEC SQL
               DECLARE CSR_EMP CURSOR FOR
               SELECT
                   E.EMP_ID,
                   E.EMP_NAME,
                   E.BRANCH_SORT_CODE,
                   E.ROLE_CD,
                   E.RM_TIER,
                   E.PORTFOLIO_GBP_THOU,
                   E.FCA_CERTIFIED_FLAG,
                   VARCHAR_FORMAT(E.START_DATE, 'YYYY-MM-DD')
               FROM CRDB2.EMPLOYEE_MASTER E
               WHERE E.ROLE_CD = 'RMGR'
                 AND E.EMP_STATUS = 'A'
               ORDER BY E.BRANCH_SORT_CODE, E.EMP_ID
           END-EXEC.
           EXEC SQL
               OPEN CSR_EMP
           END-EXEC.
           MOVE 'Y' TO WS-CURSOR-OPEN.

      *================================================================
       FETCH-NEXT-PARA.
           EXEC SQL
               FETCH CSR_EMP
               INTO  :HV-EMP-ID,
                     :HV-EMP-NAME,
                     :HV-BRANCH-SORT-CODE,
                     :HV-ROLE-CD,
                     :HV-RM-TIER,
                     :HV-PORTFOLIO-THOU,
                     :HV-FCA-CERT-FLAG,
                     :HV-START-DATE
           END-EXEC.
           IF SQLCODE = 0
               PERFORM MAP-ROW-PARA
               MOVE ZERO TO EMC-RETURN-CODE
           ELSE
               PERFORM CLOSE-CURSOR-PARA
               MOVE 4 TO EMC-RETURN-CODE
           END-IF.

      *================================================================
       MAP-ROW-PARA.
           MOVE HV-EMP-ID           TO EMC-EMP-ID.
           MOVE HV-EMP-NAME         TO EMC-EMP-NAME.
           MOVE HV-BRANCH-SORT-CODE TO EMC-BRANCH-SORT-CODE.
           MOVE HV-ROLE-CD          TO EMC-ROLE.
           MOVE HV-RM-TIER          TO EMC-RM-TIER.
           MOVE HV-PORTFOLIO-THOU   TO EMC-PORTFOLIO-THOU.
           MOVE HV-FCA-CERT-FLAG    TO EMC-FCA-CERT-FLAG.
           MOVE HV-START-DATE       TO EMC-START-DATE.

      *================================================================
       CLOSE-CURSOR-PARA.
           EXEC SQL
               CLOSE CSR_EMP
           END-EXEC.
           MOVE 'N' TO WS-CURSOR-OPEN.
