"""
FP4×FP4 → QI9 Multiplier — Current Best Circuit (88 gates)

Run: python eval_circuit.py autoresearch/multiplier.py
     python autoresearch/run.py

Gate count history:
  135 → v1 (canonical M-E encoding, structural)
  126 → v2 (shared K×shift precomputation)
  101 → v3 (direct formula, no subtractor)
   89 → v4  (zero=000 encoding + K-flag masking)
   88 → v4b (+ sh6=u11 decoder optimization)

---

Encoding (4-bit code = sign | a1 a2 a3):
  magnitude code 000 → zero (both +0 and -0)
  magnitude code 001 → 1.5  (M=1, E=0,  E'=1)
  magnitude code 010 → 3.0  (M=1, E=1,  E'=2)
  magnitude code 011 → 6.0  (M=1, E=2,  E'=3)
  magnitude code 100 → 0.5  (M=0, E=-1, E'=0)
  magnitude code 101 → 1.0  (M=0, E=0,  E'=1)
  magnitude code 110 → 2.0  (M=0, E=1,  E'=2)
  magnitude code 111 → 4.0  (M=0, E=2,  E'=3)

Key mathematical structure:
  All non-zero FP4 magnitudes = 1.5^M × 2^E, M∈{0,1}, E∈{-1,0,1,2}.
  Product magnitude = 1.5^M_sum × 2^S, where:
    M_sum = M_a + M_b ∈ {0,1,2}   (K-type: 1, 3/2, 9/4)
    S = E'_a + E'_b ∈ {0,...,6}   (shift, E'=E+1)
  Output bit i: m_i = (not_k9 ∧ S=i) ∨ (k3 ∧ S=i+1) ∨ (k9 ∧ S=i-1) ∨ (k9 ∧ S=i+2)

Gate breakdown:
  sign:        1   XOR(a0,b0)
  nz detect:   5   OR trees for non-zero detection
  E-sum:       7   2-bit adder for (a2,a3)+(b2,b3)
  K-flags:     3   OR(a1,b1), NOT, XOR(a1,b1)
  K-masking:   3   AND each K-flag with nz
  S decoder:  13   3 NOT + 4 pair-AND + 6 sh (sh6=u11 saves 1 vs naive 14)
  AND-terms:  18   7 nmc×sh + 6 k3×sh + 5 k9×sh
  Mag bits:   15   OR assembly for 8 magnitude output bits
  Cond neg:   22   carry chain (r8=m0 pass-through saves 1 gate)
  Sign mask:   1   AND(sign, nz)
  ─────────────────
  Total:      88
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

    # sign
    sign = XOR(a0, b0)

    # non-zero detection (nz=1 iff both inputs non-zero)
    or_a23 = OR(a2, a3);   nz_a = OR(a1, or_a23)
    or_b23 = OR(b2, b3);   nz_b = OR(b1, or_b23)
    nz = AND(nz_a, nz_b)

    # E-sum: S = (a2,a3) + (b2,b3), 3-bit
    s0  = XOR(a3, b3);  c0  = AND(a3, b3)
    s1x = XOR(a2, b2);  s1  = XOR(s1x, c0)
    s2  = OR(AND(a2, b2), AND(s1x, c0))

    # K-flags (M=NOT(a1); k9=NOR(a1,b1), k3=XOR(a1,b1), not_k9=OR(a1,b1))
    or_a1b1 = OR(a1, b1)
    k9_raw  = NOT(or_a1b1)
    k3_raw  = XOR(a1, b1)

    # Mask K-flags with nz → all magnitude bits auto-zero when any input is zero
    nmc = AND(or_a1b1, nz)   # not_k9 × nz
    k3  = AND(k3_raw,  nz)
    k9  = AND(k9_raw,  nz)

    # S decoder (one-hot, S∈{0..6}; sh6=u11 since S≤6 guarantees s0=0 when u11=1)
    ns0 = NOT(s0);  ns1 = NOT(s1);  ns2 = NOT(s2)

    u00 = AND(ns2, ns1);  u01 = AND(ns2, s1)
    u10 = AND(s2, ns1);   u11 = AND(s2, s1)   # sh6 = u11

    sh0 = AND(u00, ns0);  sh1 = AND(u00, s0)
    sh2 = AND(u01, ns0);  sh3 = AND(u01, s0)
    sh4 = AND(u10, ns0);  sh5 = AND(u10, s0)

    # AND-terms: K × sh_j
    nmc0 = AND(nmc, sh0);  nmc1 = AND(nmc, sh1);  nmc2 = AND(nmc, sh2)
    nmc3 = AND(nmc, sh3);  nmc4 = AND(nmc, sh4);  nmc5 = AND(nmc, sh5)
    nmc6 = AND(nmc, u11)

    k3_1 = AND(k3, sh1);  k3_2 = AND(k3, sh2);  k3_3 = AND(k3, sh3)
    k3_4 = AND(k3, sh4);  k3_5 = AND(k3, sh5);  k3_6 = AND(k3, u11)

    k9_2 = AND(k9, sh2);  k9_3 = AND(k9, sh3);  k9_4 = AND(k9, sh4)
    k9_5 = AND(k9, sh5);  k9_6 = AND(k9, u11)

    # Magnitude bits: m_i = nmc_i OR k3_{i+1} OR k9_{i-1} OR k9_{i+2}
    m7 = k9_6
    m6 = OR(nmc6, k9_5)
    m5 = OR(nmc5, OR(k3_6, k9_4))
    m4 = OR(OR(nmc4, k3_5), OR(k9_6, k9_3))
    m3 = OR(OR(nmc3, k3_4), OR(k9_5, k9_2))
    m2 = OR(nmc2, OR(k3_3, k9_4))
    m1 = OR(nmc1, OR(k3_2, k9_3))
    m0 = OR(nmc0, OR(k3_1, k9_2))

    # Conditional 2's complement negation (LSB pass-through: r8=m0 always)
    t0 = XOR(m0, sign);  r8 = m0;            c1 = AND(t0, sign)
    t1 = XOR(m1, sign);  r7 = XOR(t1, c1);  c2 = AND(t1, c1)
    t2 = XOR(m2, sign);  r6 = XOR(t2, c2);  c3 = AND(t2, c2)
    t3 = XOR(m3, sign);  r5 = XOR(t3, c3);  c4 = AND(t3, c3)
    t4 = XOR(m4, sign);  r4 = XOR(t4, c4);  c5 = AND(t4, c4)
    t5 = XOR(m5, sign);  r3 = XOR(t5, c5);  c6 = AND(t5, c5)
    t6 = XOR(m6, sign);  r2 = XOR(t6, c6);  c7 = AND(t6, c6)
    t7 = XOR(m7, sign);  r1 = XOR(t7, c7)

    # Sign masking (magnitude auto-zeros via K-masking; only sign bit needs mask)
    res0 = AND(sign, nz)

    return res0, r1, r2, r3, r4, r5, r6, r7, r8
