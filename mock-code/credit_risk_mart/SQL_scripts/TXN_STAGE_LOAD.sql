-- ================================================================
-- SCRIPT  : TXN_STAGE_LOAD.sql
-- SYSTEM  : Credit Risk Data Mart - Transactions pipeline
-- PURPOSE : Staging table DDL + load procedure. Reads the external
--           table TXN_TRANSACTIONS_EXT and loads the typed staging
--           table TXN_TRANSACTIONS_STG (column names mutate with a
--           _STG suffix; VARCHAR2 cast to native types).
-- ================================================================

CREATE TABLE "CR_STAGE"."TXN_TRANSACTIONS_STG"
(
    TXN_REF_STG            VARCHAR2(18)  NOT NULL,
    ACCOUNT_NUMBER_STG     VARCHAR2(8)   NOT NULL,
    SORT_CODE_STG          VARCHAR2(6)   NOT NULL,
    TXN_TYPE_CD_STG        VARCHAR2(4),
    MERCHANT_CAT_CD_STG    VARCHAR2(4),
    POSTING_DATE_STG       DATE,
    CCY_STG                VARCHAR2(3),
    TXN_AMOUNT_GBP_STG     NUMBER(15,2),
    RISK_WEIGHT_STG        NUMBER(5,4),
    FCA_REPORTABLE_STG     VARCHAR2(1),
    LOAD_DATE              DATE DEFAULT SYSDATE
);

CREATE OR REPLACE PROCEDURE "CR_STAGE"."PRC_LOAD_TXN_STG"
AS
BEGIN
    INSERT INTO "CR_STAGE"."TXN_TRANSACTIONS_STG"
    (
        TXN_REF_STG, ACCOUNT_NUMBER_STG, SORT_CODE_STG,
        TXN_TYPE_CD_STG, MERCHANT_CAT_CD_STG, POSTING_DATE_STG,
        CCY_STG, TXN_AMOUNT_GBP_STG, RISK_WEIGHT_STG,
        FCA_REPORTABLE_STG, LOAD_DATE
    )
    SELECT
        TRIM(e.TXN_REF)                              AS TXN_REF_STG,
        TRIM(e.ACCOUNT_NUMBER)                       AS ACCOUNT_NUMBER_STG,
        TRIM(e.SORT_CODE)                            AS SORT_CODE_STG,
        TRIM(e.TXN_TYPE_CODE)                        AS TXN_TYPE_CD_STG,
        TRIM(e.MERCHANT_CAT_CODE)                    AS MERCHANT_CAT_CD_STG,
        TO_DATE(TRIM(e.POSTING_DATE), 'YYYY-MM-DD')  AS POSTING_DATE_STG,
        TRIM(e.CURRENCY_CODE)                        AS CCY_STG,
        TO_NUMBER(TRIM(e.TXN_AMOUNT_GBP))            AS TXN_AMOUNT_GBP_STG,
        TO_NUMBER(TRIM(e.RISK_WEIGHT))               AS RISK_WEIGHT_STG,
        TRIM(e.FCA_REPORTABLE)                       AS FCA_REPORTABLE_STG,
        SYSDATE                                      AS LOAD_DATE
    FROM "CR_STAGE"."TXN_TRANSACTIONS_EXT" e
    WHERE TRIM(e.ACCOUNT_NUMBER) IS NOT NULL;

    COMMIT;
END PRC_LOAD_TXN_STG;
/
