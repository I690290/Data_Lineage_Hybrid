-- ================================================================
-- SCRIPT  : MI4014_STAGE_LOAD.sql
-- SYSTEM  : Credit Risk Behaviour Scoring - Neptune Data Load
-- PURPOSE : Staging table DDL and load procedure for MI4014.
--           Loads from external table to internal staging table
--           with type-cast columns for downstream scoring.
--
-- DEPENDS ON: MI4014_EXT_TABLE.sql (external table must exist)
-- ================================================================

-- ----------------------------------------------------------------
-- Staging table: typed columns for Credit Risk scoring engine
-- ----------------------------------------------------------------
CREATE TABLE "BDD_NEPTUNE_DICC"."MI4014_TRANSACCIONES_STG"
(
    MAIN_ACCOUNT_NUMBER     VARCHAR2(20)    NOT NULL,
    SUB_ACCOUNT_NUMBER      VARCHAR2(10)    NOT NULL,
    COMPANY                 VARCHAR2(6),
    TRANSACTION_CODE        VARCHAR2(10),
    TRANSACTION_AMOUNT      NUMBER(15,2),
    TRANSACTION_GROUP       VARCHAR2(6),
    POSTED_DATE             DATE,
    EFFECTIVE_DATE          DATE,
    UNSECURED               VARCHAR2(1),
    NEW_MAIN_ACC_NUM        VARCHAR2(20),
    NEW_LOAN_ACC_NUM        VARCHAR2(20),
    -- ETL metadata columns
    LOAD_DATE               DATE            DEFAULT SYSDATE,
    SOURCE_FILE             VARCHAR2(100),
    LOAD_STATUS             VARCHAR2(1)     DEFAULT 'P'
        CHECK (LOAD_STATUS IN ('P','V','E','R'))
);

-- Primary key for downstream dedup
ALTER TABLE "BDD_NEPTUNE_DICC"."MI4014_TRANSACCIONES_STG"
    ADD CONSTRAINT PK_MI4014_STG
    PRIMARY KEY (MAIN_ACCOUNT_NUMBER, SUB_ACCOUNT_NUMBER,
                 TRANSACTION_CODE, POSTED_DATE, LOAD_DATE);

-- ----------------------------------------------------------------
-- PRC_MI4014_STAGE_LOAD
-- Stored procedure: load from external table into staging with
-- type conversion, then mark invalid-amount rows as Error.
-- All VARCHAR2 fields from external table cast to typed columns.
-- ----------------------------------------------------------------
CREATE OR REPLACE PROCEDURE "BDD_NEPTUNE_DICC"."PRC_MI4014_STAGE_LOAD"
AS
    v_ext_count   NUMBER;
    v_stg_count   NUMBER;
BEGIN
    INSERT /*+ APPEND PARALLEL(s,4) */
    INTO "BDD_NEPTUNE_DICC"."MI4014_TRANSACCIONES_STG" s
    (
        MAIN_ACCOUNT_NUMBER,
        SUB_ACCOUNT_NUMBER,
        COMPANY,
        TRANSACTION_CODE,
        TRANSACTION_AMOUNT,
        TRANSACTION_GROUP,
        POSTED_DATE,
        EFFECTIVE_DATE,
        UNSECURED,
        NEW_MAIN_ACC_NUM,
        NEW_LOAN_ACC_NUM,
        LOAD_DATE,
        SOURCE_FILE,
        LOAD_STATUS
    )
    SELECT
        TRIM(e.MAIN_ACCOUNT_NUMBER)                         AS MAIN_ACCOUNT_NUMBER,
        TRIM(e.SUB_ACCOUNT_NUMBER)                          AS SUB_ACCOUNT_NUMBER,
        TRIM(e.COMPANY)                                     AS COMPANY,
        TRIM(e.TRANSACTION_CODE)                            AS TRANSACTION_CODE,
        -- Amount: handle sign and strip spaces
        TO_NUMBER(TRIM(REPLACE(e.TRANSACTION_AMOUNT,' ','')),
                  'FM9999999999999.99')                     AS TRANSACTION_AMOUNT,
        TRIM(e.TRANSACTION_GROUP)                           AS TRANSACTION_GROUP,
        -- Dates: COBOL outputs YYYY-MM-DD format
        TO_DATE(TRIM(e.POSTED_DATE),    'YYYY-MM-DD')       AS POSTED_DATE,
        TO_DATE(TRIM(e.EFFECTIVE_DATE), 'YYYY-MM-DD')       AS EFFECTIVE_DATE,
        TRIM(e.UNSECURED)                                   AS UNSECURED,
        TRIM(e.NEW_MAIN_ACC_NUM)                            AS NEW_MAIN_ACC_NUM,
        TRIM(e.NEW_LOAN_ACC_NUM)                            AS NEW_LOAN_ACC_NUM,
        SYSDATE                                             AS LOAD_DATE,
        'MI4014_Transaction_Extract_TSB_NAM65_'
            || TO_CHAR(SYSDATE,'YYYYMMDD') || '.xml'        AS SOURCE_FILE,
        'P'                                                 AS LOAD_STATUS
    FROM "BDD_NEPTUNE_DICC"."MI4014_TRANSACCIONES_DIARIAS" e
    WHERE TRIM(e.MAIN_ACCOUNT_NUMBER) IS NOT NULL
      AND TRIM(e.TRANSACTION_CODE)    IS NOT NULL;

    COMMIT;

    -- ------------------------------------------------------------
    -- Post-load validation: mark records with invalid amounts as Error
    -- ------------------------------------------------------------
    UPDATE "BDD_NEPTUNE_DICC"."MI4014_TRANSACCIONES_STG"
    SET    LOAD_STATUS = 'E'
    WHERE  TRANSACTION_AMOUNT IS NULL
      AND  LOAD_DATE = TRUNC(SYSDATE);

    COMMIT;

    -- ------------------------------------------------------------
    -- Row count check for reconciliation
    -- ------------------------------------------------------------
    SELECT COUNT(*) INTO v_ext_count
    FROM   "BDD_NEPTUNE_DICC"."MI4014_TRANSACCIONES_DIARIAS";

    SELECT COUNT(*) INTO v_stg_count
    FROM   "BDD_NEPTUNE_DICC"."MI4014_TRANSACCIONES_STG"
    WHERE  LOAD_DATE >= TRUNC(SYSDATE);

    DBMS_OUTPUT.PUT_LINE('EXTERNAL_TABLE rows: ' || v_ext_count);
    DBMS_OUTPUT.PUT_LINE('STAGING_TABLE  rows: ' || v_stg_count);
END PRC_MI4014_STAGE_LOAD;
/
