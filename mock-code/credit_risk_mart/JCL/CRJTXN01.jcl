//CRJTXN01 JOB (CRDM,TXN,001),
//         'CRM TXN EXTRACT',
//         CLASS=A,
//         MSGCLASS=X,
//         MSGLEVEL=(1,1),
//         NOTIFY=&SYSUID,
//         REGION=0M
//*
//*================================================================
//* JOB    : CRJTXN01
//* SYSTEM : Credit Risk Data Mart - Transactions pipeline
//* PURPOSE: Extract + sort + MVC transform of daily transactions.
//*   STEP010 - DSNUTILB UNLOAD of CRDB2.CUST_TRANSACTIONS
//*             -> CRDM.TXN.UNLOAD (operational archive)
//*   STEP020 - DFSORT sort of the unload by account / posting date
//*             -> CRDM.TXN.SORTED.UNLOAD
//*   STEP040 - CTXNDRV: MVC chain (CTXNDRV -> CTXNCTL -> CTXNBIZ
//*             -> CTXNDAO) reads CRDB2.CUST_TRANSACTIONS via cursor
//*             and writes the processed feed
//*             -> CRDM.TXN.PROCESSED.FEED
//*
//* SCHEDULE : Daily, Mon-Fri, 01:30 EST
//*================================================================
//JOBLIB   DD DSN=CRDM.PROD.LOADLIB,DISP=SHR
//         DD DSN=SYS1.DFSORT.SORTLIB,DISP=SHR
//*
//***********************************************************
//* STEP010: DB2 UNLOAD utility (DSNUTILB)                  *
//* READS : CRDB2.CUST_TRANSACTIONS (DB2)                   *
//* WRITES: CRDM.TXN.UNLOAD                                 *
//***********************************************************
//STEP010  EXEC PGM=DSNUTILB,
//         PARM='DBCR,UNLDTXN',
//         COND=(4,LT)
//STEPLIB  DD DSN=DSN.SDSNLOAD,DISP=SHR
//SYSPRINT DD SYSOUT=*
//UTPRINT  DD SYSOUT=*
//SYSREC   DD DSN=CRDM.TXN.UNLOAD,
//            DISP=(NEW,CATLG,DELETE),
//            SPACE=(CYL,(100,20),RLSE),
//            DCB=(RECFM=FB,LRECL=72,BLKSIZE=27936,DSORG=PS),
//            UNIT=SYSDA
//SYSPUNCH DD DSN=CRDM.TXN.UNLOAD.CTL,
//            DISP=(NEW,CATLG,DELETE),
//            SPACE=(TRK,(2,1)),UNIT=SYSDA
//SYSIN    DD *
  UNLOAD TABLESPACE CRDB2.TSCUSTXN
    FROM TABLE CRDB2.CUST_TRANSACTIONS
       ( TXN_ID              POSITION(1)  CHAR(18),
         ACCOUNT_NUMBER      POSITION(19) CHAR(8),
         SORT_CODE           POSITION(27) CHAR(6),
         TXN_AMT_PENCE       POSITION(33) DECIMAL,
         TXN_CCY             POSITION(41) CHAR(3),
         TXN_TYPE_CD         POSITION(44) CHAR(4),
         MERCHANT_CAT_CD     POSITION(48) CHAR(4),
         POSTING_TS          POSITION(52) CHAR(10),
         FCA_REPORTABLE_FLAG POSITION(62) CHAR(1) )
    WHERE 'TXN_STATUS = ''P'' AND TXN_CCY = ''GBP'''
/*
//*
//***********************************************************
//* STEP020: DFSORT - sort the unload by account/date       *
//* READS : CRDM.TXN.UNLOAD                                 *
//* WRITES: CRDM.TXN.SORTED.UNLOAD                          *
//***********************************************************
//STEP020  EXEC PGM=SORT,
//         COND=(4,LT)
//SYSOUT   DD SYSOUT=*
//SORTIN   DD DSN=CRDM.TXN.UNLOAD,DISP=SHR
//SORTOUT  DD DSN=CRDM.TXN.SORTED.UNLOAD,
//            DISP=(NEW,CATLG,DELETE),
//            SPACE=(CYL,(100,20),RLSE),
//            DCB=(RECFM=FB,LRECL=72,BLKSIZE=27936,DSORG=PS),
//            UNIT=SYSDA
//SYSIN    DD *
  SORT FIELDS=(19,8,CH,A,52,10,CH,A)
  SUM FIELDS=NONE
/*
//*
//***********************************************************
//* STEP040: MVC transform driver (4-layer nested CALL)     *
//* READS : CRDB2.CUST_TRANSACTIONS (DB2, via CTXNDAO)      *
//* WRITES: CRDM.TXN.PROCESSED.FEED                         *
//***********************************************************
//STEP040  EXEC PGM=CTXNDRV,
//         PARM='SUBSYS=DBCR',
//         COND=(4,LT)
//STEPLIB  DD DSN=CRDM.PROD.LOADLIB,DISP=SHR
//SYSPRINT DD SYSOUT=*
//SYSOUT   DD SYSOUT=*
//SYSDBOUT DD SYSOUT=*
//DBRM     DD DSN=CRDM.PROD.DBRMLIB(CTXNDAO),DISP=SHR
//TXNFEED  DD DSN=CRDM.TXN.PROCESSED.FEED,
//            DISP=(NEW,CATLG,DELETE),
//            SPACE=(CYL,(100,20),RLSE),
//            DCB=(RECFM=FB,LRECL=80,BLKSIZE=27920,DSORG=PS),
//            UNIT=SYSDA
//*
