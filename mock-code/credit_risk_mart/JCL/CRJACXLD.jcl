//CRJACXLD JOB (CRDM,ACX,003),
//         'CRM EXPOSURE ORA LOAD',
//         CLASS=A,MSGCLASS=X,MSGLEVEL=(1,1),NOTIFY=&SYSUID
//*
//*================================================================
//* JOB    : CRJACXLD
//* SYSTEM : Credit Risk Data Mart - Accounts/Exposure Oracle ingest
//* PURPOSE: BPXBATCH triggers load_acx.ksh which runs SQL*Plus to
//*          define the external table over CR_ACX_VALID_*.dat and
//*          load CR_STAGE.ACCOUNT_EXPOSURE_STG.
//*================================================================
//STEP010  EXEC PGM=BPXBATCH,
//         PARM='SH /app/crm/scripts/load_acx.ksh',
//         COND=(4,LT)
//STDOUT   DD SYSOUT=*
//STDERR   DD SYSOUT=*
//STDENV   DD *
ORACLE_SID=CRMP
ORACLE_HOME=/opt/oracle/product/19c
CRM_LOAD_DIR=/app/crm/load
/*
//*
