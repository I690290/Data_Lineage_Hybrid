#!/bin/ksh
# ================================================================
# SCRIPT  : load_cus.ksh
# SYSTEM  : Credit Risk Data Mart - Customers Oracle ingest
# PURPOSE : Invoked by JCL CRJCUSLD via BPXBATCH. Runs SQL*Plus to
#           create the external table over CR_CUS_VALID_*.dat and
#           load the staging table via PRC_LOAD_CUS_STG.
# ================================================================
set -e
SCRIPTDIR=/app/crm/scripts/sql

sqlplus -s /nolog <<-SQLEOF
    CONNECT cr_stage/${CR_STAGE_PWD}@${ORACLE_SID}
    WHENEVER SQLERROR EXIT FAILURE
    SET SERVEROUTPUT ON
    @${SCRIPTDIR}/CUS_EXT_TABLE.sql
    EXEC CR_STAGE.PRC_LOAD_CUS_STG;
    EXIT
SQLEOF

echo "load_cus.ksh complete rc=$?"
