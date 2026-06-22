//CRJTXNQA JOB (CRDM,TXN,002),
//         'CRM TXN DQ',
//         CLASS=A,MSGCLASS=X,MSGLEVEL=(1,1),NOTIFY=&SYSUID
//*
//*================================================================
//* JOB    : CRJTXNQA - Transactions data quality
//* PURPOSE: CTXNDQA reads CRDM.TXN.PROCESSED.FEED and splits it
//*          into valid (.dat), error and metrics feeds.
//*================================================================
//JOBLIB   DD DSN=CRDM.PROD.LOADLIB,DISP=SHR
//*
//STEP010  EXEC PGM=CTXNDQA,COND=(4,LT)
//STEPLIB  DD DSN=CRDM.PROD.LOADLIB,DISP=SHR
//SYSPRINT DD SYSOUT=*
//SYSOUT   DD SYSOUT=*
//*    Input: processed transaction feed from CRJTXN01
//TXNFEED  DD DSN=CRDM.TXN.PROCESSED.FEED,DISP=SHR
//*    Output 1: valid records (becomes the .dat for Oracle load)
//TXNVALID DD DSN=CRDM.TXN.VALID.DAT,
//            DISP=(NEW,CATLG,DELETE),
//            SPACE=(CYL,(100,20),RLSE),
//            DCB=(RECFM=FB,LRECL=80,BLKSIZE=27920,DSORG=PS),
//            UNIT=SYSDA
//*    Output 2: rejected records
//TXNERROR DD DSN=CRDM.TXN.ERROR,
//            DISP=(NEW,CATLG,DELETE),
//            SPACE=(CYL,(10,5),RLSE),
//            DCB=(RECFM=FB,LRECL=120,BLKSIZE=27840,DSORG=PS),
//            UNIT=SYSDA
//*    Output 3: quality metrics summary
//TXNMETR  DD DSN=CRDM.TXN.METRICS,
//            DISP=(NEW,CATLG,DELETE),
//            SPACE=(TRK,(2,1),RLSE),
//            DCB=(RECFM=FB,LRECL=80,BLKSIZE=27920,DSORG=PS),
//            UNIT=SYSDA
//*
