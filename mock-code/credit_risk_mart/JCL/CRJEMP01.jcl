//CRJEMP01 JOB (CRDM,EMP,001),
//         'CRM RM EXTRACT',
//         CLASS=A,
//         MSGCLASS=X,
//         MSGLEVEL=(1,1),
//         NOTIFY=&SYSUID,
//         REGION=0M
//*
//*================================================================
//* JOB    : CRJEMP01
//* SYSTEM : Credit Risk Data Mart - Employees (RM) pipeline
//* PURPOSE: Extract + sort + MVC transform of relationship mgrs.
//*   STEP010 - DSNUTILB UNLOAD of CRDB2.EMPLOYEE_MASTER
//*             -> CRDM.EMP.UNLOAD
//*   STEP020 - DFSORT sort by branch sort code / employee id
//*             -> CRDM.EMP.SORTED.UNLOAD
//*   STEP040 - CEMPDRV: MVC chain (CEMPDRV -> CEMPCTL -> CEMPBIZ
//*             -> CEMPDAO) reads CRDB2.EMPLOYEE_MASTER via cursor,
//*             scales portfolio to GBP -> CRDM.EMP.PROCESSED.FEED
//*
//* SCHEDULE : Weekly, Monday, 02:00 EST
//*================================================================
//JOBLIB   DD DSN=CRDM.PROD.LOADLIB,DISP=SHR
//         DD DSN=SYS1.DFSORT.SORTLIB,DISP=SHR
//*
//***********************************************************
//* STEP010: DB2 UNLOAD utility (DSNUTILB)                  *
//* READS : CRDB2.EMPLOYEE_MASTER (DB2)                     *
//* WRITES: CRDM.EMP.UNLOAD                                 *
//***********************************************************
//STEP010  EXEC PGM=DSNUTILB,
//         PARM='DBCR,UNLDEMP',
//         COND=(4,LT)
//STEPLIB  DD DSN=DSN.SDSNLOAD,DISP=SHR
//SYSPRINT DD SYSOUT=*
//UTPRINT  DD SYSOUT=*
//SYSREC   DD DSN=CRDM.EMP.UNLOAD,
//            DISP=(NEW,CATLG,DELETE),
//            SPACE=(CYL,(20,5),RLSE),
//            DCB=(RECFM=FB,LRECL=80,BLKSIZE=27920,DSORG=PS),
//            UNIT=SYSDA
//SYSPUNCH DD DSN=CRDM.EMP.UNLOAD.CTL,
//            DISP=(NEW,CATLG,DELETE),
//            SPACE=(TRK,(2,1)),UNIT=SYSDA
//SYSIN    DD *
  UNLOAD TABLESPACE CRDB2.TSEMPMST
    FROM TABLE CRDB2.EMPLOYEE_MASTER
       ( EMP_ID             POSITION(1)  CHAR(8),
         EMP_NAME           POSITION(9)  CHAR(40),
         BRANCH_SORT_CODE   POSITION(49) CHAR(6),
         ROLE_CD            POSITION(55) CHAR(4),
         RM_TIER            POSITION(59) CHAR(2),
         PORTFOLIO_GBP_THOU POSITION(61) DECIMAL,
         FCA_CERTIFIED_FLAG POSITION(69) CHAR(1),
         START_DATE         POSITION(70) CHAR(10) )
    WHERE 'ROLE_CD = ''RMGR'' AND EMP_STATUS = ''A'''
/*
//*
//***********************************************************
//* STEP020: DFSORT - sort unload by branch / employee id   *
//* READS : CRDM.EMP.UNLOAD                                 *
//* WRITES: CRDM.EMP.SORTED.UNLOAD                          *
//***********************************************************
//STEP020  EXEC PGM=SORT,
//         COND=(4,LT)
//SYSOUT   DD SYSOUT=*
//SORTIN   DD DSN=CRDM.EMP.UNLOAD,DISP=SHR
//SORTOUT  DD DSN=CRDM.EMP.SORTED.UNLOAD,
//            DISP=(NEW,CATLG,DELETE),
//            SPACE=(CYL,(20,5),RLSE),
//            DCB=(RECFM=FB,LRECL=80,BLKSIZE=27920,DSORG=PS),
//            UNIT=SYSDA
//SYSIN    DD *
  SORT FIELDS=(49,6,CH,A,1,8,CH,A)
/*
//*
//***********************************************************
//* STEP040: MVC transform driver (4-layer nested CALL)     *
//* READS : CRDB2.EMPLOYEE_MASTER (DB2, via CEMPDAO)        *
//* WRITES: CRDM.EMP.PROCESSED.FEED                         *
//***********************************************************
//STEP040  EXEC PGM=CEMPDRV,
//         PARM='SUBSYS=DBCR',
//         COND=(4,LT)
//STEPLIB  DD DSN=CRDM.PROD.LOADLIB,DISP=SHR
//SYSPRINT DD SYSOUT=*
//SYSOUT   DD SYSOUT=*
//SYSDBOUT DD SYSOUT=*
//DBRM     DD DSN=CRDM.PROD.DBRMLIB(CEMPDAO),DISP=SHR
//EMPFEED  DD DSN=CRDM.EMP.PROCESSED.FEED,
//            DISP=(NEW,CATLG,DELETE),
//            SPACE=(CYL,(20,5),RLSE),
//            DCB=(RECFM=FB,LRECL=85,BLKSIZE=27880,DSORG=PS),
//            UNIT=SYSDA
//*
