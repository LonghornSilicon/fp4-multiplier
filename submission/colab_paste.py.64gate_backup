# ============================================================================
# PASTE-IN BLOCK 1: replaces the INPUT_REMAP cell
# ============================================================================
# Remap sigma = (0, 1, 2, 3, 6, 7, 4, 5):
#   codes 0b0100..0b0111 carry magnitudes 4, 6, 2, 3 (instead of default 2, 3, 4, 6).
#   Sign bit (MSB) preserved. Magnitudes 0, 0.5, 1, 1.5 stay at codes 0..3.
INPUT_REMAP = {
    float4_e2m1fn(0):    uint4(0b0000),
    float4_e2m1fn(0.5):  uint4(0b0001),
    float4_e2m1fn(1):    uint4(0b0010),
    float4_e2m1fn(1.5):  uint4(0b0011),
    float4_e2m1fn(2):    uint4(0b0110),
    float4_e2m1fn(3):    uint4(0b0111),
    float4_e2m1fn(4):    uint4(0b0100),
    float4_e2m1fn(6):    uint4(0b0101),
    float4_e2m1fn(-0.0): uint4(0b0000),
    float4_e2m1fn(-0.5): uint4(0b1001),
    float4_e2m1fn(-1):   uint4(0b1010),
    float4_e2m1fn(-1.5): uint4(0b1011),
    float4_e2m1fn(-2):   uint4(0b1110),
    float4_e2m1fn(-3):   uint4(0b1111),
    float4_e2m1fn(-4):   uint4(0b1100),
    float4_e2m1fn(-6):   uint4(0b1101),
}


# ============================================================================
# PASTE-IN BLOCK 2: replaces the write_your_multiplier_here cell
# ============================================================================
# 64-gate canonical: 25 AND + 12 OR + 21 XOR + 6 NOT. Verified 256/256.

def write_your_multiplier_here(a0, a1, a2, a3, b0, b1, b2, b3):
    # Notebook convention: a0=sign (MSB of code), a3=mantissa (LSB of code).
    # Our circuit was synthesized with a[0]=LSB ... a[3]=sign. Rebind so the
    # gate body below uses the synthesized convention natively.
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

    # res0 = MSB (sign), res8 = LSB (0.25 place value).
    return y8, y7, y6, y5, y4, y3, y2, y1, y0

