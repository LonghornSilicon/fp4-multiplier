"""
v4: Zero=000 encoding with K-flag masking — target 89 gates.

Key changes vs v3 (101 gates):
1. Zero → code 000 in magnitude (vs code 100 in v3)
   - Zero detection via NOR tree: 5 gates (vs 9 in v3)
   - Mask 3 K-flags with nz instead of 9 output bits: 3 gates (vs 10 in v3)
   → Saves 11 gates on zero overhead (19→8 total)

2. K-flag derivation differs (M = NOT(a1) in new encoding):
   - not_k9 = OR(a1, b1):  1 gate
   - k9_raw = NOT(or_a1b1): 1 gate
   - k3_raw = XOR(a1, b1): 1 gate
   → 3 gates total K-flags (vs 4 in v3)

3. LSB of conditional negation r8 = m0 always (2's complement
   preserves LSB), so the XOR for r8 is free (pass-through).
   → Saves 1 gate in cond_neg (23→22)

Encoding (magnitude code a1 a2 a3, a1=MSB):
  000 = zero     (M=1* but masked by nz — auto-zero via K-masking)
  001 = 1.5      (M=1, E=0,  E'=(a2,a3)=01=1)
  010 = 3.0      (M=1, E=1,  E'=10=2)
  011 = 6.0      (M=1, E=2,  E'=11=3)
  100 = 0.5      (M=0, E=-1, E'=00=0)
  101 = 1.0      (M=0, E=0,  E'=01=1)
  110 = 2.0      (M=0, E=1,  E'=10=2)
  111 = 4.0      (M=0, E=2,  E'=11=3)

M = NOT(a1) for non-zero; E' = (a2, a3) for all.

K-flags (where M_a = NOT(a1), M_b = NOT(b1)):
  k9 (M_sum=2) = AND(NOT a1, NOT b1) = NOR(a1, b1)
  k3 (M_sum=1) = XOR(NOT a1, NOT b1) = XOR(a1, b1)
  not_k9        = OR(a1, b1)

Formula (same as v3):
  mag_bit_i = (not_k9 AND S==i) OR (k3 AND S==i+1) OR
              (k9 AND S==i+2)   OR (k9 AND S==i-1)
All K-flags are AND-ed with nz before use → auto-zero when input is 0.

Gate count breakdown:
  sign:            1
  nz detect:       5  (OR(a2,a3), OR(a1,_), OR(b2,b3), OR(b1,_), AND(nz_a,nz_b))
  E-sum:           7
  K-flags raw:     3
  K-masking:       3  (AND each of k9_raw, k3_raw, or_a1b1 with nz)
  S decoder:      14
  AND-terms:      18
  Mag bits:       15
  Cond neg:       22  (r8=m0 pass-through saves 1 vs v3)
  Sign mask:       1
  ─────────────────
  Total:          89  (vs 101 in v3)
"""

import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from eval_circuit import evaluate_fast, FP4_TABLE


def make_remap_v4():
    """
    4-bit code = sign_bit(MSB) | mag_code(3 bits).
    Magnitude codes: 000=zero, 001=1.5, 010=3, 011=6,
                     100=0.5, 101=1.0, 110=2.0, 111=4.0
    """
    mag_to_code = {
        0.0: 0b000,
        1.5: 0b001,
        3.0: 0b010,
        6.0: 0b011,
        0.5: 0b100,
        1.0: 0b101,
        2.0: 0b110,
        4.0: 0b111,
    }
    remap = []
    for v in FP4_TABLE:
        sign = 1 if v < 0 else 0
        code = mag_to_code[abs(v)]
        remap.append((sign << 3) | code)
    return remap


def multiplier_v4(a0, a1, a2, a3, b0, b1, b2, b3, NOT, AND, OR, XOR):
    """89-gate FP4 multiplier (v4, zero=000 encoding)."""

    # ── Sign ─────────────────────────────────────────────────────────────────
    sign = XOR(a0, b0)                                              # 1

    # ── Zero detection (for K-flag masking) ──────────────────────────────────
    or_a23 = OR(a2, a3)                                             # 1
    nz_a = OR(a1, or_a23)                                           # 1
    or_b23 = OR(b2, b3)                                             # 1
    nz_b = OR(b1, or_b23)                                           # 1
    nz = AND(nz_a, nz_b)                                            # 1  → 5 gates

    # ── E-sum: S = (a2,a3) + (b2,b3), 3-bit result ──────────────────────────
    s0 = XOR(a3, b3)                                                # 1
    c0 = AND(a3, b3)                                                # 1
    s1x = XOR(a2, b2)                                               # 1
    s1 = XOR(s1x, c0)                                               # 1
    s2 = OR(AND(a2, b2), AND(s1x, c0))                             # 3  → 7 gates

    # ── K-flags raw (M = NOT(a1)) ─────────────────────────────────────────────
    # k9 = AND(NOT a1, NOT b1) = NOR(a1, b1)
    # k3 = XOR(NOT a1, NOT b1) = XOR(a1, b1)
    # not_k9 = OR(a1, b1)
    or_a1b1 = OR(a1, b1)                                            # 1  (= not_k9_raw)
    k9_raw = NOT(or_a1b1)                                           # 1
    k3_raw = XOR(a1, b1)                                            # 1  → 3 gates

    # ── Mask K-flags with nz (zero → all K-flags = 0 → all mag bits = 0) ─────
    nmc = AND(or_a1b1, nz)   # not_k9 masked                        # 1
    k3  = AND(k3_raw, nz)                                           # 1
    k9  = AND(k9_raw, nz)                                           # 1  → 3 gates

    # ── S decoder (3-of-7 one-hot) ───────────────────────────────────────────
    ns0 = NOT(s0)                                                    # 1
    ns1 = NOT(s1)                                                    # 1
    ns2 = NOT(s2)                                                    # 1

    u00 = AND(ns2, ns1)                                              # 1
    u01 = AND(ns2, s1)                                               # 1
    u10 = AND(s2, ns1)                                               # 1
    u11 = AND(s2, s1)                                                # 1

    sh0 = AND(u00, ns0)                                              # 1
    sh1 = AND(u00, s0)                                               # 1
    sh2 = AND(u01, ns0)                                              # 1
    sh3 = AND(u01, s0)                                               # 1
    sh4 = AND(u10, ns0)                                              # 1
    sh5 = AND(u10, s0)                                               # 1
    sh6 = AND(u11, ns0)                                              # 1   → 14 gates

    # ── AND-terms (K × shift) ────────────────────────────────────────────────
    # nmc × sh_j  j=0..6 : 7 terms (K=1 and K=3/2 upper bit)
    nmc0 = AND(nmc, sh0)
    nmc1 = AND(nmc, sh1)
    nmc2 = AND(nmc, sh2)
    nmc3 = AND(nmc, sh3)
    nmc4 = AND(nmc, sh4)
    nmc5 = AND(nmc, sh5)
    nmc6 = AND(nmc, sh6)   # 7 gates

    # k3 × sh_j  j=1..6 : 6 terms (K=3/2 lower bit; j=0 impossible)
    k3_1 = AND(k3, sh1)
    k3_2 = AND(k3, sh2)
    k3_3 = AND(k3, sh3)
    k3_4 = AND(k3, sh4)
    k3_5 = AND(k3, sh5)
    k3_6 = AND(k3, sh6)   # 6 gates

    # k9 × sh_j  j=2..6 : 5 terms (K=9/4; j=0,1 impossible since min S=2 for k9)
    k9_2 = AND(k9, sh2)
    k9_3 = AND(k9, sh3)
    k9_4 = AND(k9, sh4)
    k9_5 = AND(k9, sh5)
    k9_6 = AND(k9, sh6)   # 5 gates  → 18 total

    # ── Magnitude bits ────────────────────────────────────────────────────────
    # mag_bit_i = nmc_{i} OR k3_{i+1} OR k9_{i+2} OR k9_{i-1}
    m7 = k9_6                                                        # 0
    m6 = OR(nmc6, k9_5)                                              # 1
    m5 = OR(nmc5, OR(k3_6, k9_4))                                   # 2
    m4 = OR(OR(nmc4, k3_5), OR(k9_6, k9_3))                        # 3
    m3 = OR(OR(nmc3, k3_4), OR(k9_5, k9_2))                        # 3
    m2 = OR(nmc2, OR(k3_3, k9_4))                                   # 2
    m1 = OR(nmc1, OR(k3_2, k9_3))                                   # 2
    m0 = OR(nmc0, OR(k3_1, k9_2))                                   # 2  → 15 gates

    # ── Conditional two's complement negation ─────────────────────────────────
    # t_i = XOR(m_i, sign); r_{8-i} = XOR(t_i, carry); carry_next = AND(t_i, carry)
    # Note: r8 = m0 always (2's complement preserves LSB), saves 1 XOR gate.
    t0 = XOR(m0, sign);  r8 = m0;            c1 = AND(t0, sign)   # 2
    t1 = XOR(m1, sign);  r7 = XOR(t1, c1);  c2 = AND(t1, c1)     # 3
    t2 = XOR(m2, sign);  r6 = XOR(t2, c2);  c3 = AND(t2, c2)     # 3
    t3 = XOR(m3, sign);  r5 = XOR(t3, c3);  c4 = AND(t3, c3)     # 3
    t4 = XOR(m4, sign);  r4 = XOR(t4, c4);  c5 = AND(t4, c4)     # 3
    t5 = XOR(m5, sign);  r3 = XOR(t5, c5);  c6 = AND(t5, c5)     # 3
    t6 = XOR(m6, sign);  r2 = XOR(t6, c6);  c7 = AND(t6, c6)     # 3
    t7 = XOR(m7, sign);  r1 = XOR(t7, c7)                         # 2  → 22 gates

    # ── Sign masking (magnitude auto-zeros via K-flags, only sign needs mask) ─
    res0 = AND(sign, nz)                                             # 1

    return res0, r1, r2, r3, r4, r5, r6, r7, r8


def multiplier_v4b(a0, a1, a2, a3, b0, b1, b2, b3, NOT, AND, OR, XOR):
    """
    88-gate FP4 multiplier (v4b).

    Same as v4 but with one S-decoder optimization:
      sh6 = AND(u11, ns0) where u11 = AND(s2, s1).
      Since S <= 6 always (max E'_a + E'_b = 3+3=6), whenever u11=1
      we know S=6 and s0=0, so ns0=1 always. Thus sh6 = u11. Saves 1 gate.
    """
    sign = XOR(a0, b0)

    or_a23 = OR(a2, a3)
    nz_a = OR(a1, or_a23)
    or_b23 = OR(b2, b3)
    nz_b = OR(b1, or_b23)
    nz = AND(nz_a, nz_b)

    s0 = XOR(a3, b3)
    c0 = AND(a3, b3)
    s1x = XOR(a2, b2)
    s1 = XOR(s1x, c0)
    s2 = OR(AND(a2, b2), AND(s1x, c0))

    or_a1b1 = OR(a1, b1)
    k9_raw = NOT(or_a1b1)
    k3_raw = XOR(a1, b1)

    nmc = AND(or_a1b1, nz)
    k3  = AND(k3_raw, nz)
    k9  = AND(k9_raw, nz)

    ns0 = NOT(s0)
    ns1 = NOT(s1)
    ns2 = NOT(s2)

    u00 = AND(ns2, ns1)
    u01 = AND(ns2, s1)
    u10 = AND(s2, ns1)
    u11 = AND(s2, s1)   # sh6 = u11 (S<=6 guarantees ns0=1 when u11=1)

    sh0 = AND(u00, ns0)
    sh1 = AND(u00, s0)
    sh2 = AND(u01, ns0)
    sh3 = AND(u01, s0)
    sh4 = AND(u10, ns0)
    sh5 = AND(u10, s0)
    # sh6 = u11  (optimization: saves 1 AND gate)

    nmc0 = AND(nmc, sh0);  nmc1 = AND(nmc, sh1);  nmc2 = AND(nmc, sh2)
    nmc3 = AND(nmc, sh3);  nmc4 = AND(nmc, sh4);  nmc5 = AND(nmc, sh5)
    nmc6 = AND(nmc, u11)

    k3_1 = AND(k3, sh1);  k3_2 = AND(k3, sh2);  k3_3 = AND(k3, sh3)
    k3_4 = AND(k3, sh4);  k3_5 = AND(k3, sh5);  k3_6 = AND(k3, u11)

    k9_2 = AND(k9, sh2);  k9_3 = AND(k9, sh3);  k9_4 = AND(k9, sh4)
    k9_5 = AND(k9, sh5);  k9_6 = AND(k9, u11)

    m7 = k9_6
    m6 = OR(nmc6, k9_5)
    m5 = OR(nmc5, OR(k3_6, k9_4))
    m4 = OR(OR(nmc4, k3_5), OR(k9_6, k9_3))
    m3 = OR(OR(nmc3, k3_4), OR(k9_5, k9_2))
    m2 = OR(nmc2, OR(k3_3, k9_4))
    m1 = OR(nmc1, OR(k3_2, k9_3))
    m0 = OR(nmc0, OR(k3_1, k9_2))

    t0 = XOR(m0, sign);  r8 = m0;            c1 = AND(t0, sign)
    t1 = XOR(m1, sign);  r7 = XOR(t1, c1);  c2 = AND(t1, c1)
    t2 = XOR(m2, sign);  r6 = XOR(t2, c2);  c3 = AND(t2, c2)
    t3 = XOR(m3, sign);  r5 = XOR(t3, c3);  c4 = AND(t3, c3)
    t4 = XOR(m4, sign);  r4 = XOR(t4, c4);  c5 = AND(t4, c4)
    t5 = XOR(m5, sign);  r3 = XOR(t5, c5);  c6 = AND(t5, c5)
    t6 = XOR(m6, sign);  r2 = XOR(t6, c6);  c7 = AND(t6, c6)
    t7 = XOR(m7, sign);  r1 = XOR(t7, c7)

    res0 = AND(sign, nz)
    return res0, r1, r2, r3, r4, r5, r6, r7, r8


if __name__ == "__main__":
    remap = make_remap_v4()

    print("=" * 60)
    print("v4: zero=000, K-flag masking")
    print("Expected: 89 gates")
    print("=" * 60)
    print(f"\nRemap: {remap}\n")

    correct, gc, errors = evaluate_fast(multiplier_v4, remap, verbose=True)
    status = "CORRECT" if correct else f"WRONG ({len(errors)} errors)"
    print(f"\nResult: {status}")
    print(f"Gates:  {gc}")

    if errors:
        print("First 5 errors:")
        for a_i, b_i, exp, got in errors[:5]:
            print(f"  {FP4_TABLE[a_i]} × {FP4_TABLE[b_i]}: exp={exp} got={got}")

    print("\n" + "=" * 60)
    print("v4b: same + sh6=u11 decoder optimization")
    print("Expected: 88 gates")
    print("=" * 60)
    correct2, gc2, errors2 = evaluate_fast(multiplier_v4b, remap, verbose=True)
    status2 = "CORRECT" if correct2 else f"WRONG ({len(errors2)} errors)"
    print(f"\nResult: {status2}")
    print(f"Gates:  {gc2}")

    if errors2:
        print("First 5 errors:")
        for a_i, b_i, exp, got in errors2[:5]:
            print(f"  {FP4_TABLE[a_i]} × {FP4_TABLE[b_i]}: exp={exp} got={got}")

    best_correct = correct2 if correct2 else correct
    best_gc = gc2 if correct2 else (gc if correct else None)

    out = {"approach": "v4b_zero000_sh6_opt", "correct": best_correct,
           "gate_count": best_gc,
           "v4_gates": gc, "v4b_gates": gc2}
    out_path = os.path.join(os.path.dirname(__file__), "..", "autoresearch", "data",
                            "track_v4_results.json")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, 'w') as f:
        json.dump(out, f)
    print(f"\nSaved to {out_path}")
