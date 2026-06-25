      *================================================================
      * COPYBOOK : ACXCOMM
      * SYSTEM   : Credit Risk Data Mart - Accounts/Exposure pipeline
      * PURPOSE  : Shared communication area for the MVC chain
      *            CACXDRV -> CACXCTL -> CACXBIZ -> CACXDAO.
      *            CACXDAO fills the raw pence balances and Basel risk
      *            drivers from DB2; CACXBIZ converts pence to GBP and
      *            derives the regulatory credit-risk measures:
      *              EAD (Exposure At Default), LGD (Loss Given Default),
      *              PD (Probability of Default) and Expected Loss.
      *================================================================
           05  AXC-RETURN-CODE        PIC S9(4) COMP.
           05  AXC-ACCOUNT-NUMBER     PIC X(8).
           05  AXC-SORT-CODE          PIC X(6).
           05  AXC-CUST-ID            PIC X(15).
           05  AXC-PRODUCT            PIC X(4).
           05  AXC-BALANCE-PENCE      PIC S9(15) COMP-3.
           05  AXC-LIMIT-PENCE        PIC S9(15) COMP-3.
           05  AXC-COLLATERAL-PENCE   PIC S9(15) COMP-3.
           05  AXC-ARREARS-DAYS       PIC S9(4) COMP.
           05  AXC-DEFAULT-FLAG       PIC X(1).
      *    Raw Basel risk drivers fetched from DB2 (CACXDAO)
           05  AXC-DRAWN-PENCE        PIC S9(15) COMP-3.
           05  AXC-UNDRAWN-PENCE      PIC S9(15) COMP-3.
           05  AXC-ACCRUED-PENCE      PIC S9(15) COMP-3.
           05  AXC-DAYS-PAST-DUE      PIC S9(4) COMP.
           05  AXC-BUREAU-SCORE       PIC S9(4) COMP.
           05  AXC-COLLATERAL-CODE    PIC X(2).
           05  AXC-MACRO-ADJ-BPS      PIC S9(4) COMP.
      *    Exposure measures derived by the business layer (CACXBIZ)
           05  AXC-BALANCE-GBP        PIC S9(13)V99 COMP-3.
           05  AXC-LIMIT-GBP          PIC S9(13)V99 COMP-3.
           05  AXC-COLLATERAL-GBP     PIC S9(13)V99 COMP-3.
           05  AXC-NET-EXPOSURE-GBP   PIC S9(13)V99 COMP-3.
           05  AXC-UTILISATION-PCT    PIC S9(3)V99 COMP-3.
           05  AXC-DRAWN-GBP          PIC S9(13)V99 COMP-3.
           05  AXC-UNDRAWN-GBP        PIC S9(13)V99 COMP-3.
           05  AXC-ACCRUED-GBP        PIC S9(13)V99 COMP-3.
      *    Regulatory credit-risk measures (EAD / LGD / PD / EL)
           05  AXC-CCF-RATE           PIC S9V9(4) COMP-3.
           05  AXC-EAD-GBP            PIC S9(15)V99 COMP-3.
           05  AXC-LGD-BASE-RATE      PIC S9V9(4) COMP-3.
           05  AXC-MACRO-ADJ          PIC S9V9(4) COMP-3.
           05  AXC-FINAL-LGD          PIC S9V9(4) COMP-3.
           05  AXC-PD-RATE            PIC S9V9(4) COMP-3.
           05  AXC-RISK-STATUS        PIC X(8).
           05  AXC-EXPECTED-LOSS-GBP  PIC S9(15)V99 COMP-3.
