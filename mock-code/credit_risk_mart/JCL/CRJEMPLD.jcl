//CRJEMPLD JOB (CRDM,EMP,003),
//         'CRM RM ORA LOAD',
//         CLASS=A,MSGCLASS=X,MSGLEVEL=(1,1),NOTIFY=&SYSUID
//*
//*================================================================
//* JOB    : CRJEMPLD
//* SYSTEM : Credit Risk Data Mart - Employees (RM) Oracle ingest
//* PURPOSE: BPXBATCH triggers load_emp.ksh which runs SQL*Plus to
//*          define the external table over CR_EMP_VALID_*.dat and
//*          load CR_STAGE.RM_PORTFOLIO_STG.
//*================================================================
//STEP010  EXEC PGM=BPXBATCH,
//         PARM='SH /app/crm/scripts/load_emp.ksh',
//         COND=(4,LT)
//STDOUT   DD SYSOUT=*
//STDERR   DD SYSOUT=*
//STDENV   DD *
ORACLE_SID=CRMP
ORACLE_HOME=/opt/oracle/product/19c
CRM_LOAD_DIR=/app/crm/load
/*
//*
