//CRJTXNLD JOB (CRDM,TXN,003),
//         'CRM TXN ORA LOAD',
//         CLASS=A,MSGCLASS=X,MSGLEVEL=(1,1),NOTIFY=&SYSUID
//*
//*================================================================
//* JOB    : CRJTXNLD
//* SYSTEM : Credit Risk Data Mart - Transactions Oracle ingest
//* PURPOSE: BPXBATCH triggers the remote UNIX driver script which
//*          runs SQL*Plus to (1) define the external table over the
//*          delivered CR_TXN_VALID_*.dat and (2) load the staging
//*          table CR_STAGE.TXN_TRANSACTIONS_STG.
//*================================================================
//STEP010  EXEC PGM=BPXBATCH,
//         PARM='SH /app/crm/scripts/load_txn.ksh',
//         COND=(4,LT)
//STDOUT   DD SYSOUT=*
//STDERR   DD SYSOUT=*
//STDENV   DD *
ORACLE_SID=CRMP
ORACLE_HOME=/opt/oracle/product/19c
CRM_LOAD_DIR=/app/crm/load
/*
//*
