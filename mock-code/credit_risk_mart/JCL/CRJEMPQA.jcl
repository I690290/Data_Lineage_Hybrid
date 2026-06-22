//CRJEMPQA JOB (CRDM,EMP,002),
//         'CRM RM DQ',
//         CLASS=A,MSGCLASS=X,MSGLEVEL=(1,1),NOTIFY=&SYSUID
//*
//*================================================================
//* JOB    : CRJEMPQA - Employees (RM) data quality
//* PURPOSE: CEMPDQA reads CRDM.EMP.PROCESSED.FEED and splits it
//*          into valid (.dat), error and metrics feeds.
//*================================================================
//JOBLIB   DD DSN=CRDM.PROD.LOADLIB,DISP=SHR
//*
//STEP010  EXEC PGM=CEMPDQA,COND=(4,LT)
//STEPLIB  DD DSN=CRDM.PROD.LOADLIB,DISP=SHR
//SYSPRINT DD SYSOUT=*
//SYSOUT   DD SYSOUT=*
//EMPFEED  DD DSN=CRDM.EMP.PROCESSED.FEED,DISP=SHR
//EMPVALID DD DSN=CRDM.EMP.VALID.DAT,
//            DISP=(NEW,CATLG,DELETE),
//            SPACE=(CYL,(20,5),RLSE),
//            DCB=(RECFM=FB,LRECL=85,BLKSIZE=27880,DSORG=PS),
//            UNIT=SYSDA
//EMPERROR DD DSN=CRDM.EMP.ERROR,
//            DISP=(NEW,CATLG,DELETE),
//            SPACE=(TRK,(10,5),RLSE),
//            DCB=(RECFM=FB,LRECL=125,BLKSIZE=27875,DSORG=PS),
//            UNIT=SYSDA
//EMPMETR  DD DSN=CRDM.EMP.METRICS,
//            DISP=(NEW,CATLG,DELETE),
//            SPACE=(TRK,(2,1),RLSE),
//            DCB=(RECFM=FB,LRECL=80,BLKSIZE=27920,DSORG=PS),
//            UNIT=SYSDA
//*
