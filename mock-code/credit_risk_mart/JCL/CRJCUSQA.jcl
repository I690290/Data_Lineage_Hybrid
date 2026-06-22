//CRJCUSQA JOB (CRDM,CUS,002),
//         'CRM CUST DQ',
//         CLASS=A,MSGCLASS=X,MSGLEVEL=(1,1),NOTIFY=&SYSUID
//*
//*================================================================
//* JOB    : CRJCUSQA - Customers data quality
//* PURPOSE: CCUSDQA reads CRDM.CUS.PROCESSED.FEED and splits it
//*          into valid (.dat), error and metrics feeds.
//*================================================================
//JOBLIB   DD DSN=CRDM.PROD.LOADLIB,DISP=SHR
//*
//STEP010  EXEC PGM=CCUSDQA,COND=(4,LT)
//STEPLIB  DD DSN=CRDM.PROD.LOADLIB,DISP=SHR
//SYSPRINT DD SYSOUT=*
//SYSOUT   DD SYSOUT=*
//CUSFEED  DD DSN=CRDM.CUS.PROCESSED.FEED,DISP=SHR
//CUSVALID DD DSN=CRDM.CUS.VALID.DAT,
//            DISP=(NEW,CATLG,DELETE),
//            SPACE=(CYL,(50,10),RLSE),
//            DCB=(RECFM=FB,LRECL=86,BLKSIZE=27864,DSORG=PS),
//            UNIT=SYSDA
//CUSERROR DD DSN=CRDM.CUS.ERROR,
//            DISP=(NEW,CATLG,DELETE),
//            SPACE=(CYL,(10,5),RLSE),
//            DCB=(RECFM=FB,LRECL=126,BLKSIZE=27846,DSORG=PS),
//            UNIT=SYSDA
//CUSMETR  DD DSN=CRDM.CUS.METRICS,
//            DISP=(NEW,CATLG,DELETE),
//            SPACE=(TRK,(2,1),RLSE),
//            DCB=(RECFM=FB,LRECL=80,BLKSIZE=27920,DSORG=PS),
//            UNIT=SYSDA
//*
