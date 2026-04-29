"""
FP4×FP4 → QI9 multiplier: 63 gates.

Gate breakdown: 5 NOT1 + 24 AND2 + 12 OR2 + 22 XOR2 = 63 total.
Found by: eSLIM --syn-mode sat --size 10 --seed 1024 on the 5-NOT 64-gate
variant (which itself came from XOR re-association perturbation of Longhorn's
canonical 64-gate BLIF via eSLIM --size 6 --seed 7777).

Verified 256/256 correct via eval_circuit.evaluate_fast with the σ INPUT_REMAP.
"""

# σ remap (Longhorn's permutation): maps FP4 magnitude codes to 4-bit indices.
# Original Etched encoding: 2→0b0100, 3→0b0101, 4→0b0110, 6→0b0111
# Longhorn's σ encoding:    2→0b0110, 3→0b0111, 4→0b0100, 6→0b0101  (σ swaps bits 4-7)
from eval_circuit import FP4_TABLE
_sigma = {
    0.0: 0b0000, 0.5: 0b0001, 1.0: 0b0010, 1.5: 0b0011,
    2.0: 0b0110, 3.0: 0b0111, 4.0: 0b0100, 6.0: 0b0101,
}
INPUT_REMAP = []
for _v in FP4_TABLE:
    _s = 1 if _v < 0 else 0
    INPUT_REMAP.append((_s << 3) | _sigma[abs(_v)])


def write_your_multiplier_here(a0, a1, a2, a3, b0, b1, b2, b3,
                                NOT=None, AND=None, OR=None, XOR=None):
    if NOT is None:
        NOT = lambda x: not x
        AND = lambda x, y: x & y
        OR  = lambda x, y: x | y
        XOR = lambda x, y: x ^ y

    # Remap to Longhorn's bit convention:
    #   their a[3]=sign=a0_notebook, a[0]=LSB=a3_notebook
    a0, a1, a2, a3 = a3, a2, a1, a0
    b0, b1, b2, b3 = b3, b2, b1, b0

    # 63-gate body (5 NOT1, 24 AND2, 12 OR2, 22 XOR2)
    w_28 = AND(b1, b2)
    w_29 = OR(b1, b2)
    w_30 = XOR(a3, b3)
    w_32 = AND(a2, b2)
    w_31 = XOR(a2, b2)
    w_33 = AND(a1, a2)
    w_34 = XOR(w_28, w_33)
    w_35 = OR(w_33, w_28)
    w_36 = XOR(w_31, w_35)
    w_45 = OR(w_32, w_36)
    w_25 = w_45
    w_37 = OR(a1, a2)
    w_38 = AND(b0, w_37)
    w_39 = AND(w_29, w_37)
    w_40 = AND(a0, b0)
    w_41 = OR(w_34, w_40)
    w_42 = AND(w_41, w_39)
    w_43 = XOR(w_36, w_42)
    w_44 = XOR(w_34, w_41)
    w_46 = XOR(w_44, w_45)
    y0 = AND(w_46, w_44)
    w_49 = AND(w_30, y0)
    w_47 = XOR(w_40, w_46)
    w_16 = XOR(w_36, w_47)
    w_48 = AND(w_46, w_16)
    w_50 = AND(w_44, w_16)
    w_51 = AND(a0, w_29)
    w_52 = XOR(w_51, w_38)
    w_53 = AND(w_34, w_52)
    w_54 = XOR(w_47, w_53)
    w_55 = XOR(w_43, w_53)
    w_20 = XOR(w_55, w_39)
    w_21 = w_20
    w_22 = XOR(w_52, w_54)
    w_64 = XOR(w_22, w_36)
    w_18 = OR(w_64, w_43)
    w_19 = w_18
    w_60 = XOR(w_22, w_49)
    w_23 = w_22
    not_19 = NOT(w_19)
    not_21 = NOT(w_21)
    not_23 = NOT(w_23)
    not_25 = NOT(w_25)
    not_46 = NOT(w_46)
    w_56 = AND(not_46, w_20)
    w_57 = AND(w_30, w_56)
    w_58 = AND(w_47, not_21)
    w_59 = AND(w_30, w_58)
    w_65 = AND(not_19, w_47)
    w_66 = AND(w_30, w_65)
    y1 = AND(not_25, w_60)
    w_61 = OR(y0, y1)
    w_62 = AND(w_30, w_61)
    y2 = XOR(w_56, w_62)
    w_63 = OR(w_57, w_62)
    w_67 = AND(not_23, w_18)
    w_68 = OR(w_67, w_63)
    w_69 = AND(w_30, w_68)
    y4 = XOR(w_58, w_69)
    w_70 = OR(w_59, w_69)
    y5 = XOR(w_65, w_70)
    w_71 = OR(w_66, w_70)
    y6 = XOR(w_48, w_71)
    w_72 = AND(w_30, y6)
    y8 = OR(w_72, w_71)
    y7 = XOR(y8, w_50)
    y3 = XOR(w_67, w_63)

    # Return MSB first: y8 (bit 8) .. y0 (bit 0)
    return (y8, y7, y6, y5, y4, y3, y2, y1, y0)
