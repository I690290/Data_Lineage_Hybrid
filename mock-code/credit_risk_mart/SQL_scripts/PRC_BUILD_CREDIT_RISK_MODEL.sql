-- ================================================================
-- SCRIPT  : PRC_BUILD_CREDIT_RISK_MODEL.sql
-- SYSTEM  : Credit Risk Data Mart - final modelling layer
-- PURPOSE : Master modelling artefacts. Defines:
--             - four global temporary tables (one per source domain)
--             - the unified reporting table CREDIT_RISK_MODEL
--             - PRC_BUILD_CREDIT_RISK_MODEL which populates the temp
--               tables from the staging tables, then joins them into
--               CREDIT_RISK_MODEL.
--
-- GRAIN   : one row per open account exposure, enriched with the
--           owning customer, the branch relationship manager and the
--           account's 30-day transaction aggregate.
--
-- LINEAGE : CR_STAGE.ACCOUNT_EXPOSURE_STG  -> TMP_ACCOUNT_EXPOSURE
--           CR_STAGE.CUSTOMER_STG          -> TMP_CUSTOMER_RISK
--           CR_STAGE.RM_PORTFOLIO_STG      -> TMP_RM_PORTFOLIO
--           CR_STAGE.TXN_TRANSACTIONS_STG  -> TMP_TXN_AGG
--           (TMP_* joined) -> CR_MART.CREDIT_RISK_MODEL
-- ================================================================

-- ----------------------------------------------------------------
-- Intermediate temporary tables
-- ----------------------------------------------------------------
CREATE GLOBAL TEMPORARY TABLE "CR_MART"."TMP_CUSTOMER_RISK"
(
    CUSTOMER_KEY           VARCHAR2(15),
    CUSTOMER_FULL_NAME     VARCHAR2(51),
    CUSTOMER_RISK_TIER     VARCHAR2(1),
    SORT_CODE              VARCHAR2(6),
    VULNERABLE_FLAG        VARCHAR2(1)
) ON COMMIT PRESERVE ROWS;

CREATE GLOBAL TEMPORARY TABLE "CR_MART"."TMP_ACCOUNT_EXPOSURE"
(
    ACCOUNT_NUMBER         VARCHAR2(8),
    BRANCH_SORT_CODE       VARCHAR2(6),
    CUSTOMER_KEY           VARCHAR2(15),
    PRODUCT_CODE           VARCHAR2(4),
    ACCOUNT_BALANCE_GBP    NUMBER(15,2),
    CREDIT_LIMIT_GBP       NUMBER(15,2),
    NET_EXPOSURE_GBP       NUMBER(15,2),
    UTILISATION_PCT        NUMBER(5,2),
    ARREARS_DAYS           NUMBER(5),
    DEFAULT_FLAG           VARCHAR2(1)
) ON COMMIT PRESERVE ROWS;

CREATE GLOBAL TEMPORARY TABLE "CR_MART"."TMP_RM_PORTFOLIO"
(
    BRANCH_SORT_CODE       VARCHAR2(6),
    RM_EMP_ID              VARCHAR2(8),
    RM_PORTFOLIO_VALUE_GBP NUMBER(16,2)
) ON COMMIT PRESERVE ROWS;

CREATE GLOBAL TEMPORARY TABLE "CR_MART"."TMP_TXN_AGG"
(
    ACCOUNT_NUMBER         VARCHAR2(8),
    TXN_VOLUME_GBP_30D     NUMBER(18,2),
    TXN_COUNT_30D          NUMBER(9),
    FCA_REPORTABLE_FLAG    VARCHAR2(1)
) ON COMMIT PRESERVE ROWS;

-- ----------------------------------------------------------------
-- Unified reporting table
-- ----------------------------------------------------------------
CREATE TABLE "CR_MART"."CREDIT_RISK_MODEL"
(
    CUSTOMER_KEY           VARCHAR2(15) NOT NULL,
    CUSTOMER_FULL_NAME     VARCHAR2(51),
    CUSTOMER_RISK_TIER     VARCHAR2(1),
    BRANCH_SORT_CODE       VARCHAR2(6),
    ACCOUNT_NUMBER         VARCHAR2(8)  NOT NULL,
    PRODUCT_CODE           VARCHAR2(4),
    ACCOUNT_BALANCE_GBP    NUMBER(15,2),
    CREDIT_LIMIT_GBP       NUMBER(15,2),
    NET_EXPOSURE_GBP       NUMBER(15,2),
    UTILISATION_PCT        NUMBER(5,2),
    ARREARS_DAYS           NUMBER(5),
    TXN_VOLUME_GBP_30D     NUMBER(18,2),
    TXN_COUNT_30D          NUMBER(9),
    RM_EMP_ID              VARCHAR2(8),
    RM_PORTFOLIO_VALUE_GBP NUMBER(16,2),
    VULNERABLE_FLAG        VARCHAR2(1),
    FCA_REPORTABLE_FLAG    VARCHAR2(1),
    DEFAULT_FLAG           VARCHAR2(1),
    MODEL_RUN_DATE         DATE,
    CONSTRAINT PK_CREDIT_RISK_MODEL
        PRIMARY KEY (CUSTOMER_KEY, ACCOUNT_NUMBER)
);

-- ----------------------------------------------------------------
-- Master modelling procedure
-- ----------------------------------------------------------------
CREATE OR REPLACE PROCEDURE "CR_MART"."PRC_BUILD_CREDIT_RISK_MODEL"
AS
    v_rows NUMBER;
BEGIN
    -- 1. Customer risk dimension from the customer staging table
    INSERT INTO "CR_MART"."TMP_CUSTOMER_RISK"
        (CUSTOMER_KEY, CUSTOMER_FULL_NAME, CUSTOMER_RISK_TIER,
         SORT_CODE, VULNERABLE_FLAG)
    SELECT
        c.CUSTOMER_ID_STG,
        c.CUSTOMER_NAME_STG,
        c.CREDIT_RISK_TIER_STG,
        c.SORT_CODE_STG,
        c.VULNERABLE_FLAG_STG
    FROM "CR_STAGE"."CUSTOMER_STG" c;

    -- 2. Account exposure facts from the exposure staging table
    INSERT INTO "CR_MART"."TMP_ACCOUNT_EXPOSURE"
        (ACCOUNT_NUMBER, BRANCH_SORT_CODE, CUSTOMER_KEY, PRODUCT_CODE,
         ACCOUNT_BALANCE_GBP, CREDIT_LIMIT_GBP, NET_EXPOSURE_GBP,
         UTILISATION_PCT, ARREARS_DAYS, DEFAULT_FLAG)
    SELECT
        a.ACCOUNT_NUMBER_STG,
        a.SORT_CODE_STG,
        a.CUSTOMER_ID_STG,
        a.PRODUCT_CODE_STG,
        a.BALANCE_GBP_STG,
        a.CREDIT_LIMIT_GBP_STG,
        a.NET_EXPOSURE_GBP_STG,
        a.UTILISATION_PCT_STG,
        a.ARREARS_DAYS_STG,
        a.DEFAULT_FLAG_STG
    FROM "CR_STAGE"."ACCOUNT_EXPOSURE_STG" a;

    -- 3. Relationship manager portfolio (one RM per branch sort code)
    INSERT INTO "CR_MART"."TMP_RM_PORTFOLIO"
        (BRANCH_SORT_CODE, RM_EMP_ID, RM_PORTFOLIO_VALUE_GBP)
    SELECT
        r.BRANCH_SORT_CODE_STG,
        MAX(r.RM_EMP_ID_STG),
        SUM(r.PORTFOLIO_VALUE_GBP_STG)
    FROM "CR_STAGE"."RM_PORTFOLIO_STG" r
    GROUP BY r.BRANCH_SORT_CODE_STG;

    -- 4. 30-day transaction aggregate per account
    INSERT INTO "CR_MART"."TMP_TXN_AGG"
        (ACCOUNT_NUMBER, TXN_VOLUME_GBP_30D, TXN_COUNT_30D,
         FCA_REPORTABLE_FLAG)
    SELECT
        t.ACCOUNT_NUMBER_STG,
        SUM(t.TXN_AMOUNT_GBP_STG * t.RISK_WEIGHT_STG),
        COUNT(*),
        MAX(t.FCA_REPORTABLE_STG)
    FROM "CR_STAGE"."TXN_TRANSACTIONS_STG" t
    WHERE t.POSTING_DATE_STG >= TRUNC(SYSDATE) - 30
    GROUP BY t.ACCOUNT_NUMBER_STG;

    -- 5. Join all temporary tables into the unified model
    INSERT INTO "CR_MART"."CREDIT_RISK_MODEL"
        (CUSTOMER_KEY, CUSTOMER_FULL_NAME, CUSTOMER_RISK_TIER,
         BRANCH_SORT_CODE, ACCOUNT_NUMBER, PRODUCT_CODE,
         ACCOUNT_BALANCE_GBP, CREDIT_LIMIT_GBP, NET_EXPOSURE_GBP,
         UTILISATION_PCT, ARREARS_DAYS, TXN_VOLUME_GBP_30D,
         TXN_COUNT_30D, RM_EMP_ID, RM_PORTFOLIO_VALUE_GBP,
         VULNERABLE_FLAG, FCA_REPORTABLE_FLAG, DEFAULT_FLAG,
         MODEL_RUN_DATE)
    SELECT
        x.CUSTOMER_KEY,
        cu.CUSTOMER_FULL_NAME,
        cu.CUSTOMER_RISK_TIER,
        x.BRANCH_SORT_CODE,
        x.ACCOUNT_NUMBER,
        x.PRODUCT_CODE,
        x.ACCOUNT_BALANCE_GBP,
        x.CREDIT_LIMIT_GBP,
        x.NET_EXPOSURE_GBP,
        x.UTILISATION_PCT,
        x.ARREARS_DAYS,
        NVL(tx.TXN_VOLUME_GBP_30D, 0),
        NVL(tx.TXN_COUNT_30D, 0),
        rm.RM_EMP_ID,
        rm.RM_PORTFOLIO_VALUE_GBP,
        cu.VULNERABLE_FLAG,
        NVL(tx.FCA_REPORTABLE_FLAG, 'N'),
        x.DEFAULT_FLAG,
        TRUNC(SYSDATE)
    FROM "CR_MART"."TMP_ACCOUNT_EXPOSURE" x
    INNER JOIN "CR_MART"."TMP_CUSTOMER_RISK" cu
        ON cu.CUSTOMER_KEY = x.CUSTOMER_KEY
    LEFT JOIN "CR_MART"."TMP_RM_PORTFOLIO" rm
        ON rm.BRANCH_SORT_CODE = x.BRANCH_SORT_CODE
    LEFT JOIN "CR_MART"."TMP_TXN_AGG" tx
        ON tx.ACCOUNT_NUMBER = x.ACCOUNT_NUMBER;

    v_rows := SQL%ROWCOUNT;
    DBMS_OUTPUT.PUT_LINE('CREDIT_RISK_MODEL rows inserted: ' || v_rows);
    COMMIT;
END PRC_BUILD_CREDIT_RISK_MODEL;
/
