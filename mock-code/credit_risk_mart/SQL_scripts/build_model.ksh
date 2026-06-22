#!/bin/ksh
# ================================================================
# SCRIPT  : build_model.ksh
# SYSTEM  : Credit Risk Data Mart - final modelling
# PURPOSE : Invoked by JCL CRJMART via BPXBATCH. Runs SQL*Plus to
#           execute the master modelling procedure
#           CR_MART.PRC_BUILD_CREDIT_RISK_MODEL, which joins the four
#           staging tables into CR_MART.CREDIT_RISK_MODEL.
# ================================================================
set -e

sqlplus -s /nolog <<-SQLEOF
    CONNECT cr_mart/${CR_MART_PWD}@${ORACLE_SID}
    WHENEVER SQLERROR EXIT FAILURE
    SET SERVEROUTPUT ON
    EXEC CR_MART.PRC_BUILD_CREDIT_RISK_MODEL;
    EXIT
SQLEOF

echo "build_model.ksh complete rc=$?"
