#!/bin/ksh
# ================================================================
# SCRIPT  : load_txn.ksh
# SYSTEM  : Credit Risk Data Mart - Transactions Oracle ingest
# PURPOSE : Invoked by JCL CRJTXNLD via BPXBATCH. Runs SQL*Plus to
#           (1) (re)create the external table over the delivered
#           CR_TXN_VALID_*.dat and (2) load the staging table via
#           PRC_LOAD_TXN_STG.
# ================================================================
set -e
SCRIPTDIR=/app/crm/scripts/sql
LOGDIR=/app/crm/log

sqlplus -s /nolog <<-SQLEOF
    CONNECT cr_stage/${CR_STAGE_PWD}@${ORACLE_SID}
    WHENEVER SQLERROR EXIT FAILURE
    SET SERVEROUTPUT ON
    @${SCRIPTDIR}/TXN_EXT_TABLE.sql
    EXEC CR_STAGE.PRC_LOAD_TXN_STG;
    EXIT
SQLEOF

echo "load_txn.ksh complete rc=$?"
