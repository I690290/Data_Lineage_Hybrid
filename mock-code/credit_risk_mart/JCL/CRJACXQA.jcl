//CRJACXQA JOB (CRDM,ACX,002),
//         'CRM EXPOSURE DQ',
//         CLASS=A,MSGCLASS=X,MSGLEVEL=(1,1),NOTIFY=&SYSUID
//*
//*================================================================
//* JOB    : CRJACXQA - Accounts/Exposure data quality
//* PURPOSE: CACXDQA reads CRDM.ACX.PROCESSED.FEED and splits it
//*          into valid (.dat), error and metrics feeds.
//*================================================================
//JOBLIB   DD DSN=CRDM.PROD.LOADLIB,DISP=SHR
//*
//STEP010  EXEC PGM=CACXDQA,COND=(4,LT)
//STEPLIB  DD DSN=CRDM.PROD.LOADLIB,DISP=SHR
//SYSPRINT DD SYSOUT=*
//SYSOUT   DD SYSOUT=*
//ACXFEED  DD DSN=CRDM.ACX.PROCESSED.FEED,DISP=SHR
//ACXVALID DD DSN=CRDM.ACX.VALID.DAT,
//            DISP=(NEW,CATLG,DELETE),
//            SPACE=(CYL,(80,20),RLSE),
//            DCB=(RECFM=FB,LRECL=104,BLKSIZE=27872,DSORG=PS),
//            UNIT=SYSDA
//ACXERROR DD DSN=CRDM.ACX.ERROR,
//            DISP=(NEW,CATLG,DELETE),
//            SPACE=(CYL,(10,5),RLSE),
//            DCB=(RECFM=FB,LRECL=144,BLKSIZE=27936,DSORG=PS),
//            UNIT=SYSDA
//ACXMETR  DD DSN=CRDM.ACX.METRICS,
//            DISP=(NEW,CATLG,DELETE),
//            SPACE=(TRK,(2,1),RLSE),
//            DCB=(RECFM=FB,LRECL=80,BLKSIZE=27920,DSORG=PS),
//            UNIT=SYSDA
//*
