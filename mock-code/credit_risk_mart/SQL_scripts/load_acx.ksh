#!/bin/ksh
# ================================================================
# SCRIPT  : load_acx.ksh
# SYSTEM  : Credit Risk Data Mart - Accounts/Exposure Oracle ingest
# PURPOSE : Invoked by JCL CRJACXLD via BPXBATCH. Runs SQL*Plus to
#           create the external table over CR_ACX_VALID_*.dat and
#           load the staging table via PRC_LOAD_ACX_STG.
# ================================================================
set -e
SCRIPTDIR=/app/crm/scripts/sql

sqlplus -s /nolog <<-SQLEOF
    CONNECT cr_stage/${CR_STAGE_PWD}@${ORACLE_SID}
    WHENEVER SQLERROR EXIT FAILURE
    SET SERVEROUTPUT ON
    @${SCRIPTDIR}/ACX_EXT_TABLE.sql
    EXEC CR_STAGE.PRC_LOAD_ACX_STG;
    EXIT
SQLEOF

echo "load_acx.ksh complete rc=$?"
