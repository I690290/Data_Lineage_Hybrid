-- ================================================================
-- SCRIPT  : TXN_EXT_TABLE.sql
-- SYSTEM  : Credit Risk Data Mart - Transactions pipeline
-- PURPOSE : Oracle External Table over the validated transaction
--           .dat feed delivered from the mainframe (CR_TXN_VALID_*.dat,
--           fixed-position FB output of CTXNDQA).
-- SCHEMA  : CR_STAGE     DIR OBJ : CRM_LOAD_DIR
-- ================================================================

CREATE TABLE "CR_STAGE"."TXN_TRANSACTIONS_EXT"
   (
    TXN_REF            VARCHAR2(18),
    ACCOUNT_NUMBER     VARCHAR2(8),
    SORT_CODE          VARCHAR2(6),
    TXN_TYPE_CODE      VARCHAR2(4),
    MERCHANT_CAT_CODE  VARCHAR2(4),
    POSTING_DATE       VARCHAR2(10),
    CURRENCY_CODE      VARCHAR2(3),
    TXN_AMOUNT_GBP     VARCHAR2(15),
    RISK_WEIGHT        VARCHAR2(6),
    FCA_REPORTABLE     VARCHAR2(1)
   )
   ORGANIZATION EXTERNAL
    ( TYPE ORACLE_LOADER
      DEFAULT DIRECTORY "CRM_LOAD_DIR"
      ACCESS PARAMETERS
      ( RECORDS FIXED 80
        FIELDS
        ( TXN_REF           POSITION(1:18)   CHAR(18),
          ACCOUNT_NUMBER    POSITION(19:26)  CHAR(8),
          SORT_CODE         POSITION(27:32)  CHAR(6),
          TXN_TYPE_CODE     POSITION(33:36)  CHAR(4),
          MERCHANT_CAT_CODE POSITION(37:40)  CHAR(4),
          POSTING_DATE      POSITION(41:50)  CHAR(10),
          CURRENCY_CODE     POSITION(51:53)  CHAR(3),
          TXN_AMOUNT_GBP    POSITION(54:68)  CHAR(15),
          RISK_WEIGHT       POSITION(69:74)  CHAR(6),
          FCA_REPORTABLE    POSITION(75:75)  CHAR(1)
        )
      )
      LOCATION ( 'CR_TXN_VALID_20260622.dat' )
    )
   REJECT LIMIT UNLIMITED;
