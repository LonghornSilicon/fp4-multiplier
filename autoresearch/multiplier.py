"""
FP4 Multiplier - Current Best Circuit

This file is the target for iterative optimization.
Run with: python eval_circuit.py autoresearch/multiplier.py
Or verify with: python autoresearch/run.py

Format: write_your_multiplier_here(a0..a3, b0..b3, *, NOT, AND, OR, XOR) -> (res0..res8)
  - a0/b0: sign bit (MSB)
  - a1/b1: exponent MSB
  - a2/b2: exponent LSB
  - a3/b3: mantissa bit (LSB)
  - res0: sign/MSB of output, res8: LSB (place value 1/4)

INPUT_REMAP uses canonical (M, E+1) encoding:
  Zero  → 0b0000 (sign=0, mag_code=000)
  0.5   → 0b0010  (M=0, E=-1 → E+1=0 → code 010 = 2, sign=0)
  ...
  (See build_remap() below for full mapping)

Current approach: mathematical structural decomposition
  1. sign = XOR(a0, b0)
  2. zero detection
  3. M-type (mantissa factor: 1.5^0=1 or 1.5^1=1.5)
  4. exponent sum (2-bit + 2-bit → 3-bit)
  5. K-type and shift from M-sum and E-sum
  6. output bit generation
  7. conditional negation
  8. zero masking
"""

# ── Input remapping ───────────────────────────────────────────────────────────
# This will be replaced by the best remapping found by experiments.
# Default: canonical (M, E+1) where mag = 1.5^M * 2^E
# Encoding: sign bit | M bit | (E+1) high | (E+1) low
# So for positive magnitudes: 0 | M | e1 | e0   where E+1 = 2*e1 + e0

try:
    import ml_dtypes
    from ml_dtypes import uint4, float4_e2m1fn

    def build_remap():
        # Non-zero magnitudes: 0.5, 1, 1.5, 2, 3, 4, 6
        # mag = 1.5^M * 2^E
        # 0.5 = 1.5^0 * 2^(-1): M=0, E=-1 → E+1=0 → code = 0|0|0|0 = 0  but wait sign=0
        # Let's use 3-bit magnitude code = M*4 + (E+1)
        # 0.5: M=0, E=-1, E+1=0 → 000 → full code (sign=0) = 0000
        # 1.0: M=0, E=0,  E+1=1 → 001 → 0001
        # 2.0: M=0, E=1,  E+1=2 → 010 → 0010
        # 4.0: M=0, E=2,  E+1=3 → 011 → 0011
        # 1.5: M=1, E=-1, E+1=0 → 100 → 0100
        # 3.0: M=1, E=0,  E+1=1 → 101 → 0101
        # 6.0: M=1, E=1,  E+1=2 → 110 → 0110
        # 0:   zero              → 0111 (or any unused code)
        # Negative: sign bit = 1, same magnitude codes
        mag_to_3bit = {
            0.5: 0b000,   # M=0, E+1=0
            1.0: 0b001,   # M=0, E+1=1
            2.0: 0b010,   # M=0, E+1=2
            4.0: 0b011,   # M=0, E+1=3
            1.5: 0b100,   # M=1, E+1=0
            3.0: 0b101,   # M=1, E+1=1
            6.0: 0b110,   # M=1, E+1=2
            0.0: 0b111,   # zero (unused slot)
        }

        vals = [0.0, 0.5, 1.0, 1.5, 2.0, 3.0, 4.0, 6.0,
                0.0, -0.5, -1.0, -1.5, -2.0, -3.0, -4.0, -6.0]

        remap = {}
        for i, v in enumerate(vals):
            fp4 = uint4(i).view(float4_e2m1fn)
            sign = 1 if v < 0 else 0
            mag = abs(v)
            mag_code = mag_to_3bit[mag]
            new_code = (sign << 3) | mag_code
            remap[fp4] = uint4(new_code)
        return remap

    INPUT_REMAP = build_remap()

except ImportError:
    INPUT_REMAP = None


# ── Circuit implementation ────────────────────────────────────────────────────

def write_your_multiplier_here(a0, a1, a2, a3, b0, b1, b2, b3,
                                NOT=None, AND=None, OR=None, XOR=None):
    """
    FP4 multiplier using canonical (M, E+1) encoding.

    With the above remap:
      a0 = sign of a
      a1 = M bit of a (1 if magnitude has factor 1.5)
      a2 = (E+1) high bit
      a3 = (E+1) low bit
      Same for b.

    Zero is encoded as 0b0111 → a0=0, a1=1, a2=1, a3=1
    So: zero_a = AND(a1, AND(a2, a3)) AND NOT(a0) ... but for negative zero it's 0b1111
    Better: zero_a = AND(a1, AND(a2, a3))   [true for both +0 and -0 since mag_code=111]

    Magnitude bits:
      a1 = M_a (mantissa flag)
      a2,a3 = (E_a+1) high,low  (2-bit exponent offset)
    """
    # Fallback if not injected (for compatibility with original test harness)
    if NOT is None:
        NOT = lambda x: not x
        AND = lambda x, y: x & y
        OR = lambda x, y: x | y
        XOR = lambda x, y: x ^ y

    # ── 1. Sign ────────────────────────────────────────────────────────────────
    sign = XOR(a0, b0)   # 1 gate

    # ── 2. Zero detection ──────────────────────────────────────────────────────
    # With our encoding, zero = mag_code 111 (a1=a2=a3=1)
    # zero_a = a1 AND a2 AND a3
    a2_and_a3 = AND(a2, a3)          # 1 gate
    zero_a = AND(a1, a2_and_a3)      # 1 gate

    b2_and_b3 = AND(b2, b3)          # 1 gate
    zero_b = AND(b1, b2_and_b3)      # 1 gate

    either_zero = OR(zero_a, zero_b) # 1 gate   → 5 gates total for zero

    # ── 3. M-type flags ────────────────────────────────────────────────────────
    # a1 = M_a: 1 if magnitude of a has factor 1.5 (i.e., mag ∈ {1.5, 3, 6})
    # b1 = M_b: same for b
    # But for zero (mag_code=111), a1=1 too — we'll mask at the end anyway
    M_a = a1   # free (already an input)
    M_b = b1   # free

    # M_sum = M_a + M_b ∈ {0, 1, 2}
    # K = 1.5^M_sum: K=1 if M_sum=0, K=3/2 if M_sum=1 (→ K=3 after ×2), K=9/4 if M_sum=2 (→ K=9 after ×4)
    # Actually the product is: |4*a*b| = 1.5^(M_a+M_b) * 2^(E_a+E_b+2)
    # = K_raw * 2^shift  where K_raw = 1.5^(M_a+M_b)
    # But 1.5^0=1, 1.5^1=3/2, 1.5^2=9/4 — non-integer!
    # We need to fold in powers of 2:
    # M_sum=0: K=1, no extra shift
    # M_sum=1: K=3, subtract 1 from shift (3/2 * 2^k = 3 * 2^(k-1))
    # M_sum=2: K=9, subtract 2 from shift (9/4 * 2^k = 9 * 2^(k-2))
    # So effective shift = (E_a+E_b+2) - M_sum
    #                    = (E_a + E_b) + 2 - M_sum

    # ── 4. Exponent addition ───────────────────────────────────────────────────
    # E_a = a2,a3 represent E_a+1 ∈ {0,1,2,3}
    # E_b = b2,b3 represent E_b+1 ∈ {0,1,2,3}
    # E_a+E_b+2 = (E_a+1) + (E_b+1) = sum of two 2-bit numbers ∈ {0..6}
    # = 3-bit value: s2 s1 s0

    # 2-bit adder for (a2,a3) + (b2,b3):
    s0 = XOR(a3, b3)                       # 1 gate  (LSB of sum)
    c0 = AND(a3, b3)                       # 1 gate  (carry from bit 0)
    s1_xor = XOR(a2, b2)                   # 1 gate
    s1 = XOR(s1_xor, c0)                   # 1 gate  (middle bit of sum)
    s2 = OR(AND(a2, b2), AND(s1_xor, c0)) # 3 gates (MSB / carry out)
    # s2 s1 s0 = (E_a+1) + (E_b+1) ∈ {0..6}   (5 gates)

    # ── 5. Adjust shift for M_sum ─────────────────────────────────────────────
    # We need: shift = s - M_sum where s = s2 s1 s0 (3-bit) and M_sum ∈ {0,1,2}
    # M_sum = M_a + M_b: computed as a 2-bit sum
    m_s0 = XOR(M_a, M_b)             # 1 gate  (LSB of M_sum)
    m_c0 = AND(M_a, M_b)             # 1 gate  (carry = MSB of M_sum, since max=2)
    # M_sum as 2 bits: (m_c0, m_s0)

    # shift = s - M_sum = (s2 s1 s0) - (m_c0 m_s0)
    # Subtraction: shift = s + ~M_sum + 1  (two's complement)
    # ~M_sum = (~m_c0, ~m_s0) + 1 (but we're adding 2-bit negation to 3-bit)
    # Alternatively, just compute the 3-bit subtraction directly.
    # shift range: s ∈ {0..6}, M_sum ∈ {0..2} → shift ∈ {-2..6}
    # But in practice:
    #   M_sum=0: s = E_a+E_b ∈ {0..6}, shift = s
    #   M_sum=1: shift = s-1 ∈ {-1..5}, but s >= 1 always when M_sum=1? Not necessarily.
    #   M_sum=2: shift = s-2 ∈ {-2..4}, but s >= 2 when M_sum=2? Not necessarily.
    # Actually for the non-zero case: E ∈ {-1,0,1,2} so E+1 ∈ {0,1,2,3}
    # When M=1: magnitudes are 1.5(E=-1), 3(E=0), 6(E=1), so E+1 ∈ {0,1,2}
    # When M=0: magnitudes are 0.5(E=-1), 1(E=0), 2(E=1), 4(E=2), so E+1 ∈ {0,1,2,3}
    # So for M_sum=1: at least one M=1 means E+1 ∈ {0,1,2}
    #   s = (E_a+1) + (E_b+1), shift = s - 1 ≥ -1
    #   But with zero masked, we don't care about zero inputs.
    # For M_sum=2: both M=1, so both E+1 ∈ {0,1,2}
    #   s ∈ {0..4}, shift = s - 2 ≥ -2
    #   But min E+1 for M=1 is 0 (for 1.5), and 0+0-2 = -2... but 1.5×1.5×4=9, shift should give k s.t. 9 = 9*2^k → k=0
    #   Check: s = 0+0 = 0, M_sum=2, shift = 0-2 = -2? That would mean 9 * 2^(-2) = 9/4 ≠ 9.
    # Wait, I need to recheck.
    #
    # Let me recompute: |4*a*b| = 1.5^(M_a+M_b) * 2^(E_a+E_b+2)
    # For a=1.5 (M=1, E=-1) and b=1.5 (M=1, E=-1):
    #   = 1.5^2 * 2^(-1-1+2) = 2.25 * 2^0 = 2.25? But 4*1.5*1.5=9, not 2.25!
    #
    # Let me redo the math. mag = 1.5^M * 2^E. For 1.5: M=1, E=0 (since 1.5 = 1.5^1 * 2^0).
    # Wait, I need to recheck what E values the existing code uses.
    # From fp4_structure_analysis.py: "mag = 1.5^M * 2^E" with E ∈ {-1,0,1,2}
    # 0.5 = 1.5^0 * 2^(-1): M=0, E=-1 ✓
    # 1.0 = 1.5^0 * 2^0:    M=0, E=0  ✓
    # 2.0 = 1.5^0 * 2^1:    M=0, E=1  ✓
    # 4.0 = 1.5^0 * 2^2:    M=0, E=2  ✓
    # 1.5 = 1.5^1 * 2^0:    M=1, E=0  ✓
    # 3.0 = 1.5^1 * 2^1:    M=1, E=1  ✓
    # 6.0 = 1.5^1 * 2^2:    M=1, E=2  ✓
    # So E ∈ {-1,0,1,2} for M=0 and E ∈ {0,1,2} for M=1.
    # E+1 ∈ {0,1,2,3} for M=0 and E+1 ∈ {1,2,3} for M=1.
    #
    # Now |4*a*b| = 4 * 1.5^(M_a+M_b) * 2^(E_a+E_b)
    #            = 1.5^(M_a+M_b) * 2^(E_a+E_b+2)
    # For a=1.5 (M=1,E=0), b=1.5 (M=1,E=0):
    #   = 1.5^2 * 2^(0+0+2) = 2.25 * 4 = 9 ✓
    #
    # So sum = (E_a+1) + (E_b+1) = (E_a+E_b+2)  ← this is the 3-bit sum s2 s1 s0
    # For a=1.5: E_a+1 = 0+1 = 1. For b=1.5: E_b+1 = 0+1 = 1. Sum = 2.
    # shift = sum - M_sum = 2 - 2 = 0. K = 9. So 9 * 2^0 = 9. ✓
    #
    # For a=0.5 (M=0,E=-1): E_a+1=0. For b=0.5 (M=0,E=-1): E_b+1=0. Sum=0. M_sum=0. shift=0. K=1. 1*2^0=1. ✓ (4*0.5*0.5=1)
    # For a=6 (M=1,E=2): E_a+1=3. For b=6 (M=1,E=2): E_b+1=3. Sum=6. M_sum=2. shift=4. K=9. 9*2^4=144. ✓ (4*6*6=144)
    # For a=1 (M=0,E=0): E_a+1=1. For b=6 (M=1,E=2): E_b+1=3. Sum=4. M_sum=1. shift=3. K=3. 3*2^3=24. ✓ (4*1*6=24)
    #
    # Great! So: shift = s - M_sum, K determined by M_sum (0→1, 1→3, 2→9)
    # shift ∈ {0..6} for valid non-zero inputs (can verify: max shift = 6 when a=4,b=4,M_sum=0)

    # shift = s - M_sum (3-bit unsigned result, guaranteed ≥ 0 for valid inputs)
    # We compute: shift2, shift1, shift0 = s2 s1 s0 minus m_c0 m_s0
    # Using ripple-borrow subtractor:
    # diff_0 = s0 XOR m_s0          borrow_0 = (NOT s0) AND m_s0
    # diff_1 = s1 XOR m_c0 XOR borrow_0   borrow_1 = ...
    # diff_2 = s2 XOR borrow_1

    diff_0 = XOR(s0, m_s0)                    # 1 gate
    borrow_0 = AND(NOT(s0), m_s0)             # 2 gates
    diff_1_xor = XOR(s1, m_c0)               # 1 gate
    diff_1 = XOR(diff_1_xor, borrow_0)        # 1 gate
    borrow_1 = OR(AND(NOT(s1), m_c0),         # need: borrow if (s1<m_c0) OR (s1==m_c0 AND borrow_0)
                  AND(NOT(diff_1_xor), borrow_0))  # 4 gates
    diff_2 = XOR(s2, borrow_1)                # 1 gate

    # shift = diff_2, diff_1, diff_0  (3-bit, MSB first)   11 gates for subtract

    # ── 6. K-type flags ────────────────────────────────────────────────────────
    # K=1: M_sum=0 → m_c0=0, m_s0=0
    # K=3: M_sum=1 → m_c0=0, m_s0=1
    # K=9: M_sum=2 → m_c0=1, m_s0=0

    # k_is_1 = NOT(m_c0) AND NOT(m_s0)
    not_mc0 = NOT(m_c0)                # 1 gate
    not_ms0 = NOT(m_s0)                # 1 gate
    k_is_1 = AND(not_mc0, not_ms0)    # 1 gate  (K=1 when M_sum=0)
    k_is_3 = AND(not_mc0, m_s0)       # 1 gate  (K=3 when M_sum=1)
    k_is_9 = m_c0                      # free    (K=9 when M_sum=2, i.e. m_c0=1)

    # ── 7. Output bit generation ───────────────────────────────────────────────
    # Output magnitude = K * 2^shift, shift ∈ {0..6}, K ∈ {1,3,9}
    # 8-bit unsigned output bits (bit 7 = MSB, bit 0 = LSB):
    #
    # For K=1: exactly bit 'shift' is set
    # For K=3: bits 'shift' and 'shift+1' are set  (3 = 0b11 = 2^1 + 2^0, shifted by shift)
    # For K=9: bits 'shift' and 'shift+3' are set  (9 = 0b1001 = 2^3 + 2^0, shifted by shift)
    #
    # We need to compute 8 output bits (m7..m0) for the magnitude.
    # Each bit m_i = 1 iff:
    #   (K=1 AND shift=i) OR
    #   (K=3 AND (shift=i OR shift=i-1)) OR
    #   (K=9 AND (shift=i OR shift=i-3))
    #
    # shift is 3-bit: (diff_2, diff_1, diff_0), values 0..6
    # Let's decode shift using the 3-bit value:
    # sh=0: d2=0,d1=0,d0=0
    # sh=1: d2=0,d1=0,d0=1
    # sh=2: d2=0,d1=1,d0=0
    # sh=3: d2=0,d1=1,d0=1
    # sh=4: d2=1,d1=0,d0=0
    # sh=5: d2=1,d1=0,d0=1
    # sh=6: d2=1,d1=1,d0=0
    # (sh=7 not valid for our inputs)
    #
    # For brevity: d0=diff_0, d1=diff_1, d2=diff_2
    d0 = diff_0
    d1 = diff_1
    d2 = diff_2

    not_d0 = NOT(d0)   # 1 gate
    not_d1 = NOT(d1)   # 1 gate
    not_d2 = NOT(d2)   # 1 gate

    # Shift decoder: sh_i = (shift == i)
    # sh_0 = ~d2 & ~d1 & ~d0
    sh_0 = AND(AND(not_d2, not_d1), not_d0)  # 2 gates
    # sh_1 = ~d2 & ~d1 & d0
    sh_1 = AND(AND(not_d2, not_d1), d0)      # 2 gates
    # sh_2 = ~d2 & d1 & ~d0
    sh_2 = AND(AND(not_d2, d1), not_d0)      # 2 gates
    # sh_3 = ~d2 & d1 & d0
    sh_3 = AND(AND(not_d2, d1), d0)          # 2 gates
    # sh_4 = d2 & ~d1 & ~d0
    sh_4 = AND(AND(d2, not_d1), not_d0)      # 2 gates
    # sh_5 = d2 & ~d1 & d0
    sh_5 = AND(AND(d2, not_d1), d0)          # 2 gates
    # sh_6 = d2 & d1 & ~d0
    sh_6 = AND(AND(d2, d1), not_d0)          # 2 gates
    # 14 gates for shift decoder

    # Magnitude bit i:
    # m_i = (k_is_1 AND sh_i) OR
    #       (k_is_3 AND (sh_i OR sh_{i-1})) OR
    #       (k_is_9 AND (sh_i OR sh_{i-3}))
    # where sh_{negative} = 0

    def mag_bit(i, sh):
        """Compute magnitude output bit i. sh is list [sh0..sh6]."""
        # Contribution from K=1
        term_k1 = AND(k_is_1, sh[i]) if 0 <= i <= 6 else False

        # Contribution from K=3 (bit i set when shift=i or shift=i-1)
        k3_terms = []
        if 0 <= i <= 6:
            k3_terms.append(AND(k_is_3, sh[i]))
        if 0 <= i-1 <= 6:
            k3_terms.append(AND(k_is_3, sh[i-1]))
        if k3_terms:
            term_k3 = k3_terms[0]
            for t in k3_terms[1:]:
                term_k3 = OR(term_k3, t)
        else:
            term_k3 = False

        # Contribution from K=9 (bit i set when shift=i or shift=i-3)
        k9_terms = []
        if 0 <= i <= 6:
            k9_terms.append(AND(k_is_9, sh[i]))
        if 0 <= i-3 <= 6:
            k9_terms.append(AND(k_is_9, sh[i-3]))
        if k9_terms:
            term_k9 = k9_terms[0]
            for t in k9_terms[1:]:
                term_k9 = OR(term_k9, t)
        else:
            term_k9 = False

        # Combine: OR all non-False terms
        all_terms = [t for t in [term_k1, term_k3, term_k9] if t is not False]
        if not all_terms:
            return False
        result = all_terms[0]
        for t in all_terms[1:]:
            result = OR(result, t)
        return result

    sh = [sh_0, sh_1, sh_2, sh_3, sh_4, sh_5, sh_6]

    m7 = mag_bit(7, sh)  # bit 7 (2^7 = 128): K=1,sh=7(invalid) OR K=3,sh=6 OR K=9,sh=4 or 7(invalid)
    m6 = mag_bit(6, sh)  # bit 6 (2^6 = 64):  K=1,sh=6 OR K=3,sh=5 or 6 OR K=9,sh=3 or 6
    m5 = mag_bit(5, sh)  # bit 5
    m4 = mag_bit(4, sh)  # bit 4
    m3 = mag_bit(3, sh)  # bit 3
    m2 = mag_bit(2, sh)  # bit 2
    m1 = mag_bit(1, sh)  # bit 1
    m0 = mag_bit(0, sh)  # bit 0 (2^0 = 1): K=1,sh=0 OR K=3,sh=0(-1 invalid) OR K=9,sh=0(-3 invalid)

    # ── 8. Conditional two's complement negation ──────────────────────────────
    # If sign=1: result = -magnitude (two's complement)
    # If sign=0: result = magnitude
    # Two's complement: flip bits XOR sign, add 1 (carry chain)
    # result_i = XOR(m_i, sign) XOR carry_i
    # carry_{i+1} = AND(XOR(m_i, sign), carry_i), carry_0 = sign

    # We work LSB to MSB (m0 = LSB)
    t0 = XOR(m0, sign)   # 1
    r8 = XOR(t0, sign)   # Wait — carry_0 = sign, so r8 = XOR(t0, sign) = XOR(XOR(m0,sign), sign) = m0
    # Hmm that's wrong for negative case. Let me redo.
    # For two's complement:
    #   flipped_i = XOR(m_i, sign)   [flip if sign=1]
    #   result[LSB] = flipped_0, carry_1 = AND(flipped_0, carry_0) where carry_0=sign
    #   Wait: two's complement = flipped + sign (treating sign as the +1)
    #   result_0 = XOR(flipped_0, sign)  ... but flipped_0 = XOR(m_0, sign)
    #   result_0 = XOR(XOR(m_0, sign), sign) = m_0? No that doesn't work for negation.
    #
    # Standard conditional two's complement:
    #   t_i = XOR(m_i, sign)         [conditionally flip]
    #   result_0 = t_0 (no carry in)
    #   carry_0 = 0
    #   carry_{i+1} = AND(NOT(t_i), carry_i) is wrong too.
    #
    # Correct formula: -x = ~x + 1
    #   If sign=0: output = x
    #   If sign=1: output = ~x + 1 = XOR(x, 1...1) + 1
    # For conditional: output_i = x_i XOR sign XOR carry_i
    #   carry_0 = sign (the +1 we're adding)
    #   carry_{i+1} = AND(x_i XOR sign, carry_i) [carry propagates when flipped bit = 1]
    #   Actually carry_{i+1} = carry when current sum digit = 0: NOT(t_i XOR carry_i) = ...
    # Let me just use the standard ripple approach:
    #   r_i = t_i XOR c_i
    #   c_{i+1} = t_i AND c_i  [carry when both t_i=1 and c_i=1]
    # Wait, adding 1 to ~x:
    #   At bit 0: ~x_0 + 1, sum = ~x_0 XOR 1 = x_0, carry = ~x_0 AND 1 = NOT(x_0)
    #   Hmm, so carry_1 = NOT(x_0) when sign=1
    # Let me use the known-correct formula:
    # c_0 = sign
    # t_i = XOR(m_i, sign)
    # r_i = XOR(t_i, c_i)
    # c_{i+1} = AND(t_i, c_i)   [carry propagates when flipped bit=1 AND carry_in=1]
    # This is correct: r_i = m_i XOR sign XOR c_i
    # When sign=0: c_0=0, t_i=m_i, r_i=m_i XOR 0 = m_i ✓
    # When sign=1: c_0=1, t_0=NOT(m_0), r_0=NOT(m_0) XOR 1 = m_0?
    #   No: r_0 = XOR(t_0, c_0) = XOR(NOT(m_0), 1) = m_0. That's the two's complement of the LSB? Let me check:
    #   -1 = 111...111. m_0=1 → r_0=1. ✓ (NOT(1) XOR 1 = 0 XOR 1 = 1)
    #   -2 = 111...110. m_0=0 → t_0=NOT(0)=1, r_0=XOR(1,1)=0. ✓ (LSB of -2 is 0)
    #   But carry: c_1 = AND(t_0, c_0) = AND(1,1)=1 for -2 case. ✓
    # OK so formula is: t_i = XOR(m_i, sign); r_i = XOR(t_i, c_i); c_{i+1} = AND(t_i, c_i); c_0 = sign.

    c_in = sign  # free (alias)

    t_m0 = XOR(m0, sign);  r8_bit = XOR(t_m0, c_in);  c1 = AND(t_m0, c_in)
    t_m1 = XOR(m1, sign);  r7_bit = XOR(t_m1, c1);    c2 = AND(t_m1, c1)
    t_m2 = XOR(m2, sign);  r6_bit = XOR(t_m2, c2);    c3 = AND(t_m2, c2)
    t_m3 = XOR(m3, sign);  r5_bit = XOR(t_m3, c3);    c4 = AND(t_m3, c3)
    t_m4 = XOR(m4, sign);  r4_bit = XOR(t_m4, c4);    c5 = AND(t_m4, c4)
    t_m5 = XOR(m5, sign);  r3_bit = XOR(t_m5, c5);    c6 = AND(t_m5, c5)
    t_m6 = XOR(m6, sign);  r2_bit = XOR(t_m6, c6);    c7 = AND(t_m6, c6)
    t_m7 = XOR(m7, sign);  r1_bit = XOR(t_m7, c7)
    # sign bit of result: r0 = sign (for two's complement, the sign bit extends)
    r0_bit = sign  # free (the sign of the result is the XOR of input signs)

    # ── 9. Zero masking ────────────────────────────────────────────────────────
    # If either input is zero, all output bits must be 0
    not_zero = NOT(either_zero)   # 1 gate

    res0 = AND(r0_bit, not_zero)  # 1 gate
    res1 = AND(r1_bit, not_zero)  # 1 gate
    res2 = AND(r2_bit, not_zero)  # 1 gate
    res3 = AND(r3_bit, not_zero)  # 1 gate
    res4 = AND(r4_bit, not_zero)  # 1 gate
    res5 = AND(r5_bit, not_zero)  # 1 gate
    res6 = AND(r6_bit, not_zero)  # 1 gate
    res7 = AND(r7_bit, not_zero)  # 1 gate
    res8 = AND(r8_bit, not_zero)  # 1 gate   (9 gates for masking)

    return res0, res1, res2, res3, res4, res5, res6, res7, res8


# ── Quick self-test ───────────────────────────────────────────────────────────
if __name__ == "__main__":
    import sys
    sys.path.insert(0, '..')
    from eval_circuit import evaluate_fast

    print("Testing baseline multiplier...")

    # Build remap as raw int list
    mag_to_3bit = {
        0.5: 0b000, 1.0: 0b001, 2.0: 0b010, 4.0: 0b011,
        1.5: 0b100, 3.0: 0b101, 6.0: 0b110, 0.0: 0b111,
    }
    FP4_TABLE = [0.0, 0.5, 1.0, 1.5, 2.0, 3.0, 4.0, 6.0,
                 0.0, -0.5, -1.0, -1.5, -2.0, -3.0, -4.0, -6.0]
    remap_int = []
    for i, v in enumerate(FP4_TABLE):
        sign = 1 if v < 0 else 0
        mag = abs(v)
        mag_code = mag_to_3bit[mag]
        remap_int.append((sign << 3) | mag_code)

    # Patch evaluate_fast to use int remap
    from fp4_core import MAGNITUDES, build_truth_table, FP4_VALUES

    perm = (0, 1, 2, 3, 4, 5, 6, 7)  # placeholder — real remap is above

    # Use evaluate_fast with our int remap converted to INPUT_REMAP format
    try:
        import ml_dtypes
        from ml_dtypes import uint4, float4_e2m1fn
        remap_dict = {}
        for i, v in enumerate(FP4_TABLE):
            fp4 = uint4(i).view(float4_e2m1fn)
            sign = 1 if v < 0 else 0
            mag = abs(v)
            mag_code = mag_to_3bit[mag]
            new_code = (sign << 3) | mag_code
            remap_dict[fp4] = uint4(new_code)

        correct, gate_count, errors = evaluate_fast(write_your_multiplier_here, remap_dict, verbose=True)
        status = "CORRECT" if correct else f"WRONG ({len(errors)} errors)"
        print(f"\nResult: {status}")
        print(f"Gates:  {gate_count}")
    except ImportError:
        print("ml_dtypes not available, skipping full test")
