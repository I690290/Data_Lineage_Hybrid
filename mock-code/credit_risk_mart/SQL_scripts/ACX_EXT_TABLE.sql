-- ================================================================
-- SCRIPT  : ACX_EXT_TABLE.sql
-- SYSTEM  : Credit Risk Data Mart - Accounts/Exposure pipeline
-- PURPOSE : Oracle External Table over the validated account
--           exposure .dat feed (CR_ACX_VALID_*.dat, output of CACXDQA).
--           Now carries the regulatory EAD / LGD / PD / Expected-Loss
--           metrics derived on the mainframe by CACXBIZ.
-- SCHEMA  : CR_STAGE     DIR OBJ : CRM_LOAD_DIR
-- ================================================================

CREATE TABLE "CR_STAGE"."ACCOUNT_EXPOSURE_EXT"
   (
    ACCOUNT_NUMBER     VARCHAR2(8),
    SORT_CODE          VARCHAR2(6),
    CUST_ID            VARCHAR2(15),
    PRODUCT_CODE       VARCHAR2(4),
    BALANCE_GBP        VARCHAR2(17),
    CREDIT_LIMIT_GBP   VARCHAR2(17),
    COLLATERAL_GBP     VARCHAR2(17),
    NET_EXPOSURE_GBP   VARCHAR2(17),
    UTILISATION_PCT    VARCHAR2(6),
    ARREARS_DAYS       VARCHAR2(4),
    DEFAULT_FLAG       VARCHAR2(1),
    EAD_GBP            VARCHAR2(17),
    LGD_BASE_RATE      VARCHAR2(6),
    FINAL_LGD          VARCHAR2(6),
    PD_RATE            VARCHAR2(6),
    RISK_STATUS        VARCHAR2(8),
    EXPECTED_LOSS_GBP  VARCHAR2(17)
   )
   ORGANIZATION EXTERNAL
    ( TYPE ORACLE_LOADER
      DEFAULT DIRECTORY "CRM_LOAD_DIR"
      ACCESS PARAMETERS
      ( RECORDS FIXED 172
        FIELDS
        ( ACCOUNT_NUMBER    POSITION(1:8)     CHAR(8),
          SORT_CODE         POSITION(9:14)    CHAR(6),
          CUST_ID           POSITION(15:29)   CHAR(15),
          PRODUCT_CODE      POSITION(30:33)   CHAR(4),
          BALANCE_GBP       POSITION(34:50)   CHAR(17),
          CREDIT_LIMIT_GBP  POSITION(51:67)   CHAR(17),
          COLLATERAL_GBP    POSITION(68:84)   CHAR(17),
          NET_EXPOSURE_GBP  POSITION(85:101)  CHAR(17),
          UTILISATION_PCT   POSITION(102:107) CHAR(6),
          ARREARS_DAYS      POSITION(108:111) CHAR(4),
          DEFAULT_FLAG      POSITION(112:112) CHAR(1),
          EAD_GBP           POSITION(113:129) CHAR(17),
          LGD_BASE_RATE     POSITION(130:135) CHAR(6),
          FINAL_LGD         POSITION(136:141) CHAR(6),
          PD_RATE           POSITION(142:147) CHAR(6),
          RISK_STATUS       POSITION(148:155) CHAR(8),
          EXPECTED_LOSS_GBP POSITION(156:172) CHAR(17)
        )
      )
      LOCATION ( 'CR_ACX_VALID_20260622.dat' )
    )
   REJECT LIMIT UNLIMITED;
