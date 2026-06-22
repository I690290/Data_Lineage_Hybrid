-- ================================================================
-- SCRIPT  : EMP_STAGE_LOAD.sql
-- SYSTEM  : Credit Risk Data Mart - Employees (RM) pipeline
-- PURPOSE : Staging table DDL + load procedure. Reads RM_PORTFOLIO_EXT
--           and loads RM_PORTFOLIO_STG. EMP_ID mutates to RM_EMP_ID_STG.
-- ================================================================

CREATE TABLE "CR_STAGE"."RM_PORTFOLIO_STG"
(
    RM_EMP_ID_STG          VARCHAR2(8)   NOT NULL,
    RM_NAME_STG            VARCHAR2(40),
    BRANCH_SORT_CODE_STG   VARCHAR2(6),
    ROLE_CODE_STG          VARCHAR2(4),
    RM_TIER_STG            VARCHAR2(2),
    PORTFOLIO_VALUE_GBP_STG NUMBER(16,2),
    FCA_CERTIFIED_STG      VARCHAR2(1),
    START_DATE_STG         DATE,
    LOAD_DATE              DATE DEFAULT SYSDATE
);

CREATE OR REPLACE PROCEDURE "CR_STAGE"."PRC_LOAD_EMP_STG"
AS
BEGIN
    INSERT INTO "CR_STAGE"."RM_PORTFOLIO_STG"
    (
        RM_EMP_ID_STG, RM_NAME_STG, BRANCH_SORT_CODE_STG,
        ROLE_CODE_STG, RM_TIER_STG, PORTFOLIO_VALUE_GBP_STG,
        FCA_CERTIFIED_STG, START_DATE_STG, LOAD_DATE
    )
    SELECT
        TRIM(e.EMP_ID)                                 AS RM_EMP_ID_STG,
        TRIM(e.EMP_NAME)                               AS RM_NAME_STG,
        TRIM(e.BRANCH_SORT_CODE)                       AS BRANCH_SORT_CODE_STG,
        TRIM(e.ROLE_CODE)                              AS ROLE_CODE_STG,
        TRIM(e.RM_TIER)                                AS RM_TIER_STG,
        TO_NUMBER(TRIM(e.PORTFOLIO_GBP))               AS PORTFOLIO_VALUE_GBP_STG,
        TRIM(e.FCA_CERTIFIED)                          AS FCA_CERTIFIED_STG,
        TO_DATE(TRIM(e.START_DATE), 'YYYY-MM-DD')      AS START_DATE_STG,
        SYSDATE                                        AS LOAD_DATE
    FROM "CR_STAGE"."RM_PORTFOLIO_EXT" e
    WHERE TRIM(e.EMP_ID) IS NOT NULL;

    COMMIT;
END PRC_LOAD_EMP_STG;
/
