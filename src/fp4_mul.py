# FP4 Multiplier — 64-gate canonical solution
# Cell breakdown: 25 AND2 + 12 OR2 + 21 XOR2 + 6 NOT1 = 64
# Verified: 256/256 input pairs

# Input remap: positive magnitudes [0, 0.5, 1, 1.5, 2, 3, 4, 6]
# permuted by sigma=(0,1,2,3,6,7,4,5) -> [0, 0.5, 1, 1.5, 4, 6, 2, 3].
# Sign bit (MSB of 4-bit code) gives the negative copies.
INPUT_REMAP = [0, 0.5, 1, 1.5, 4, 6, 2, 3, 0.0, -0.5, -1, -1.5, -4, -6, -2, -3]

# Two-input gates from the contest library + free 1-bit NOT.
# (If your notebook already defines these, delete the next 4 lines.)
def AND(x, y): return x & y
def OR(x, y):  return x | y
def XOR(x, y): return x ^ y
def NOT(x):    return 1 - x

def write_your_multiplier_here(a, b):
    """
    a, b: each is a list of 4 bits, [a0, a1, a2, a3] where a0 is the LSB
          and a3 is the sign bit (the 4-bit code in standard low-to-high order).
    Returns: list of 9 bits [y0..y8] where y0 is the LSB (= 0.25) and y8 is
             the sign bit of the 9-bit two's complement output (representing
             4 * remap(a) * remap(b)).
    """
    a0, a1, a2, a3 = a[0], a[1], a[2], a[3]
    b0, b1, b2, b3 = b[0], b[1], b[2], b[3]

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
    y = [y0, y1, y2, y3, y4, y5, y6, y7, y8]
    return y  # y[0] is LSB (represents 0.25), y[8] is MSB (sign)
