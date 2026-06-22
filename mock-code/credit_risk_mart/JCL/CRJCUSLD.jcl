//CRJCUSLD JOB (CRDM,CUS,003),
//         'CRM CUST ORA LOAD',
//         CLASS=A,MSGCLASS=X,MSGLEVEL=(1,1),NOTIFY=&SYSUID
//*
//*================================================================
//* JOB    : CRJCUSLD
//* SYSTEM : Credit Risk Data Mart - Customers Oracle ingest
//* PURPOSE: BPXBATCH triggers load_cus.ksh which runs SQL*Plus to
//*          define the external table over CR_CUS_VALID_*.dat and
//*          load CR_STAGE.CUSTOMER_STG.
//*================================================================
//STEP010  EXEC PGM=BPXBATCH,
//         PARM='SH /app/crm/scripts/load_cus.ksh',
//         COND=(4,LT)
//STDOUT   DD SYSOUT=*
//STDERR   DD SYSOUT=*
//STDENV   DD *
ORACLE_SID=CRMP
ORACLE_HOME=/opt/oracle/product/19c
CRM_LOAD_DIR=/app/crm/load
/*
//*
