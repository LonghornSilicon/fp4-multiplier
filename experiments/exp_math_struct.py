"""
Track B: Mathematical structural circuit using K-type decomposition.

Key insight: |4*a*b| = K * 2^shift where K ∈ {1,3,9}, shift ∈ {0..6}
This allows a very structured circuit:
1. Compute sign (XOR)
2. Detect zero
3. Compute M_a, M_b (mantissa flags)
4. Compute exponent sum
5. Determine K-type and shift
6. Generate sparse output bits
7. Conditional negation
8. Zero masking

This script tries multiple encoding strategies and circuit decompositions,
verifies each, and reports gate counts.
"""

import sys
import os
import itertools

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from eval_circuit import evaluate_fast, GateCounter


# ── Encoding helpers ──────────────────────────────────────────────────────────

FP4_TABLE = [0.0, 0.5, 1.0, 1.5, 2.0, 3.0, 4.0, 6.0,
             0.0, -0.5, -1.0, -1.5, -2.0, -3.0, -4.0, -6.0]


def make_remap_canonical():
    """
    Canonical (M, E+1) encoding:
    - bit0 = sign
    - bit1 = M (1 if magnitude has 1.5 factor)
    - bit2 bit3 = E+1 in {0..3}
    - Zero → 0b0111 (M=1, E+1=3 — unused slot since M=1 only has E+1 ∈ {1,2,3}... actually E+1=0 is unused for M=1 since E≥0 for M=1)

    Wait, M=1 magnitudes: 1.5(E=0,E+1=1), 3(E=1,E+1=2), 6(E=2,E+1=3).
    M=1, E+1=0 (E=-1) would be 1.5^1 * 2^(-1) = 0.75 which isn't in FP4.
    So 0b0100 = sign=0, M=1, E+1=0 is unused by any non-zero positive mag.
    Map zero to 0b0100 so zero detection is AND(bit1, NOT(bit2), NOT(bit3)).
    Or map zero to 0b0111 (M=1, E+1=3 for positive, same for negative).
    """
    mag_to_code = {
        0.5: 0b000,  # M=0, E+1=0
        1.0: 0b001,  # M=0, E+1=1
        2.0: 0b010,  # M=0, E+1=2
        4.0: 0b011,  # M=0, E+1=3
        1.5: 0b100,  # M=1, E+1=1... wait
        3.0: 0b101,  # M=1, E+1=2... wait
        6.0: 0b110,  # M=1, E+1=3... wait
        0.0: 0b111,  # zero
    }
    # Actually with M in bit1 and (E+1) in bits 2-3:
    # bit1=M, bit2=(E+1)_high, bit3=(E+1)_low
    # 0.5: M=0, E+1=0 → 0_00 → 000
    # 1.0: M=0, E+1=1 → 0_01 → 001
    # 2.0: M=0, E+1=2 → 0_10 → 010
    # 4.0: M=0, E+1=3 → 0_11 → 011
    # 1.5: M=1, E+1=1 → 1_01 → 101
    # 3.0: M=1, E+1=2 → 1_10 → 110
    # 6.0: M=1, E+1=3 → 1_11 → 111
    # Available: 100 (M=1, E+1=0) → use for zero
    mag_to_code = {
        0.5: 0b000,
        1.0: 0b001,
        2.0: 0b010,
        4.0: 0b011,
        1.5: 0b101,
        3.0: 0b110,
        6.0: 0b111,
        0.0: 0b100,  # zero → M=1, E+1=00 (unused)
    }
    remap = []
    for i, v in enumerate(FP4_TABLE):
        sign = 1 if v < 0 else 0
        mag = abs(v)
        code = mag_to_code[mag]
        remap.append((sign << 3) | code)
    return remap


def make_remap_gray_exp():
    """
    Same M-E structure but use Gray code for E+1 to reduce transitions.
    E+1: 0→00, 1→01, 2→11, 3→10 (Gray)
    """
    gray = [0b00, 0b01, 0b11, 0b10]
    mag_to_code = {
        0.5: (0 << 2) | gray[0],   # M=0, E+1=0 → 0_00
        1.0: (0 << 2) | gray[1],   # M=0, E+1=1 → 0_01
        2.0: (0 << 2) | gray[2],   # M=0, E+1=2 → 0_11
        4.0: (0 << 2) | gray[3],   # M=0, E+1=3 → 0_10
        1.5: (1 << 2) | gray[1],   # M=1, E+1=1 → 1_01
        3.0: (1 << 2) | gray[2],   # M=1, E+1=2 → 1_11
        6.0: (1 << 2) | gray[3],   # M=1, E+1=3 → 1_10
        0.0: (1 << 2) | gray[0],   # zero → M=1, E+1=0 → 1_00 (unused slot)
    }
    remap = []
    for i, v in enumerate(FP4_TABLE):
        sign = 1 if v < 0 else 0
        mag = abs(v)
        code = mag_to_code[mag]
        remap.append((sign << 3) | code)
    return remap


# ── Structural circuit variant 1: canonical encoding ─────────────────────────

def multiplier_v1(a0, a1, a2, a3, b0, b1, b2, b3, NOT, AND, OR, XOR):
    """
    Structural circuit using canonical encoding:
    a1=M_a, a2=E_high, a3=E_low  (E+1 encoded in a2,a3)
    Zero encoded as (M=1, E+1=00) i.e. a1=1, a2=0, a3=0

    Total gate count target: < 80
    """
    # ── Sign ──────────────────────────────────────────────────────────────────
    sign = XOR(a0, b0)                          # 1

    # ── Zero detection ────────────────────────────────────────────────────────
    # zero_a = a1=1 AND a2=0 AND a3=0 → AND(a1, AND(NOT(a2), NOT(a3)))
    not_a2 = NOT(a2)                            # 1
    not_a3 = NOT(a3)                            # 1
    zero_a = AND(a1, AND(not_a2, not_a3))       # 2
    not_b2 = NOT(b2)                            # 1
    not_b3 = NOT(b3)                            # 1
    zero_b = AND(b1, AND(not_b2, not_b3))       # 2
    either_zero = OR(zero_a, zero_b)            # 1   → 9 gates

    # ── M-type (bit 1 of 3-bit magnitude code) ────────────────────────────────
    # With our encoding: a1 = M_a (1 iff magnitude ∈ {1.5,3,6})
    # But zero also has a1=1 — doesn't matter since we mask at end

    # ── Exponent sum: (a2,a3) + (b2,b3) → (s2,s1,s0) ────────────────────────
    # (a2,a3) and (b2,b3) encode (E_a+1) and (E_b+1)
    # For zero: E+1=0 → a2=0,a3=0 → contributes 0 to sum (correct, masked out anyway)
    s0 = XOR(a3, b3)                            # 1
    c0 = AND(a3, b3)                            # 1
    s1_x = XOR(a2, b2)                          # 1
    s1 = XOR(s1_x, c0)                          # 1
    # s2 = (a2 AND b2) OR (s1_x AND c0)
    s2 = OR(AND(a2, b2), AND(s1_x, c0))        # 3   → 7 gates for E-sum

    # ── M-sum: M_a + M_b → (m_carry, m_lsb) ─────────────────────────────────
    m_lsb = XOR(a1, b1)                         # 1
    m_carry = AND(a1, b1)                        # 1   → 2 gates

    # ── Shift = E-sum - M_sum ─────────────────────────────────────────────────
    # (s2,s1,s0) - (m_carry, m_lsb) using 3-bit ripple borrow subtractor
    d0 = XOR(s0, m_lsb)                         # 1
    not_s0 = NOT(s0)                             # 1
    borrow0 = AND(not_s0, m_lsb)                # 1
    d1_x = XOR(s1, m_carry)                     # 1
    d1 = XOR(d1_x, borrow0)                     # 1
    # borrow1 = (NOT(s1) AND m_carry) OR (NOT(d1_x) AND borrow0)
    not_s1 = NOT(s1)                             # 1
    not_d1x = NOT(d1_x)                          # 1
    borrow1 = OR(AND(not_s1, m_carry), AND(not_d1x, borrow0))  # 3
    d2 = XOR(s2, borrow1)                        # 1   → 11 gates

    # shift = (d2, d1, d0) ∈ {0..6}

    # ── K-type flags ─────────────────────────────────────────────────────────
    # K=1: m_carry=0, m_lsb=0  → k_is_1 = NOT(m_carry) AND NOT(m_lsb)
    # K=3: m_carry=0, m_lsb=1  → k_is_3 = NOT(m_carry) AND m_lsb
    # K=9: m_carry=1, m_lsb=0  → k_is_9 = m_carry (since m_lsb must be 0 if m_carry=1, max M_sum=2)
    not_mc = NOT(m_carry)                        # 1
    not_ml = NOT(m_lsb)                          # 1
    k1 = AND(not_mc, not_ml)                     # 1
    k3 = AND(not_mc, m_lsb)                      # 1
    k9 = m_carry                                 # free (alias)
    # 4 gates

    # ── Shift decoder ────────────────────────────────────────────────────────
    not_d0 = NOT(d0)                             # 1
    not_d1 = NOT(d1)                             # 1
    not_d2 = NOT(d2)                             # 1

    sh0 = AND(AND(not_d2, not_d1), not_d0)       # 2
    sh1 = AND(AND(not_d2, not_d1), d0)           # 2
    sh2 = AND(AND(not_d2, d1), not_d0)           # 2
    sh3 = AND(AND(not_d2, d1), d0)               # 2
    sh4 = AND(AND(d2, not_d1), not_d0)           # 2
    sh5 = AND(AND(d2, not_d1), d0)               # 2
    sh6 = AND(AND(d2, d1), not_d0)               # 2
    # 3 + 14 = 17 gates for NOT + decoder

    # ── Magnitude bits (output bits 7..0 of 8-bit unsigned) ──────────────────
    # Precompute: k1*sh[i], k3*sh[i], k9*sh[i] for reuse
    # mag bit i = (k1 AND sh_i) OR (k3 AND (sh_i OR sh_{i-1})) OR (k9 AND (sh_i OR sh_{i-3}))

    # Note: valid shift range for each K:
    # K=1: shift 0..6
    # K=3: shift 0..5 (K=3, shift=6 → bit 7 set, but 3*2^6=192 > 144=max → impossible)
    #   Actually max for K=3 is when a=4,b=4? No: K=3 needs M_sum=1.
    #   Max when M_sum=1: one M=1 (max E=2,E+1=3), one M=0 (max E=2,E+1=3): s=6, M_sum=1 → shift=5. 3*2^5=96. ✓
    # K=9: shift 0..4 (max when both M=1, max E+1=3 each: s=6, M_sum=2 → shift=4). 9*2^4=144. ✓
    # So: K=1 covers shifts 0-6; K=3 covers 0-5; K=9 covers 0-4.
    # But for output bits, K=3,shift=6 would set bit 7 and bit 6 (both from K=3 with its adjacent pair).
    # However M_sum=1, E_a+E_b+2=7 means E_a+E_b=5. Max (E_a+1)+(E_b+1)=3+3=6, so 6=7? No 6≠7.
    # Actually max s = (3+3) = 6, shift = 6 - M_sum = 6-1=5 for K=3. So K=3,shift=6 is impossible.

    sh = [sh0, sh1, sh2, sh3, sh4, sh5, sh6]

    # Helper: build AND-OR for magnitude bit
    # Returns (expression, gate_count_added)
    def mbit(i):
        terms = []
        if 0 <= i <= 6:
            terms.append(AND(k1, sh[i]))         # k1 * sh_i
        if 0 <= i <= 5:
            terms.append(AND(k3, sh[i]))          # k3 * sh_i (K=3 contributes at bit i from shift=i)
        if 0 <= i-1 <= 5:
            terms.append(AND(k3, sh[i-1]))        # k3 * sh_{i-1} (K=3 contributes at bit i from shift=i-1)
        if 0 <= i <= 4:
            terms.append(AND(k9, sh[i]))          # k9 * sh_i
        if 0 <= i-3 <= 4:
            terms.append(AND(k9, sh[i-3]))        # k9 * sh_{i-3}
        if not terms:
            return False
        result = terms[0]
        for t in terms[1:]:
            result = OR(result, t)
        return result

    m7 = mbit(7)
    m6 = mbit(6)
    m5 = mbit(5)
    m4 = mbit(4)
    m3 = mbit(3)
    m2 = mbit(2)
    m1 = mbit(1)
    m0 = mbit(0)

    # ── Conditional two's complement negation ─────────────────────────────────
    # t_i = XOR(m_i, sign); r_i = XOR(t_i, carry_i); carry_{i+1} = AND(t_i, carry_i)
    # carry_0 = sign
    def cond_neg_bit(m_bit, carry_in):
        t = XOR(m_bit, sign)
        r = XOR(t, carry_in)
        c_out = AND(t, carry_in)
        return r, c_out, t

    r8, c1, t0_ = cond_neg_bit(m0, sign)
    r7, c2, t1_ = cond_neg_bit(m1, c1)
    r6, c3, t2_ = cond_neg_bit(m2, c2)
    r5, c4, t3_ = cond_neg_bit(m3, c3)
    r4, c5, t4_ = cond_neg_bit(m4, c4)
    r3, c6, t5_ = cond_neg_bit(m5, c5)
    r2, c7, t6_ = cond_neg_bit(m6, c6)
    r1, _,  t7_ = cond_neg_bit(m7, c7)
    r0 = sign  # sign of result is input sign XOR

    # ── Zero masking ──────────────────────────────────────────────────────────
    not_zero = NOT(either_zero)                  # 1

    res0 = AND(r0, not_zero)
    res1 = AND(r1, not_zero)
    res2 = AND(r2, not_zero)
    res3 = AND(r3, not_zero)
    res4 = AND(r4, not_zero)
    res5 = AND(r5, not_zero)
    res6 = AND(r6, not_zero)
    res7 = AND(r7, not_zero)
    res8 = AND(r8, not_zero)   # 9 gates for masking

    return res0, res1, res2, res3, res4, res5, res6, res7, res8


# ── Structural circuit variant 2: avoid separate shift decoder ────────────────

def multiplier_v2(a0, a1, a2, a3, b0, b1, b2, b3, NOT, AND, OR, XOR):
    """
    Optimized structural circuit: avoid full shift decoder by generating
    magnitude bits directly from (d2,d1,d0) and K-type without enumeration.

    For K=1: output bit i = 1 iff shift = i
      → bit 0: shift=0 → d2=0,d1=0,d0=0
      → etc.
    For K=3: output bit i = 1 iff shift=i OR shift=i-1
      → bit 1: shift=0 or shift=1 → d2=0,d1=0 (for both cases)
      Some bits have simplified expressions.
    For K=9: output bit i = 1 iff shift=i OR shift=i-3
      → Can sometimes factor the condition.
    """
    # ── Sign ─────────────────────────────────────────────────────────────────
    sign = XOR(a0, b0)                           # 1

    # ── Zero detection (zero = a1=1, a2=0, a3=0 in canonical encoding) ───────
    not_a2 = NOT(a2)                             # 1
    not_a3 = NOT(a3)                             # 1
    zero_a = AND(a1, AND(not_a2, not_a3))        # 2
    not_b2 = NOT(b2)                             # 1
    not_b3 = NOT(b3)                             # 1
    zero_b = AND(b1, AND(not_b2, not_b3))        # 2
    either_zero = OR(zero_a, zero_b)             # 1   → 9 gates

    # ── Exponent sum ─────────────────────────────────────────────────────────
    s0 = XOR(a3, b3)                             # 1
    c0 = AND(a3, b3)                             # 1
    s1_x = XOR(a2, b2)                           # 1
    s1 = XOR(s1_x, c0)                           # 1
    s2 = OR(AND(a2, b2), AND(s1_x, c0))         # 3   → 7 gates

    # ── M-sum ────────────────────────────────────────────────────────────────
    m_lsb = XOR(a1, b1)                          # 1
    m_carry = AND(a1, b1)                         # 1   → 2 gates

    # ── K-type flags ─────────────────────────────────────────────────────────
    not_mc = NOT(m_carry)                         # 1
    not_ml = NOT(m_lsb)                           # 1
    k1 = AND(not_mc, not_ml)                      # 1
    k3 = AND(not_mc, m_lsb)                       # 1
    k9 = m_carry                                  # free
    # 4 gates

    # ── Shift = E-sum - M-sum ─────────────────────────────────────────────────
    d0 = XOR(s0, m_lsb)                          # 1
    borrow0 = AND(NOT(s0), m_lsb)                # 2
    d1_x = XOR(s1, m_carry)                      # 1
    d1 = XOR(d1_x, borrow0)                      # 1
    not_d1x = NOT(d1_x)                           # 1
    borrow1 = OR(AND(NOT(s1), m_carry), AND(not_d1x, borrow0))  # 4 (reuse NOT(s1)? no...)
    # Actually let's be careful: NOT(s1) needs 1 gate
    not_s1_ = NOT(s1)                             # 1
    borrow1 = OR(AND(not_s1_, m_carry), AND(not_d1x, borrow0))  # 3
    d2 = XOR(s2, borrow1)                         # 1   → 11 gates for shift

    # Precompute NOT of shift bits
    not_d0 = NOT(d0)                              # 1
    not_d1 = NOT(d1)                              # 1
    not_d2 = NOT(d2)                              # 1   → 3 gates

    # ── Direct magnitude bit computation (without full shift decoder) ─────────
    # Rather than decoding shift to one-hot then ANDing with K-type,
    # compute each mag bit's condition directly.
    #
    # mag_bit_i = (k1 AND shift==i) OR (k3 AND (shift==i OR shift==i-1)) OR (k9 AND (shift==i OR shift==i-3))
    #
    # Group: all three terms involve "shift==i" → factor it out:
    # mag_bit_i = (shift==i AND (k1 OR k3_valid_at_i OR k9_valid_at_i)) OR
    #             (k3 AND shift==i-1) OR (k9 AND shift==i-3)
    # where k3_valid_at_i = k3 if i-1 is valid shift for K=3 (i.e., another bit i-1 also gets set)
    #
    # Actually simpler grouping:
    # Let any_k_shift_i = OR(k1, k3, k9) AND shift==i  ... but OR(k1,k3,k9) = NOT(zero_flag) when nonzero
    # Actually k1 OR k3 OR k9 = NOT(m_carry AND m_lsb) ... no: m_carry=1,m_lsb=1 → K=1.5^3=3.375 not integer
    # In fact exactly one of {k1, k3, k9} is true for any valid non-zero input.
    # So (k1 OR k3 OR k9) is always true for non-zero inputs — simplifies nothing.
    #
    # Let's just use the full expansion but try to share NOT(sh_i) computations:

    # Precomputed shift matches (need both sh_i and NOT(sh_i) style terms):
    d2d1 = AND(d2, d1)      # 1 gate: used for sh6 and others
    d2nd1 = AND(d2, not_d1)  # 1 gate
    nd2d1 = AND(not_d2, d1)  # 1 gate
    nd2nd1 = AND(not_d2, not_d1)  # 1 gate
    # 4 gates for "upper pair" combinations

    sh0 = AND(nd2nd1, not_d0)   # 1
    sh1 = AND(nd2nd1, d0)       # 1
    sh2 = AND(nd2d1, not_d0)    # 1
    sh3 = AND(nd2d1, d0)        # 1
    sh4 = AND(d2nd1, not_d0)    # 1
    sh5 = AND(d2nd1, d0)        # 1
    sh6 = AND(d2d1, not_d0)     # 1
    # 7 gates for shift one-hot (reusing the 4 pair combinations)

    # Now magnitude bits using shared K*sh terms:
    # Precompute k3*sh[i] and k9*sh[i] for the values that appear in 2+ bits
    # k3 appears in: bit0(sh0), bit1(sh0,sh1), bit2(sh1,sh2), bit3(sh2,sh3),
    #                bit4(sh3,sh4), bit5(sh4,sh5), bit6(sh5,sh6), bit7(sh6)
    # k9 appears in: bit0(sh0), bit3(sh0,sh3), bit1(sh1), bit4(sh1,sh4),
    #                bit2(sh2), bit5(sh2,sh5), bit3(sh3), bit6(sh3,sh6),
    #                bit4(sh4), bit7(sh4), bit5(sh5), bit6(sh6)

    # Precompute k1*sh[i] (used once each for K=1 contribution)
    # Precompute k3*sh[i] for shared use
    k3sh0 = AND(k3, sh0)   # used by bit0 and bit1
    k3sh1 = AND(k3, sh1)   # used by bit1 and bit2
    k3sh2 = AND(k3, sh2)   # used by bit2 and bit3
    k3sh3 = AND(k3, sh3)   # used by bit3 and bit4
    k3sh4 = AND(k3, sh4)   # used by bit4 and bit5
    k3sh5 = AND(k3, sh5)   # used by bit5 and bit6
    k3sh6 = AND(k3, sh6)   # used by bit6 and bit7 (but K=3,sh=6 impossible → this is always 0)
    # 7 gates

    k9sh0 = AND(k9, sh0)   # used by bit0 and bit3
    k9sh1 = AND(k9, sh1)   # used by bit1 and bit4
    k9sh2 = AND(k9, sh2)   # used by bit2 and bit5
    k9sh3 = AND(k9, sh3)   # used by bit3 and bit6
    k9sh4 = AND(k9, sh4)   # used by bit4 and bit7
    # k9sh5,k9sh6 only appear once each, compute inline
    # 5 gates

    # Now each magnitude bit:
    # bit 7: (k1,sh6) OR (k3,sh6) OR (k3,sh5) -- wait, K=3 at shift=6 sets bits 7 AND 6
    #        actually K=3*2^shift: at shift=5: 3*32=96 = 0b01100000 → bits 6 and 5 set
    #        at shift=6: 3*64=192 → bits 7 and 6 but this exceeds max product 144... actually impossible
    #        Max product is 4*6*6=144=0b10010000 → bit7 and bit4 set (K=9, shift=4)
    #        So bit7 ONLY possible via K=9 with shift=4.
    #   bit7 = k9sh4
    m7 = k9sh4                                    # 0 gates (already computed)

    # bit6: (k1,sh6) OR (k3,sh5) OR (k9,sh3) OR (k9,sh6)→impossible
    #   k3,sh6 impossible; k9,sh6 → 9*64=576 too big → impossible
    #   Actually K=9,sh=3 → 9*8=72=0b01001000 → bits 6 and 3 set (bit6 set)
    #   K=1,sh=6 → 64=0b01000000 → bit6 set
    #   K=3,sh=5 → 96=0b01100000 → bits 6 and 5 set
    k1sh6 = AND(k1, sh6)                          # 1
    m6 = OR(k1sh6, OR(k3sh5, k9sh3))             # 2

    # bit5: (k1,sh5) OR (k3,sh4) OR (k3,sh5→sets bits 6&5 ✓) OR (k9,sh2) OR (k9,sh5→9*32=288 too big→impossible)
    #   K=3,sh=5: 96=0b01100000 → bits 6,5 set → bit5 = 1 when shift=5 and K=3 → k3sh5 ✓
    #   K=3,sh=4: 48=0b00110000 → bits 5,4 → bit5 = 1 → k3sh4 ✓
    #   K=1,sh=5: 32=0b00100000 → bit5 → k1sh5
    #   K=9,sh=2: 36=0b00100100 → bits 5,2 → bit5 = 1 → k9sh2 ✓
    k1sh5 = AND(k1, sh5)                          # 1
    m5 = OR(OR(k1sh5, k3sh5), OR(k3sh4, k9sh2))  # 3

    # bit4: (k1,sh4) OR (k3,sh3) OR (k3,sh4) OR (k9,sh1) OR (k9,sh4)
    #   K=1,sh=4: 16 → bit4
    #   K=3,sh=3: 24=0b00011000 → bits 4,3 → bit4
    #   K=3,sh=4: 48=0b00110000 → bits 5,4 → bit4
    #   K=9,sh=1: 18=0b00010010 → bits 4,1 → bit4
    #   K=9,sh=4: 144=0b10010000 → bits 7,4 → bit4
    k1sh4 = AND(k1, sh4)                          # 1
    m4 = OR(OR(k1sh4, OR(k3sh3, k3sh4)), OR(k9sh1, k9sh4))  # 4

    # bit3: (k1,sh3) OR (k3,sh2) OR (k3,sh3) OR (k9,sh0) OR (k9,sh3)
    #   K=1,sh=3: 8 → bit3
    #   K=3,sh=2: 12=0b00001100 → bits 3,2 → bit3
    #   K=3,sh=3: 24=0b00011000 → bits 4,3 → bit3
    #   K=9,sh=0: 9=0b00001001 → bits 3,0 → bit3
    #   K=9,sh=3: 72=0b01001000 → bits 6,3 → bit3
    k1sh3 = AND(k1, sh3)                          # 1
    m3 = OR(OR(k1sh3, OR(k3sh2, k3sh3)), OR(k9sh0, k9sh3))  # 4

    # bit2: (k1,sh2) OR (k3,sh1) OR (k3,sh2) OR (k9,sh2) [wait k9,sh2→bit5 too] OR (k9,sh_minus1→invalid)
    #   Actually bit2 from K=9: bit2 set when shift=2 (lower bit) or shift=2-3=-1 (invalid) or shift=i with i-3=2→i=5: k9sh5
    #   K=9,sh=5 → 9*32=288 > 144 → impossible ✓
    #   Actually: K=9,sh=2 → 36=0b00100100 → bit5 AND bit2 set → bit2 set. k9sh2 ✓
    #   Wait I need to be systematic: bit i is set when K=9,shift=i (lower bit of pair) OR K=9,shift=i-3 (upper bit of pair)
    #   bit2 is set when: K=9,shift=2 (lower) → YES; K=9,shift=2-3=-1 → NO
    #   So: bit2 ← K=9 only via sh2
    #   K=3: bit2 ← K=3,sh=1 (3*2=6→bits 2,1) OR K=3,sh=2 (3*4=12→bits 3,2)
    k1sh2 = AND(k1, sh2)                          # 1
    m2 = OR(OR(k1sh2, k3sh1), OR(k3sh2, k9sh2))  # 3

    # bit1: (k1,sh1) OR (k3,sh0) OR (k3,sh1) OR (k9,sh1)
    #   K=9: bit1 set when K=9,shift=1 (lower) → 18=0b00010010→bits 4,1 ✓
    #   K=9,shift=1-3=-2 → invalid
    k1sh1 = AND(k1, sh1)                          # 1
    m1 = OR(OR(k1sh1, k3sh0), OR(k3sh1, k9sh1))  # 3

    # bit0: (k1,sh0) OR (k3,sh0-1=invalid) OR (k9,sh0) [lower] OR (k9,sh0-3=invalid)
    #   K=3,sh=0: 3*1=3=0b11 → bits 1,0 set → bit0 set
    #   Actually bit0 from K=3: K=3,shift=0 sets bits 1 and 0. So k3sh0 ✓
    k1sh0 = AND(k1, sh0)                          # 1
    m0 = OR(OR(k1sh0, k3sh0), k9sh0)             # 2

    # ── Conditional two's complement ──────────────────────────────────────────
    # sign = XOR(a0,b0) from above
    # t_i = XOR(m_i, sign); r_i = XOR(t_i, carry); carry_next = AND(t_i, carry); carry_0 = sign
    def cneg(m_i, c):
        t = XOR(m_i, sign)
        r = XOR(t, c)
        cn = AND(t, c)
        return r, cn

    r8, c1 = cneg(m0, sign)
    r7, c2 = cneg(m1, c1)
    r6, c3 = cneg(m2, c2)
    r5, c4 = cneg(m3, c3)
    r4, c5 = cneg(m4, c4)
    r3, c6 = cneg(m5, c5)
    r2, c7 = cneg(m6, c6)
    r1, _  = cneg(m7, c7)
    r0 = sign

    # ── Zero masking ─────────────────────────────────────────────────────────
    not_zero = NOT(either_zero)                   # 1
    res0 = AND(r0, not_zero)
    res1 = AND(r1, not_zero)
    res2 = AND(r2, not_zero)
    res3 = AND(r3, not_zero)
    res4 = AND(r4, not_zero)
    res5 = AND(r5, not_zero)
    res6 = AND(r6, not_zero)
    res7 = AND(r7, not_zero)
    res8 = AND(r8, not_zero)   # 9 gates

    return res0, res1, res2, res3, res4, res5, res6, res7, res8


# ── Main ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    remap = make_remap_canonical()

    print("=" * 70)
    print("Track B: Mathematical structural circuit")
    print("=" * 70)

    print("\nTesting multiplier_v1 (canonical M-E encoding)...")
    correct_v1, gc_v1, errs_v1 = evaluate_fast(multiplier_v1, remap, verbose=True)
    status_v1 = "CORRECT" if correct_v1 else f"WRONG ({len(errs_v1)} errors)"
    print(f"v1: {status_v1} | {gc_v1} gates")
    if errs_v1:
        for a_i, b_i, exp, got in errs_v1[:5]:
            from eval_circuit import FP4_TABLE as ft
            print(f"  {ft[a_i]} × {ft[b_i]}: expected {exp} got {got}")

    print("\nTesting multiplier_v2 (optimized variant with shared k*sh terms)...")
    correct_v2, gc_v2, errs_v2 = evaluate_fast(multiplier_v2, remap, verbose=True)
    status_v2 = "CORRECT" if correct_v2 else f"WRONG ({len(errs_v2)} errors)"
    print(f"v2: {status_v2} | {gc_v2} gates")
    if errs_v2:
        for a_i, b_i, exp, got in errs_v2[:5]:
            from eval_circuit import FP4_TABLE as ft
            print(f"  {ft[a_i]} × {ft[b_i]}: expected {exp} got {got}")

    # Try gray encoding too
    remap_gray = make_remap_gray_exp()
    # Gray encoding changes the E+1 bit patterns so need a circuit variant for it
    # For now just test canonical

    best_gc = min([gc for gc, ok in [(gc_v1, correct_v1), (gc_v2, correct_v2)] if ok],
                  default=None)
    print(f"\nBest correct circuit: {best_gc} gates")

    import json, os
    out = {
        "v1": {"correct": correct_v1, "gate_count": gc_v1 if correct_v1 else None},
        "v2": {"correct": correct_v2, "gate_count": gc_v2 if correct_v2 else None},
        "best": best_gc,
    }
    out_path = os.path.join(os.path.dirname(__file__), "..", "autoresearch", "data",
                            "track_b_results.json")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, 'w') as f:
        json.dump(out, f, indent=2)
    print(f"Saved to {out_path}")
