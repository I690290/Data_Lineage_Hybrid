//CRJCUS01 JOB (CRDM,CUS,001),
//         'CRM CUST EXTRACT',
//         CLASS=A,
//         MSGCLASS=X,
//         MSGLEVEL=(1,1),
//         NOTIFY=&SYSUID,
//         REGION=0M
//*
//*================================================================
//* JOB    : CRJCUS01
//* SYSTEM : Credit Risk Data Mart - Customers pipeline
//* PURPOSE: Extract + sort + MVC transform of customer master.
//*   STEP010 - IKJEFT01 / DSNTIAUL unload of CRDB2.CUSTOMER_MASTER
//*             (SQL in SYSIN) -> CRDM.CUS.UNLOAD (SYSREC00)
//*   STEP020 - ICETOOL SORT/COPY of the unload by customer id
//*             -> CRDM.CUS.SORTED.UNLOAD
//*   STEP040 - CCUSDRV: MVC chain (CCUSDRV -> CCUSCTL -> CCUSBIZ
//*             -> CCUSDAO) reads CRDB2.CUSTOMER_MASTER via cursor,
//*             derives the FCA risk tier -> CRDM.CUS.PROCESSED.FEED
//*
//* SCHEDULE : Daily, Mon-Fri, 01:30 EST
//*================================================================
//JOBLIB   DD DSN=CRDM.PROD.LOADLIB,DISP=SHR
//         DD DSN=SYS1.DFSORT.SORTLIB,DISP=SHR
//*
//***********************************************************
//* STEP010: TSO/E batch DSNTIAUL unload                    *
//* READS : CRDB2.CUSTOMER_MASTER (DB2)                     *
//* WRITES: CRDM.CUS.UNLOAD (SYSREC00)                      *
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
  SELECT CUST_ID,
         TITLE,
         FORENAME,
         SURNAME,
         DATE_OF_BIRTH,
         SORT_CODE,
         KYC_STATUS_CD,
         CR_SCORE_RAW,
         PEP_FLAG,
         RESIDENCY_CD,
         FCA_VULNERABLE_FLAG
  FROM CRDB2.CUSTOMER_MASTER
  WHERE KYC_STATUS_CD IN ('PA','EN');
/*
//SYSREC00 DD DSN=CRDM.CUS.UNLOAD,
//            DISP=(NEW,CATLG,DELETE),
//            SPACE=(CYL,(50,10),RLSE),
//            DCB=(RECFM=FB,LRECL=100,BLKSIZE=27900,DSORG=PS),
//            UNIT=SYSDA
//SYSPUNCH DD DSN=CRDM.CUS.UNLOAD.CTL,
//            DISP=(NEW,CATLG,DELETE),
//            SPACE=(TRK,(2,1)),UNIT=SYSDA
//*
//***********************************************************
//* STEP020: ICETOOL - sort unload by customer id           *
//* READS : CRDM.CUS.UNLOAD                                 *
//* WRITES: CRDM.CUS.SORTED.UNLOAD                          *
//***********************************************************
//STEP020  EXEC PGM=ICETOOL,
//         COND=(4,LT)
//TOOLMSG  DD SYSOUT=*
//DFSMSG   DD SYSOUT=*
//IN1      DD DSN=CRDM.CUS.UNLOAD,DISP=SHR
//OUT1     DD DSN=CRDM.CUS.SORTED.UNLOAD,
//            DISP=(NEW,CATLG,DELETE),
//            SPACE=(CYL,(50,10),RLSE),
//            DCB=(RECFM=FB,LRECL=100,BLKSIZE=27900,DSORG=PS),
//            UNIT=SYSDA
//TOOLIN   DD *
  SORT FROM(IN1) TO(OUT1) USING(CTL1)
/*
//CTL1CNTL DD *
  SORT FIELDS=(1,15,CH,A)
/*
//*
//***********************************************************
//* STEP040: MVC transform driver (4-layer nested CALL)     *
//* READS : CRDB2.CUSTOMER_MASTER (DB2, via CCUSDAO)        *
//* WRITES: CRDM.CUS.PROCESSED.FEED                         *
//***********************************************************
//STEP040  EXEC PGM=CCUSDRV,
//         PARM='SUBSYS=DBCR',
//         COND=(4,LT)
//STEPLIB  DD DSN=CRDM.PROD.LOADLIB,DISP=SHR
//SYSPRINT DD SYSOUT=*
//SYSOUT   DD SYSOUT=*
//SYSDBOUT DD SYSOUT=*
//DBRM     DD DSN=CRDM.PROD.DBRMLIB(CCUSDAO),DISP=SHR
//CUSFEED  DD DSN=CRDM.CUS.PROCESSED.FEED,
//            DISP=(NEW,CATLG,DELETE),
//            SPACE=(CYL,(50,10),RLSE),
//            DCB=(RECFM=FB,LRECL=86,BLKSIZE=27864,DSORG=PS),
//            UNIT=SYSDA
//*
