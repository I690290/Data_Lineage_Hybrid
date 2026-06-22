-- ================================================================
-- SCRIPT  : CUS_EXT_TABLE.sql
-- SYSTEM  : Credit Risk Data Mart - Customers pipeline
-- PURPOSE : Oracle External Table over the validated customer .dat
--           feed (CR_CUS_VALID_*.dat, fixed-position output of
--           CCUSDQA).
-- SCHEMA  : CR_STAGE     DIR OBJ : CRM_LOAD_DIR
-- ================================================================

CREATE TABLE "CR_STAGE"."CUSTOMER_EXT"
   (
    CUST_ID            VARCHAR2(15),
    FULL_NAME          VARCHAR2(51),
    DATE_OF_BIRTH      VARCHAR2(10),
    SORT_CODE          VARCHAR2(6),
    KYC_STATUS         VARCHAR2(2),
    CREDIT_RISK_TIER   VARCHAR2(1),
    PEP_FLAG           VARCHAR2(1),
    VULNERABLE_FLAG    VARCHAR2(1)
   )
   ORGANIZATION EXTERNAL
    ( TYPE ORACLE_LOADER
      DEFAULT DIRECTORY "CRM_LOAD_DIR"
      ACCESS PARAMETERS
      ( RECORDS FIXED 87
        FIELDS
        ( CUST_ID          POSITION(1:15)   CHAR(15),
          FULL_NAME        POSITION(16:66)  CHAR(51),
          DATE_OF_BIRTH    POSITION(67:76)  CHAR(10),
          SORT_CODE        POSITION(77:82)  CHAR(6),
          KYC_STATUS       POSITION(83:84)  CHAR(2),
          CREDIT_RISK_TIER POSITION(85:85)  CHAR(1),
          PEP_FLAG         POSITION(86:86)  CHAR(1),
          VULNERABLE_FLAG  POSITION(87:87)  CHAR(1)
        )
      )
      LOCATION ( 'CR_CUS_VALID_20260622.dat' )
    )
   REJECT LIMIT UNLIMITED;
