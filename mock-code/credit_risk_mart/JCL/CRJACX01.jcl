//CRJACX01 JOB (CRDM,ACX,001),
//         'CRM EXPOSURE EXTRACT',
//         CLASS=A,
//         MSGCLASS=X,
//         MSGLEVEL=(1,1),
//         NOTIFY=&SYSUID,
//         REGION=0M
//*
//*================================================================
//* JOB    : CRJACX01
//* SYSTEM : Credit Risk Data Mart - Accounts/Exposure pipeline
//* PURPOSE: Extract + JOINKEYS enrich + MVC transform of exposures.
//*   STEP010 - IKJEFT01 / DSNTIAUL unload of CRDB2.ACCOUNT_EXPOSURE
//*             (SQL in SYSIN) -> CRDM.ACX.UNLOAD (SYSREC00)
//*   STEP020 - DFSORT JOINKEYS: enrich the exposure unload (F1) with
//*             the customer unload (F2) on CUST_ID
//*             -> CRDM.ACX.ENRICHED.UNLOAD
//*   STEP040 - CACXDRV: MVC chain (CACXDRV -> CACXCTL -> CACXBIZ
//*             -> CACXDAO) reads CRDB2.ACCOUNT_EXPOSURE via cursor,
//*             derives net exposure / utilisation
//*             -> CRDM.ACX.PROCESSED.FEED
//*
//* SCHEDULE : Daily, Mon-Fri, 02:15 EST
//* DEPENDS  : CRJCUS01 (CRDM.CUS.UNLOAD must exist for STEP020)
//*================================================================
//JOBLIB   DD DSN=CRDM.PROD.LOADLIB,DISP=SHR
//         DD DSN=SYS1.DFSORT.SORTLIB,DISP=SHR
//*
//***********************************************************
//* STEP010: TSO/E batch DSNTIAUL unload                    *
//* READS : CRDB2.ACCOUNT_EXPOSURE (DB2)                    *
//* WRITES: CRDM.ACX.UNLOAD (SYSREC00)                      *
//***********************************************************
//STEP010  EXEC PGM=IKJEFT01,
//         COND=(4,LT)
//SYSTSPRT DD SYSOUT=*
//SYSPRINT DD SYSOUT=*
//SYSUDUMP DD SYSOUT=*
//SYSTSIN  DD *
  DSN SYSTEM(DBCR)
  RUN PROGRAM(DSNTIAUL) PLAN(DSNTIAUL) PARMS('SQL')
  END
/*
//SYSIN    DD *
  SELECT ACCOUNT_NUMBER,
         SORT_CODE,
         CUST_ID,
         PRODUCT_CD,
         BALANCE_PENCE,
         CREDIT_LIMIT_PENCE,
         COLLATERAL_PENCE,
         ARREARS_DAYS,
         DEFAULT_FLAG
  FROM CRDB2.ACCOUNT_EXPOSURE
  WHERE EXPOSURE_STATUS = 'OPEN';
/*
//SYSREC00 DD DSN=CRDM.ACX.UNLOAD,
//            DISP=(NEW,CATLG,DELETE),
//            SPACE=(CYL,(80,20),RLSE),
//            DCB=(RECFM=FB,LRECL=80,BLKSIZE=27920,DSORG=PS),
//            UNIT=SYSDA
//SYSPUNCH DD DSN=CRDM.ACX.UNLOAD.CTL,
//            DISP=(NEW,CATLG,DELETE),
//            SPACE=(TRK,(2,1)),UNIT=SYSDA
//*
//***********************************************************
//* STEP020: DFSORT JOINKEYS - enrich exposure w/ customer  *
//*   F1 = CRDM.ACX.UNLOAD     (key: CUST_ID pos 15,15)     *
//*   F2 = CRDM.CUS.UNLOAD     (key: CUST_ID pos 1,15)      *
//*   JOIN: inner (paired only)                              *
//* READS : CRDM.ACX.UNLOAD (F1), CRDM.CUS.UNLOAD (F2)      *
//* WRITES: CRDM.ACX.ENRICHED.UNLOAD                        *
//***********************************************************
//STEP020  EXEC PGM=SORT,
//         COND=(4,LT)
//SYSOUT   DD SYSOUT=*
//SORTJNF1 DD DSN=CRDM.ACX.UNLOAD,DISP=SHR
//SORTJNF2 DD DSN=CRDM.CUS.UNLOAD,DISP=SHR
//SORTOUT  DD DSN=CRDM.ACX.ENRICHED.UNLOAD,
//            DISP=(NEW,CATLG,DELETE),
//            SPACE=(CYL,(80,20),RLSE),
//            DCB=(RECFM=FB,LRECL=130,BLKSIZE=27950,DSORG=PS),
//            UNIT=SYSDA
//SYSIN    DD *
  JOINKEYS FILES=F1,FIELDS=(15,15,A)
  JOINKEYS FILES=F2,FIELDS=(1,15,A)
  JOIN UNPAIRED,F1,ONLY
  REFORMAT FIELDS=(F1:1,80,F2:16,30,F2:51,2)
  SORT FIELDS=(2,6,CH,A,1,8,CH,A)
/*
//*
//***********************************************************
//* STEP040: MVC transform driver (4-layer nested CALL)     *
//* READS : CRDB2.ACCOUNT_EXPOSURE (DB2, via CACXDAO)       *
//* WRITES: CRDM.ACX.PROCESSED.FEED                         *
//***********************************************************
//STEP040  EXEC PGM=CACXDRV,
//         PARM='SUBSYS=DBCR',
//         COND=(4,LT)
//STEPLIB  DD DSN=CRDM.PROD.LOADLIB,DISP=SHR
//SYSPRINT DD SYSOUT=*
//SYSOUT   DD SYSOUT=*
//SYSDBOUT DD SYSOUT=*
//DBRM     DD DSN=CRDM.PROD.DBRMLIB(CACXDAO),DISP=SHR
//ACXFEED  DD DSN=CRDM.ACX.PROCESSED.FEED,
//            DISP=(NEW,CATLG,DELETE),
//            SPACE=(CYL,(80,20),RLSE),
//            DCB=(RECFM=FB,LRECL=104,BLKSIZE=27872,DSORG=PS),
//            UNIT=SYSDA
//*
