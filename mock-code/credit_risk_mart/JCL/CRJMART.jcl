//CRJMART  JOB (CRDM,MART,001),
//         'CRM MODEL BUILD',
//         CLASS=A,MSGCLASS=X,MSGLEVEL=(1,1),NOTIFY=&SYSUID
//*
//*================================================================
//* JOB    : CRJMART
//* SYSTEM : Credit Risk Data Mart - final modelling
//* PURPOSE: Master modelling trigger. BPXBATCH runs build_model.ksh
//*          which calls SQL*Plus to execute the PL/SQL procedure
//*          CR_MART.PRC_BUILD_CREDIT_RISK_MODEL. The procedure reads
//*          the four staging tables (TXN / CUS / EMP / ACX), builds
//*          intermediate temporary tables and joins them into the
//*          unified CR_MART.CREDIT_RISK_MODEL reporting table.
//*
//* SCHEDULE : Daily, Mon-Fri, 05:00 EST
//* DEPENDS  : CRJTXNLD, CRJCUSLD, CRJEMPLD, CRJACXLD complete
//*================================================================
//STEP010  EXEC PGM=BPXBATCH,
//         PARM='SH /app/crm/scripts/build_model.ksh',
//         COND=(4,LT)
//STDOUT   DD SYSOUT=*
//STDERR   DD SYSOUT=*
//STDENV   DD *
ORACLE_SID=CRMP
ORACLE_HOME=/opt/oracle/product/19c
/*
//*
