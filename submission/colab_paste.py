# ============================================================================
# PASTE-IN BLOCK 1: replaces the INPUT_REMAP cell
# ============================================================================
# Remap sigma = (0, 1, 2, 3, 6, 7, 4, 5):
#   codes 0b0100..0b0111 carry magnitudes 4, 6, 2, 3 (instead of default 2, 3, 4, 6).
#   Sign bit (MSB) preserved. Magnitudes 0, 0.5, 1, 1.5 stay at codes 0..3.
# Identical to the prior 64-gate canonical: the sigma remap is shared, only
# the gate body differs.
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
# 63-gate body: 5 NOT + 24 AND + 12 OR + 22 XOR. Verified 256/256.
# Found by: eSLIM --syn-mode sat --size 10 --seed 1024 on a 5-NOT
# 64-gate variant, which itself came from XOR re-association
# perturbation of the canonical 64-gate via eSLIM --size 6 --seed 7777.

def write_your_multiplier_here(a0, a1, a2, a3, b0, b1, b2, b3):
    # Notebook convention: a0=sign (MSB of code), a3=mantissa (LSB of code).
    # Our circuit was synthesized with a[0]=LSB ... a[3]=sign. Rebind so the
    # gate body below uses the synthesized convention natively.
    a0, a1, a2, a3 = a3, a2, a1, a0
    b0, b1, b2, b3 = b3, b2, b1, b0

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
    w_22 = XOR(w_52, w_54)
    w_64 = XOR(w_22, w_36)
    w_18 = OR(w_64, w_43)
    w_60 = XOR(w_22, w_49)
    not_18 = NOT(w_18)
    not_20 = NOT(w_20)
    not_22 = NOT(w_22)
    not_45 = NOT(w_45)
    not_46 = NOT(w_46)
    w_56 = AND(not_46, w_20)
    w_57 = AND(w_30, w_56)
    w_58 = AND(w_47, not_20)
    w_59 = AND(w_30, w_58)
    w_65 = AND(not_18, w_47)
    w_66 = AND(w_30, w_65)
    y1 = AND(not_45, w_60)
    w_61 = OR(y0, y1)
    w_62 = AND(w_30, w_61)
    y2 = XOR(w_56, w_62)
    w_63 = OR(w_57, w_62)
    w_67 = AND(not_22, w_18)
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

    # res0 = MSB (sign), res8 = LSB (0.25 place value).
    return y8, y7, y6, y5, y4, y3, y2, y1, y0
