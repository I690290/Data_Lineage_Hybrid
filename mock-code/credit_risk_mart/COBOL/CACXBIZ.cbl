      *================================================================
      * PROGRAM  : CACXBIZ  (Layer 3 - Business Logic)
      * SYSTEM   : Credit Risk Data Mart - Accounts/Exposure pipeline
      * PURPOSE  : Derives the regulatory Basel credit-risk measures for
      *            every open account exposure fetched by CACXDAO:
      *
      *              EAD = DRAWN + (UNDRAWN * CCF) + ACCRUED INTEREST
      *                    (CCF looked up by product via SEARCH ALL)
      *              LGD = collateral base rate (SEARCH ALL on collateral
      *                    code) scaled by the macro downturn adjustment
      *              PD  = bucketed from delinquency + bureau score via an
      *                    EVALUATE decision table -> RISK STATUS + PD RATE
      *              EL  = EAD * PD * LGD  (Expected Loss)
      *
      *            Pence balances are converted to GBP first; net exposure
      *            is BALANCE - COLLATERAL.
      *
      * CALLED BY: CACXCTL (CALL 'CACXBIZ' USING WS-ACX-COMM)
      * CALLS    : CACXDAO (DB2 fetch)
      *================================================================
       IDENTIFICATION DIVISION.
       PROGRAM-ID. CACXBIZ.
       AUTHOR. CREDIT-RISK-BATCH.

       ENVIRONMENT DIVISION.

       DATA DIVISION.
       WORKING-STORAGE SECTION.
       01  WS-ACX-COMM.
       COPY ACXCOMM.

      *    Credit Conversion Factor lookup (undrawn weighting by product)
      *    each row: 4-char product + 5-digit factor in basis points
       01  WS-CCF-TABLE-DATA.
           05  FILLER  PIC X(9) VALUE 'CARD05000'.
           05  FILLER  PIC X(9) VALUE 'LOAN10000'.
           05  FILLER  PIC X(9) VALUE 'MORT07500'.
           05  FILLER  PIC X(9) VALUE 'OVDR07500'.
       01  WS-CCF-TABLE REDEFINES WS-CCF-TABLE-DATA.
           05  WS-CCF-ENTRY OCCURS 4 TIMES
                            ASCENDING KEY IS CCF-PRODUCT
                            INDEXED BY CCF-IDX.
               10  CCF-PRODUCT      PIC X(4).
               10  CCF-FACTOR-BPS   PIC 9(5).

      *    Collateral LGD base-rate lookup (unsecured default = 4500 bps)
      *    each row: 2-char collateral code + 4-digit rate in basis points
       01  WS-LGD-TABLE-DATA.
           05  FILLER  PIC X(6) VALUE 'CA0150'.
           05  FILLER  PIC X(6) VALUE 'GU0250'.
           05  FILLER  PIC X(6) VALUE 'RE0100'.
           05  FILLER  PIC X(6) VALUE 'SE0350'.
       01  WS-LGD-TABLE REDEFINES WS-LGD-TABLE-DATA.
           05  WS-LGD-ENTRY OCCURS 4 TIMES
                            ASCENDING KEY IS LGD-COLL-CODE
                            INDEXED BY LGD-IDX.
               10  LGD-COLL-CODE    PIC X(2).
               10  LGD-FACTOR-BPS   PIC 9(4).

       01  WS-WORK-AREAS.
           05  WS-CCF-FACTOR-BPS    PIC 9(5)  VALUE ZERO.
           05  WS-LGD-FACTOR-BPS    PIC 9(4)  VALUE ZERO.

       LINKAGE SECTION.
       01  LK-ACX-COMM.
       COPY ACXCOMM.

       PROCEDURE DIVISION USING LK-ACX-COMM.
      *================================================================
       MAIN-PARA.
           MOVE LK-ACX-COMM TO WS-ACX-COMM.
           CALL 'CACXDAO' USING WS-ACX-COMM.
           IF AXC-RETURN-CODE = ZERO
               PERFORM DERIVE-EXPOSURE-PARA
               PERFORM DERIVE-EAD-PARA
               PERFORM DERIVE-LGD-PARA
               PERFORM DERIVE-PD-PARA
               PERFORM DERIVE-EXPECTED-LOSS-PARA
           END-IF.
           MOVE WS-ACX-COMM TO LK-ACX-COMM.
           GOBACK.

      *================================================================
      * Pence -> GBP conversions and net exposure / utilisation.
      *================================================================
       DERIVE-EXPOSURE-PARA.
           COMPUTE AXC-BALANCE-GBP    = AXC-BALANCE-PENCE    / 100.
           COMPUTE AXC-LIMIT-GBP      = AXC-LIMIT-PENCE      / 100.
           COMPUTE AXC-COLLATERAL-GBP = AXC-COLLATERAL-PENCE / 100.
           COMPUTE AXC-DRAWN-GBP      = AXC-DRAWN-PENCE      / 100.
           COMPUTE AXC-UNDRAWN-GBP    = AXC-UNDRAWN-PENCE    / 100.
           COMPUTE AXC-ACCRUED-GBP    = AXC-ACCRUED-PENCE    / 100.
           SUBTRACT AXC-COLLATERAL-GBP FROM AXC-BALANCE-GBP
               GIVING AXC-NET-EXPOSURE-GBP.
           IF AXC-LIMIT-GBP > ZERO
               COMPUTE AXC-UTILISATION-PCT ROUNDED =
                   AXC-BALANCE-GBP / AXC-LIMIT-GBP * 100
           ELSE
               MOVE ZERO TO AXC-UTILISATION-PCT
           END-IF.

      *================================================================
      * EAD = DRAWN + (UNDRAWN * CCF) + ACCRUED.
      * The CCF is looked up by product from WS-CCF-TABLE (SEARCH ALL).
      *================================================================
       DERIVE-EAD-PARA.
           SEARCH ALL WS-CCF-ENTRY
               AT END
                   MOVE 10000 TO WS-CCF-FACTOR-BPS
               WHEN CCF-PRODUCT (CCF-IDX) = AXC-PRODUCT
                   MOVE CCF-FACTOR-BPS (CCF-IDX) TO WS-CCF-FACTOR-BPS
           END-SEARCH.
           COMPUTE AXC-CCF-RATE = WS-CCF-FACTOR-BPS / 10000.
           COMPUTE AXC-EAD-GBP =
               AXC-DRAWN-GBP +
               (AXC-UNDRAWN-GBP * AXC-CCF-RATE) +
               AXC-ACCRUED-GBP
           ON SIZE ERROR
               PERFORM 9000-MATH-ERROR-RTN
           END-COMPUTE.

      *================================================================
      * LGD = collateral base rate (SEARCH ALL by collateral code) scaled
      * by the macro downturn adjustment (basis points -> rate).
      *================================================================
       DERIVE-LGD-PARA.
           SEARCH ALL WS-LGD-ENTRY
               AT END
                   MOVE 4500 TO WS-LGD-FACTOR-BPS
               WHEN LGD-COLL-CODE (LGD-IDX) = AXC-COLLATERAL-CODE
                   MOVE LGD-FACTOR-BPS (LGD-IDX) TO WS-LGD-FACTOR-BPS
           END-SEARCH.
           COMPUTE AXC-LGD-BASE-RATE = WS-LGD-FACTOR-BPS / 10000.
           COMPUTE AXC-MACRO-ADJ     = AXC-MACRO-ADJ-BPS  / 10000.
           COMPUTE AXC-FINAL-LGD ROUNDED =
               AXC-LGD-BASE-RATE * AXC-MACRO-ADJ.

      *================================================================
      * PD bucketing: delinquency + bureau score -> RISK STATUS + PD RATE.
      *================================================================
       DERIVE-PD-PARA.
           EVALUATE TRUE
               WHEN AXC-DAYS-PAST-DUE > 90
                   MOVE 'DEFAULT' TO AXC-RISK-STATUS
                   MOVE 1.0000    TO AXC-PD-RATE
               WHEN AXC-DAYS-PAST-DUE > 30
                    AND AXC-BUREAU-SCORE < 500
                   MOVE 'HIGH'    TO AXC-RISK-STATUS
                   MOVE 0.1500    TO AXC-PD-RATE
               WHEN AXC-BUREAU-SCORE >= 750
                   MOVE 'LOW'     TO AXC-RISK-STATUS
                   MOVE 0.0100    TO AXC-PD-RATE
               WHEN OTHER
                   MOVE 'MEDIUM'  TO AXC-RISK-STATUS
                   MOVE 0.0500    TO AXC-PD-RATE
           END-EVALUATE.

      *================================================================
      * Expected Loss = EAD * PD * LGD.
      *================================================================
       DERIVE-EXPECTED-LOSS-PARA.
           COMPUTE AXC-EXPECTED-LOSS-GBP ROUNDED =
               AXC-EAD-GBP * AXC-PD-RATE * AXC-FINAL-LGD
           ON SIZE ERROR
               PERFORM 9000-MATH-ERROR-RTN
           END-COMPUTE.

      *================================================================
       9000-MATH-ERROR-RTN.
           MOVE ZERO TO AXC-EAD-GBP.
           MOVE ZERO TO AXC-EXPECTED-LOSS-GBP.
