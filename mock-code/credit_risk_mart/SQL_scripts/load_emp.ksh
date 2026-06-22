#!/bin/ksh
# ================================================================
# SCRIPT  : load_emp.ksh
# SYSTEM  : Credit Risk Data Mart - Employees (RM) Oracle ingest
# PURPOSE : Invoked by JCL CRJEMPLD via BPXBATCH. Runs SQL*Plus to
#           create the external table over CR_EMP_VALID_*.dat and
#           load the staging table via PRC_LOAD_EMP_STG.
# ================================================================
set -e
SCRIPTDIR=/app/crm/scripts/sql

sqlplus -s /nolog <<-SQLEOF
    CONNECT cr_stage/${CR_STAGE_PWD}@${ORACLE_SID}
    WHENEVER SQLERROR EXIT FAILURE
    SET SERVEROUTPUT ON
    @${SCRIPTDIR}/EMP_EXT_TABLE.sql
    EXEC CR_STAGE.PRC_LOAD_EMP_STG;
    EXIT
SQLEOF

echo "load_emp.ksh complete rc=$?"
