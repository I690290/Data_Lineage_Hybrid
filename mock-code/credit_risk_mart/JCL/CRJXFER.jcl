//CRJXFER  JOB (CRDM,XFER,001),
//         'CRM DAT TRANSFER',
//         CLASS=A,MSGCLASS=X,MSGLEVEL=(1,1),NOTIFY=&SYSUID
//*
//*================================================================
//* JOB    : CRJXFER
//* SYSTEM : Credit Risk Data Mart - file transfer
//* PURPOSE: FTP the four validated .dat feeds to the Oracle UNIX
//*          server load directory. The remote file names are
//*          date-stamped using the JCL system symbolic &DATE -
//*          the physical target name is only resolved at submit
//*          time, so static parsing cannot determine it (flagged
//*          for the AI edge-resolution layer as a dynamic symbolic).
//*================================================================
//STEP010  EXEC PGM=FTP,
//         PARM='oracle-crm-server (EXIT',
//         COND=(4,LT)
//SYSPRINT DD SYSOUT=*
//OUTPUT   DD SYSOUT=*
//INPUT    DD *
 ascii
 cd /app/crm/load
 put 'CRDM.TXN.VALID.DAT' CR_TXN_VALID_&DATE..dat
 put 'CRDM.CUS.VALID.DAT' CR_CUS_VALID_&DATE..dat
 put 'CRDM.EMP.VALID.DAT' CR_EMP_VALID_&DATE..dat
 put 'CRDM.ACX.VALID.DAT' CR_ACX_VALID_&DATE..dat
 quit
/*
//*
