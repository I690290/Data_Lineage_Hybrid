-- ================================================================
-- SCRIPT  : EMP_EXT_TABLE.sql
-- SYSTEM  : Credit Risk Data Mart - Employees (RM) pipeline
-- PURPOSE : Oracle External Table over the validated relationship-
--           manager .dat feed (CR_EMP_VALID_*.dat, output of CEMPDQA).
-- SCHEMA  : CR_STAGE     DIR OBJ : CRM_LOAD_DIR
-- ================================================================

CREATE TABLE "CR_STAGE"."RM_PORTFOLIO_EXT"
   (
    EMP_ID             VARCHAR2(8),
    EMP_NAME           VARCHAR2(40),
    BRANCH_SORT_CODE   VARCHAR2(6),
    ROLE_CODE          VARCHAR2(4),
    RM_TIER            VARCHAR2(2),
    PORTFOLIO_GBP      VARCHAR2(15),
    FCA_CERTIFIED      VARCHAR2(1),
    START_DATE         VARCHAR2(10)
   )
   ORGANIZATION EXTERNAL
    ( TYPE ORACLE_LOADER
      DEFAULT DIRECTORY "CRM_LOAD_DIR"
      ACCESS PARAMETERS
      ( RECORDS FIXED 86
        FIELDS
        ( EMP_ID           POSITION(1:8)    CHAR(8),
          EMP_NAME         POSITION(9:48)   CHAR(40),
          BRANCH_SORT_CODE POSITION(49:54)  CHAR(6),
          ROLE_CODE        POSITION(55:58)  CHAR(4),
          RM_TIER          POSITION(59:60)  CHAR(2),
          PORTFOLIO_GBP    POSITION(61:75)  CHAR(15),
          FCA_CERTIFIED    POSITION(76:76)  CHAR(1),
          START_DATE       POSITION(77:86)  CHAR(10)
        )
      )
      LOCATION ( 'CR_EMP_VALID_20260622.dat' )
    )
   REJECT LIMIT UNLIMITED;
