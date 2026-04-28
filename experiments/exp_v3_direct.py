"""
Track E: Optimized structural circuit (v3) using direct S-based formula.

Key insight: output_bit_i = (not_mc AND S==i) OR (k3 AND S==i+1) OR
                             (k9 AND S==i+2) OR (k9 AND S==i-1)
where S = E-sum = (a2,a3)+(b2,b3) directly — NO subtractor needed.

Verified algebraically:
  K=1 (not_mc, M_sum=0): bit at S → uses "not_mc AND S==i" term
  K=3 (k3, M_sum=1):     bits at S-1 and S → S-1 = i → S = i+1 (uses k3 AND S==i+1)
                                               S   = i → i (uses not_mc AND S==i, since K=3 also has not_mc=1)
  K=9 (k9, M_sum=2):     bits at S-2 and S+1 → S-2 = i → S = i+2 (uses k9 AND S==i+2)
                                                 S+1 = i → S = i-1 (uses k9 AND S==i-1)

Additional optimizations vs v2 (126 gates):
1. No subtractor (-11 gates)
2. Zero=000 encoding: zero_detect costs 5 gates vs 9 (-4 gates)
3. Only mask res0 with zero flag: bits 1-8 auto-correct via carry chain (-8 gates)
4. Remove last carry AND in cond-neg (-1 gate)
5. Eliminate k9 AND S==0,1 (impossible) and k3 AND S==0 (-3 gates)
Expected: ~94 gates (vs 126 baseline)
"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from eval_circuit import evaluate_fast, FP4_TABLE


def make_remap_zero000():
    """
    Encoding where zero magnitude → code 000.
    Non-zero magnitudes 0.5,1,1.5,2,3,4,6 → codes 001..111.
    Use canonical (M, E+1) but shift zero to code 000.

    Mapping (3-bit magnitude codes, bit1=M, bits2-3=E+1 adjusted):
      0   → 000  (zero)
      0.5 → 001  (M=0, E=-1, E+1=0 → but we need nonzero: use 001)
      1.0 → 010  (M=0, E=0, E+1=1)
      2.0 → 011  (M=0, E=1, E+1=2)
      4.0 → 100  (M=0, E=2, E+1=3)
      1.5 → 101  (M=1, E=0, E+1=1)
      3.0 → 110  (M=1, E=1, E+1=2)
      6.0 → 111  (M=1, E=2, E+1=3)

    With this encoding:
      a1 = bit[2] = high bit of magnitude code
      a2 = bit[1] = middle bit
      a3 = bit[0] = low bit
    Zero: a1=0, a2=0, a3=0
    M_a = whether it's 1.5/3/6: M_a = a1  for codes 101,110,111; but also 100 has a1=1...
    Hmm, M_a = a1 doesn't perfectly separate M=1 from M=0 anymore.

    Let me use a different arrangement:
      0   → 000
      0.5 → 001  (M=0, E+1=0 → code that encodes E+1 in bits 1-2 and M in bit 2)

    Actually let me use: bit2=M, bit1=E_high, bit0=E_low, but shift so zero=000.
    Non-zero M=0 magnitudes have E+1 ∈ {0,1,2,3} → codes 0_00..0_11 = 000..011
    But 0_00=000 is zero! Conflict.

    Resolution: for zero, use the M=1 slot that's otherwise unused.
    M=1 magnitudes: 1.5(E+1=1), 3(E+1=2), 6(E+1=3) — codes 1_01, 1_10, 1_11
    The slot 1_00 = 0b100 is unused by any M=1 magnitude → assign zero to 0b100.

    But then zero=100 ≠ 000. We need zero=000.

    Alternative: shift the E+1 encoding so 0.5 (smallest non-zero) gets code 001:
      0   → 000
      0.5 → 001  (M=0, E=-1, E+1=0 → use sequential code 001)
      1.0 → 010
      1.5 → 011
      2.0 → 100
      3.0 → 101
      4.0 → 110
      6.0 → 111

    This ordering preserves magnitude ordering! Codes 001-111 = magnitudes sorted by value.
    But M and E+1 are not directly readable from bits.

    For the circuit, what matters is:
    - M_a: is magnitude a "type 1.5^1" (i.e., in {1.5, 3, 6})?
      Codes for 1.5, 3, 6: 011, 101, 111 (all odd codes except 001)
      Actually: {001=0.5, 010=1, 011=1.5, 100=2, 101=3, 110=4, 111=6}
      M=1 (i.e., 1.5, 3, 6) → codes 011, 101, 111.
      M=1 iff the code is odd AND ≠ 001? No: 001=0.5 is M=0 and odd.
      M_a = (a1=0 AND a2=1 AND a3=1) OR (a1=1 AND a2=0 AND a3=1) OR (a1=1 AND a2=1 AND a3=1)
           = a3 AND (NOT(a1 XOR a2) is complex)...

    This sequential encoding is harder to work with. Let me use a different approach.

    BEST APPROACH: Use the QM-optimal remapping found by the search, but ensure perm[0]=0.
    The QM search found best perm=[3,1,2,0,4,6,7,5] with 288 gates (flat SOP).
    Let's use a canonical M-E encoding where zero=000.

    For the circuit to work with the direct formula, we need:
    - a1 = M_a (the mantissa flag)
    - a2,a3 = E_a+1 (2-bit exponent offset)
    - zero → code 000 (a1=0, a2=0, a3=0)

    Problem: M=0, E=-1 → E+1=0 → code 0_00 = 000 = zero! Conflict.
    Magnitude 0.5 has M=0, E=-1, E+1=0 → would get code 000.

    Solution: Use E+1 starting from 1 for M=0 magnitudes, and dedicate code 000 for zero.
    But then the exponent encoding changes and we lose the "direct adder" property.

    SIMPLEST WORKING SOLUTION: Keep zero=code 111 for magnitude (as in the original multiplier.py),
    but use the direct formula. The formula works regardless of encoding as long as we correctly
    extract M_a and E_a from the inputs.

    For zero=111 encoding (used in autoresearch/multiplier.py):
      zero → code 111 (a1=1, a2=1, a3=1)
      0.5 → 000 (M=0, E+1=0 → a1=0, a2=0, a3=0)
      1.0 → 001 (M=0, E+1=1)
      2.0 → 010 (M=0, E+1=2)
      4.0 → 011 (M=0, E+1=3)
      1.5 → 100 (M=1, E+1=0 -- but E+1=0 for M=1 is unused: E≥0 for M=1, E+1≥1!)
         CONFLICT: M=1, E+1=0 → 1.5^1 * 2^(-1) = 0.75, not in FP4.
         So code 100 (M=1, E+1=0) is actually free! Use it for zero instead.

    Let me use:
      zero → 100 (M=1, E+1=0 -- unused by non-zero magnitudes)
      0.5  → 000 (M=0, E+1=0)
      1.0  → 001 (M=0, E+1=1)
      2.0  → 010 (M=0, E+1=2)
      4.0  → 011 (M=0, E+1=3)
      1.5  → 101 (M=1, E+1=1)
      3.0  → 110 (M=1, E+1=2)
      6.0  → 111 (M=1, E+1=3)

    With this encoding:
      zero_a = a1 AND NOT(a2) AND NOT(a3)  [code 100]
      M_a = a1  (correctly identifies M=1 for 1.5,3,6 and for zero -- but zero is masked)
      E_a+1 = (a2, a3)  (E+1 ∈ {0,1,2,3})

    For the E-sum: S = (a2,a3) + (b2,b3).
    For zero inputs (code 100): a2=0, a3=0 → contributes 0 to S.
    For 0.5 (code 000): M_a=0, E_a+1=0 → contributes 0 to S.
    Both are valid (zero and 0.5 have E+1=0), but zero is detected separately.

    zero detection: zero_a = AND(a1, AND(NOT(a2), NOT(a3))) = 4 gates
    same as before... not 5 gates.

    Actually let me try a different zero encoding to get zero=000:
    Zero → 000, and remove 0.5 from code 000 to somewhere else.
    Rearrange: 0.5→001, 1→010, 1.5→011, 2→100, 3→101, 4→110, 6→111, zero→000
    This is the sequential code. M_a is harder to extract but zero detection is:
    zero_a = NOT(OR(a1, OR(a2, a3))) = 3 gates. Saves 1 gate.
    """
    mag_to_code = {
        0.0: 0b100,  # zero → M=1, E+1=0 (unused slot)
        0.5: 0b000,  # M=0, E+1=0
        1.0: 0b001,  # M=0, E+1=1
        2.0: 0b010,  # M=0, E+1=2
        4.0: 0b011,  # M=0, E+1=3
        1.5: 0b101,  # M=1, E+1=1
        3.0: 0b110,  # M=1, E+1=2
        6.0: 0b111,  # M=1, E+1=3
    }
    remap = []
    for i, v in enumerate(FP4_TABLE):
        sign = 1 if v < 0 else 0
        mag = abs(v)
        code = mag_to_code[mag]
        remap.append((sign << 3) | code)
    return remap


def multiplier_v3(a0, a1, a2, a3, b0, b1, b2, b3, NOT, AND, OR, XOR):
    """
    Optimized structural circuit.

    Encoding (magnitude code = a1 a2 a3):
      zero → 100 (M=1,E+1=0 unused)
      0.5  → 000 (M=0,E+1=0)
      1.0  → 001 (M=0,E+1=1)
      2.0  → 010 (M=0,E+1=2)
      4.0  → 011 (M=0,E+1=3)
      1.5  → 101 (M=1,E+1=1)
      3.0  → 110 (M=1,E+1=2)
      6.0  → 111 (M=1,E+1=3)

    Key formula (no subtractor!):
      mag_bit_i = (not_mc AND S==i) OR (k3 AND S==i+1) OR
                  (k9 AND S==i+2)    OR (k9 AND S==i-1)
    where S = (a2,a3)+(b2,b3) and not_mc = NOT(m_carry), k3 = AND(not_mc,m_lsb), k9 = m_carry.
    """
    # ── Sign ─────────────────────────────────────────────────────────────────
    sign = XOR(a0, b0)                                    # 1

    # ── Zero detection: code 100 → a1=1, a2=0, a3=0 ─────────────────────────
    not_a2 = NOT(a2)                                       # 1
    not_a3 = NOT(a3)                                       # 1
    zero_a = AND(a1, AND(not_a2, not_a3))                 # 2   → 4 gates zero_a
    not_b2 = NOT(b2)                                       # 1
    not_b3 = NOT(b3)                                       # 1
    zero_b = AND(b1, AND(not_b2, not_b3))                 # 2   → 4 gates zero_b
    either_zero = OR(zero_a, zero_b)                       # 1   → 9 gates total

    # ── E-sum: S = (a2,a3) + (b2,b3), 3-bit result ──────────────────────────
    s0 = XOR(a3, b3)                                       # 1
    c0 = AND(a3, b3)                                       # 1
    s1x = XOR(a2, b2)                                      # 1
    s1 = XOR(s1x, c0)                                      # 1
    s2 = OR(AND(a2, b2), AND(s1x, c0))                    # 3   → 7 gates

    # ── M-sum: m_carry + m_lsb = M_a + M_b ──────────────────────────────────
    m_lsb = XOR(a1, b1)                                    # 1
    m_carry = AND(a1, b1)                                   # 1   → 2 gates

    # ── K-type flags ─────────────────────────────────────────────────────────
    not_mc = NOT(m_carry)                                   # 1
    k3 = AND(not_mc, m_lsb)                                # 1   → 2 gates (k9 = m_carry, free)

    # ── S decoder (NOT bits + pair combos + one-hot) ─────────────────────────
    ns0 = NOT(s0)                                           # 1
    ns1 = NOT(s1)                                           # 1
    ns2 = NOT(s2)                                           # 1   → 3 NOT gates

    u00 = AND(ns2, ns1)                                     # 1  (S 0..1 region)
    u01 = AND(ns2, s1)                                      # 1  (S 2..3 region)
    u10 = AND(s2, ns1)                                      # 1  (S 4..5 region)
    u11 = AND(s2, s1)                                       # 1  (S = 6)
    # 4 gates for upper pairs

    sh0 = AND(u00, ns0)                                     # 1
    sh1 = AND(u00, s0)                                      # 1
    sh2 = AND(u01, ns0)                                     # 1
    sh3 = AND(u01, s0)                                      # 1
    sh4 = AND(u10, ns0)                                     # 1
    sh5 = AND(u10, s0)                                      # 1
    sh6 = AND(u11, ns0)                                     # 1   → 7 one-hot gates
    # Total decoder: 3+4+7 = 14 gates

    # ── Precomputed K × shift terms ───────────────────────────────────────────
    # nmc_j = not_mc AND sh_j  for j = 0..6  (7 gates)
    # k3_j  = k3 AND sh_j      for j = 1..6  (6 gates — k3 AND S==0 impossible)
    # k9_j  = m_carry AND sh_j for j = 2..6  (5 gates — k9 AND S==0,1 impossible)
    nmc0 = AND(not_mc, sh0)
    nmc1 = AND(not_mc, sh1)
    nmc2 = AND(not_mc, sh2)
    nmc3 = AND(not_mc, sh3)
    nmc4 = AND(not_mc, sh4)
    nmc5 = AND(not_mc, sh5)
    nmc6 = AND(not_mc, sh6)   # 7 gates

    k3_1 = AND(k3, sh1)
    k3_2 = AND(k3, sh2)
    k3_3 = AND(k3, sh3)
    k3_4 = AND(k3, sh4)
    k3_5 = AND(k3, sh5)
    k3_6 = AND(k3, sh6)   # 6 gates

    k9_2 = AND(m_carry, sh2)
    k9_3 = AND(m_carry, sh3)
    k9_4 = AND(m_carry, sh4)
    k9_5 = AND(m_carry, sh5)
    k9_6 = AND(m_carry, sh6)   # 5 gates
    # Total: 18 AND gates

    # ── Magnitude bits ────────────────────────────────────────────────────────
    # mag_bit_i = nmc_i OR k3_{i+1} OR k9_{i+2} OR k9_{i-1}
    # (terms with invalid index j<0 or j>6 are omitted)

    # bit7: nmc_7(invalid) | k3_8(invalid) | k9_9(invalid) | k9_6 → k9_6
    m7 = k9_6                                              # 0 extra gates

    # bit6: nmc_6 | k3_7(inv) | k9_8(inv) | k9_5
    m6 = OR(nmc6, k9_5)                                   # 1 gate

    # bit5: nmc_5 | k3_6 | k9_7(inv) | k9_4
    m5 = OR(nmc5, OR(k3_6, k9_4))                        # 2 gates

    # bit4: nmc_4 | k3_5 | k9_6 | k9_3
    m4 = OR(OR(nmc4, k3_5), OR(k9_6, k9_3))             # 3 gates

    # bit3: nmc_3 | k3_4 | k9_5 | k9_2
    m3 = OR(OR(nmc3, k3_4), OR(k9_5, k9_2))             # 3 gates

    # bit2: nmc_2 | k3_3 | k9_4 | k9_1(impossible,skip) → 3 terms
    m2 = OR(nmc2, OR(k3_3, k9_4))                        # 2 gates

    # bit1: nmc_1 | k3_2 | k9_3 | k9_0(impossible,skip) → 3 terms
    m1 = OR(nmc1, OR(k3_2, k9_3))                        # 2 gates

    # bit0: nmc_0 | k3_1 | k9_2 | k9_{-1}(inv) → 3 terms
    m0 = OR(nmc0, OR(k3_1, k9_2))                        # 2 gates

    # OR gates total: 0+1+2+3+3+2+2+2 = 15 gates

    # ── Conditional two's complement ──────────────────────────────────────────
    # t_i = XOR(m_i, sign); r_i = XOR(t_i, carry); carry_{i+1} = AND(t_i, carry)
    # carry_0 = sign; work from LSB (bit0/res8) to MSB (bit7/res1)
    # Skip last carry output (saves 1 gate)
    t0 = XOR(m0, sign);  r8 = XOR(t0, sign);   c1 = AND(t0, sign)   # 3
    t1 = XOR(m1, sign);  r7 = XOR(t1, c1);     c2 = AND(t1, c1)     # 3
    t2 = XOR(m2, sign);  r6 = XOR(t2, c2);     c3 = AND(t2, c2)     # 3
    t3 = XOR(m3, sign);  r5 = XOR(t3, c3);     c4 = AND(t3, c3)     # 3
    t4 = XOR(m4, sign);  r4 = XOR(t4, c4);     c5 = AND(t4, c4)     # 3
    t5 = XOR(m5, sign);  r3 = XOR(t5, c5);     c6 = AND(t5, c5)     # 3
    t6 = XOR(m6, sign);  r2 = XOR(t6, c6);     c7 = AND(t6, c6)     # 3
    t7 = XOR(m7, sign);  r1 = XOR(t7, c7)                            # 2 (no last carry)
    # 3*7 + 2 = 23 gates
    # res0 is the sign of the result (MSB): AND(sign, not_zero) handled below

    # ── Zero masking (all 9 output bits) ─────────────────────────────────────
    # zero=100 encoding means magnitude circuit does NOT auto-output 0 for zero.
    # Must mask all bits.
    not_zero = NOT(either_zero)                            # 1
    res0 = AND(sign, not_zero)
    res1 = AND(r1, not_zero)
    res2 = AND(r2, not_zero)
    res3 = AND(r3, not_zero)
    res4 = AND(r4, not_zero)
    res5 = AND(r5, not_zero)
    res6 = AND(r6, not_zero)
    res7 = AND(r7, not_zero)
    res8 = AND(r8, not_zero)   # 10 gates total

    return res0, res1, res2, res3, res4, res5, res6, res7, res8


if __name__ == "__main__":
    remap = make_remap_zero000()

    print("=" * 60)
    print("Track E: v3 optimized structural circuit")
    print("=" * 60)
    print(f"\nRemap: {remap}")

    correct, gc, errors = evaluate_fast(multiplier_v3, remap, verbose=True)
    status = "CORRECT" if correct else f"WRONG ({len(errors)} errors)"
    print(f"\nResult: {status}")
    print(f"Gates:  {gc}")

    if errors:
        print("First 5 errors:")
        for a_i, b_i, exp, got in errors[:5]:
            print(f"  {FP4_TABLE[a_i]} × {FP4_TABLE[b_i]}: exp={exp} got={got}")

    # Save result
    import json
    out = {"approach": "v3_direct_formula", "correct": correct,
           "gate_count": gc if correct else None}
    out_path = os.path.join(os.path.dirname(__file__), "..", "autoresearch", "data",
                            "track_e_results.json")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, 'w') as f:
        json.dump(out, f)
    print(f"Saved to {out_path}")
