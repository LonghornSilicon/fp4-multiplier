"""Verify LonghornSilicon's 64-gate solution on our eval_circuit harness."""
from __future__ import annotations
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from eval_circuit import FP4_TABLE, evaluate_fast

# σ = (0,1,2,3,6,7,4,5): magnitude-permutation remap.
# Their code in submission/colab_paste.py uses (in their ml_dtypes encoding):
#   0   -> 0000
#   0.5 -> 0001
#   1   -> 0010
#   1.5 -> 0011
#   2   -> 0110
#   3   -> 0111
#   4   -> 0100
#   6   -> 0101
# Sign at bit 3.

# Build INPUT_REMAP for our harness (list[int] indexed by FP4_TABLE position).
# FP4_TABLE order is [0, 0.5, 1, 1.5, 2, 3, 4, 6, 0, -0.5, -1, -1.5, -2, -3, -4, -6].
_mag_to_code = {
    0.0: 0b0000,
    0.5: 0b0001,
    1.0: 0b0010,
    1.5: 0b0011,
    2.0: 0b0110,
    3.0: 0b0111,
    4.0: 0b0100,
    6.0: 0b0101,
}
INPUT_REMAP = []
for v in FP4_TABLE:
    s = 1 if v < 0 else 0
    INPUT_REMAP.append((s << 3) | _mag_to_code[abs(v)])


def write_your_multiplier_here(a0, a1, a2, a3, b0, b1, b2, b3,
                                NOT=None, AND=None, OR=None, XOR=None):
    if NOT is None:
        NOT = lambda x: not x
        AND = lambda x, y: x & y
        OR  = lambda x, y: x | y
        XOR = lambda x, y: x ^ y

    # Their convention: a[3]=sign, a[0]=LSB. Our convention: a0=MSB=sign, a3=LSB.
    # Rebind so the gate body sees their convention natively.
    a0, a1, a2, a3 = a3, a2, a1, a0
    b0, b1, b2, b3 = b3, b2, b1, b0

    w_35 = AND(a1, a2)
    w_32 = AND(b1, b2)
    w_68 = XOR(w_35, w_32)
    w_22 = OR(w_68, w_35)
    w_67 = XOR(a2, b2)
    w_37 = XOR(w_22, w_67)
    w_36 = AND(a2, b2)
    w_65 = OR(w_37, w_36)
    w_42 = AND(a0, b0)
    not_68 = NOT(w_68)
    w_43 = AND(w_42, not_68)
    w_45 = XOR(w_65, w_43)
    not_45 = NOT(w_45)
    w_66 = OR(w_68, w_42)
    w_33 = OR(b1, b2)
    w_39 = OR(a1, a2)
    w_38 = AND(w_33, w_39)
    w_11 = AND(w_66, w_38)
    w_53 = XOR(w_37, w_11)
    w_41 = AND(b0, w_39)
    w_13 = AND(a0, w_33)
    w_48 = XOR(w_41, w_13)
    w_25 = XOR(w_42, w_45)
    w_73 = AND(w_48, w_68)
    w_21 = XOR(w_25, w_73)
    w_58 = XOR(w_48, w_21)
    w_26 = XOR(w_37, w_58)
    w_47 = OR(w_53, w_26)
    not_47 = NOT(w_47)
    w_40 = XOR(w_73, w_38)
    w_55 = XOR(w_40, w_53)
    not_55 = NOT(w_55)
    not_58 = NOT(w_58)
    not_65 = NOT(w_65)
    w_34 = XOR(a3, b3)
    w_15 = XOR(w_37, w_25)
    w_46 = AND(w_45, w_15)
    w_50 = AND(w_43, w_15)
    y0 = AND(not_65, w_43)
    w_57 = AND(w_25, not_55)
    w_10 = AND(w_34, w_57)
    w_18 = AND(w_55, not_45)
    w_28 = AND(w_34, w_18)
    w_64 = AND(not_58, w_47)
    w_59 = AND(w_34, w_64)
    w_71 = AND(w_65, not_47)
    w_69 = AND(w_58, not_65)
    w_24 = OR(y0, w_69)
    w_70 = AND(w_34, w_24)
    y2 = XOR(w_18, w_70)
    w_61 = AND(w_43, w_70)
    w_14 = OR(w_28, w_70)
    y3 = XOR(w_64, w_14)
    w_49 = OR(w_59, w_14)
    y4 = XOR(w_57, w_49)
    w_17 = OR(w_49, w_10)
    y5 = XOR(w_17, w_71)
    w_52 = OR(w_17, w_71)
    w_51 = AND(w_34, w_52)
    w_56 = OR(w_26, w_51)
    y8 = AND(w_34, w_56)
    y7 = XOR(w_50, y8)
    y6 = XOR(w_46, w_51)
    y1 = XOR(w_69, w_61)

    # eval_circuit expects MSB-first 9-tuple
    return y8, y7, y6, y5, y4, y3, y2, y1, y0


if __name__ == "__main__":
    correct, gc, errs = evaluate_fast(write_your_multiplier_here, INPUT_REMAP)
    print(f"Gates: {gc}")
    print(f"Correct: {correct}")
    print(f"Errors: {len(errs)}")
    if errs:
        for e in errs[:5]: print(" ", e)
