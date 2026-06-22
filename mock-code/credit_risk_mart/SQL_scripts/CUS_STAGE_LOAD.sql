-- ================================================================
-- SCRIPT  : CUS_STAGE_LOAD.sql
-- SYSTEM  : Credit Risk Data Mart - Customers pipeline
-- PURPOSE : Staging table DDL + load procedure. Reads CUSTOMER_EXT
--           and loads CUSTOMER_STG. CUST_ID mutates to CUSTOMER_ID_STG.
-- ================================================================

CREATE TABLE "CR_STAGE"."CUSTOMER_STG"
(
    CUSTOMER_ID_STG        VARCHAR2(15)  NOT NULL,
    CUSTOMER_NAME_STG      VARCHAR2(51),
    DATE_OF_BIRTH_STG      DATE,
    SORT_CODE_STG          VARCHAR2(6),
    KYC_STATUS_STG         VARCHAR2(2),
    CREDIT_RISK_TIER_STG   VARCHAR2(1),
    PEP_FLAG_STG           VARCHAR2(1),
    VULNERABLE_FLAG_STG    VARCHAR2(1),
    LOAD_DATE              DATE DEFAULT SYSDATE
);

CREATE OR REPLACE PROCEDURE "CR_STAGE"."PRC_LOAD_CUS_STG"
AS
BEGIN
    INSERT INTO "CR_STAGE"."CUSTOMER_STG"
    (
        CUSTOMER_ID_STG, CUSTOMER_NAME_STG, DATE_OF_BIRTH_STG,
        SORT_CODE_STG, KYC_STATUS_STG, CREDIT_RISK_TIER_STG,
        PEP_FLAG_STG, VULNERABLE_FLAG_STG, LOAD_DATE
    )
    SELECT
        TRIM(e.CUST_ID)                                AS CUSTOMER_ID_STG,
        TRIM(e.FULL_NAME)                              AS CUSTOMER_NAME_STG,
        TO_DATE(TRIM(e.DATE_OF_BIRTH), 'YYYY-MM-DD')   AS DATE_OF_BIRTH_STG,
        TRIM(e.SORT_CODE)                              AS SORT_CODE_STG,
        TRIM(e.KYC_STATUS)                             AS KYC_STATUS_STG,
        TRIM(e.CREDIT_RISK_TIER)                       AS CREDIT_RISK_TIER_STG,
        TRIM(e.PEP_FLAG)                               AS PEP_FLAG_STG,
        TRIM(e.VULNERABLE_FLAG)                        AS VULNERABLE_FLAG_STG,
        SYSDATE                                        AS LOAD_DATE
    FROM "CR_STAGE"."CUSTOMER_EXT" e
    WHERE TRIM(e.CUST_ID) IS NOT NULL;

    COMMIT;
END PRC_LOAD_CUS_STG;
/
