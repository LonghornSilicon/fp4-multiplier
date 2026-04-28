"""
v4f — 81 gates.

Reduction from v4e (82): k9 was AND(NOT(or_a1b1), nz). The NOT(or_a1b1) gate
is removable because k9 has the same care-set bitvector as XOR(nz, nmc):
  nmc = AND(or_a1b1, nz)
  nz XOR nmc = nz AND NOT(or_a1b1) = k9
The dedicated NOT gate gets DCE'd. Saves 1 gate.

Discovered by `sa_resub.py` — exhaustive bit-parallel resubstitution search
over single-gate replacements (constants, BUF, NOT, AND/OR/XOR of any earlier
node pair) restricted to the 225-input care set.
"""

from eval_circuit import FP4_TABLE

INPUT_REMAP = []
_mag_to_code = {
    0.0: 0b000, 1.5: 0b001, 3.0: 0b010, 6.0: 0b011,
    0.5: 0b100, 1.0: 0b101, 2.0: 0b110, 4.0: 0b111,
}
for _v in FP4_TABLE:
    _sign = 1 if _v < 0 else 0
    INPUT_REMAP.append((_sign << 3) | _mag_to_code[abs(_v)])


def write_your_multiplier_here(a0, a1, a2, a3, b0, b1, b2, b3,
                                NOT=None, AND=None, OR=None, XOR=None):
    if NOT is None:
        NOT = lambda x: not x
        AND = lambda x, y: x & y
        OR  = lambda x, y: x | y
        XOR = lambda x, y: x ^ y

    sign = XOR(a0, b0)

    or_a23 = OR(a2, a3);   nz_a = OR(a1, or_a23)
    or_b23 = OR(b2, b3);   nz_b = OR(b1, or_b23)
    nz = AND(nz_a, nz_b)

    s0  = XOR(a3, b3);  c0  = AND(a3, b3)
    s1x = XOR(a2, b2);  s1  = XOR(s1x, c0)
    s2  = OR(AND(a2, b2), AND(s1x, c0))

    or_a1b1 = OR(a1, b1)
    k3_raw  = XOR(a1, b1)

    nmc = AND(or_a1b1, nz)     # = (a1|b1) & nz
    k3  = AND(k3_raw,  nz)
    k9  = XOR(nz, nmc)         # = nz & NOT(a1|b1) — saves the dedicated NOT gate

    _or01 = OR(s2, s1);   _or012 = OR(s0, _or01)
    sh0   = NOT(_or012)
    sh1   = XOR(_or01, _or012)
    _xor2 = XOR(s0, _or012)
    _and2 = AND(s2, _xor2)
    sh3   = AND(s1, s0)
    sh5   = AND(s2, s0)
    sh2   = XOR(_xor2, _and2)
    sh6   = AND(s1, _and2)
    sh4   = XOR(_and2, sh6)

    nmc0 = AND(nmc, sh0);  nmc1 = AND(nmc, sh1);  nmc2 = AND(nmc, sh2)
    nmc3 = AND(nmc, sh3);  nmc4 = AND(nmc, sh4);  nmc5 = AND(nmc, sh5)
    nmc6 = AND(nmc, sh6)

    k3_1 = AND(k3, sh1);  k3_2 = AND(k3, sh2);  k3_3 = AND(k3, sh3)
    k3_4 = AND(k3, sh4);  k3_5 = AND(k3, sh5);  k3_6 = AND(k3, sh6)

    k9_2 = AND(k9, sh2);  k9_3 = AND(k9, sh3);  k9_4 = AND(k9, sh4)
    k9_5 = AND(k9, sh5);  k9_6 = AND(k9, sh6)

    m7 = k9_6
    m6 = OR(nmc6, k9_5)
    m5 = OR(nmc5, OR(k3_6, k9_4))
    m4 = OR(OR(nmc4, k3_5), OR(k9_6, k9_3))
    m3 = OR(OR(nmc3, k3_4), OR(k9_5, k9_2))
    m2 = OR(nmc2, OR(k3_3, k9_4))
    m1 = OR(nmc1, OR(k3_2, k9_3))
    m0 = OR(nmc0, OR(k3_1, k9_2))

    res0 = AND(sign, nz)

    p2 = OR(m0, m1);   p3 = OR(p2, m2);   p4 = OR(p3, m3)
    p5 = OR(p4, m4);   p6 = OR(p5, m5)

    sp1 = AND(sign, m0)
    sp2 = AND(sign, p2);  sp3 = AND(sign, p3);  sp4 = AND(sign, p4)
    sp5 = AND(sign, p5);  sp6 = AND(sign, p6)

    r8 = m0
    r7 = XOR(m1, sp1);  r6 = XOR(m2, sp2);  r5 = XOR(m3, sp3)
    r4 = XOR(m4, sp4);  r3 = XOR(m5, sp5);  r2 = XOR(m6, sp6)
    r1 = XOR(m7, res0)

    return res0, r1, r2, r3, r4, r5, r6, r7, r8
