      *================================================================
      * COPYBOOK : CREXPOSR
      * SYSTEM   : Credit Risk - MI5021 Counterparty Default Risk
      * PURPOSE  : Counterparty exposure communication area shared
      *            between CRRSKMST (caller) and CRRSKSUB (callee).
      *            Both programs expand this copybook under their own
      *            01 level, so the field names are identical on both
      *            sides of the CALL ... USING boundary.
      *================================================================
           05  EXP-CPTY-ID             PIC X(15).
           05  EXP-TOTAL-EXPOSURE      PIC S9(13)V99 COMP-3.
           05  EXP-COLLATERAL-VALUE    PIC S9(13)V99 COMP-3.
           05  EXP-EXPOSURE-CCY        PIC X(3).
           05  EXP-RETURN-CODE         PIC S9(4) COMP.
