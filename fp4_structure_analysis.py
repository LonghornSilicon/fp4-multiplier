"""
Structural analysis of FP4 multiplication.

Key mathematical structure:
  Each non-zero FP4 magnitude = 1.5^M * 2^E
  where M ∈ {0,1}, E ∈ {-1, 0, 1, 2}

Product x4 = 1.5^(Ma+Mb) * 2^(Ea+Eb+2) = K * 2^k
  where K = {1,3,9}[Ma+Mb], k = Ea+Eb+2

Output bit pattern in 8-bit unsigned:
  K=1: single 1-bit at position k     (bit k set)
  K=3: bits at positions k and k+1    (00011 pattern shifted by k)
  K=9: bits at positions k and k+3    (01001 pattern shifted by k)

This script derives the minimum gate circuit analytically using this structure.
"""

import itertools
from fp4_core import FP4_VALUES, MAGNITUDES, build_truth_table, tt_to_bit_functions

# ─── Map each magnitude to (E, M) ────────────────────────────────────────────

def decompose(mag):
    """Return (E, M) s.t. mag = 1.5^M * 2^E, or None for zero."""
    if mag == 0:
        return None
    for E in range(-1, 3):
        for M in range(2):
            if abs(mag - (1.5 ** M) * (2 ** E)) < 1e-9:
                return (E, M)
    raise ValueError(f"Cannot decompose {mag}")


# Decompose all magnitudes
DECOMP = [decompose(m) for m in MAGNITUDES]
print("Magnitude -> (E, M):")
for m, d in zip(MAGNITUDES, DECOMP):
    print(f"  {m:4.1f} -> {d}")

# ─── Analyze what each output bit depends on ─────────────────────────────────

def analyze_output_bit_i(bit_i_from_lsb: int, mag_perm: tuple = None):
    """
    For output bit at position bit_i_from_lsb (0=LSB, 7=MSB of magnitude),
    find all input magnitude pairs that produce a 1 in this bit.
    """
    if mag_perm is None:
        mag_perm = tuple(range(8))

    cases = []
    for a_idx in range(8):
        for b_idx in range(8):
            a_mag = MAGNITUDES[a_idx]
            b_mag = MAGNITUDES[b_idx]
            val = round(a_mag * b_mag * 4)
            bit = (val >> bit_i_from_lsb) & 1
            if bit:
                da = DECOMP[a_idx]
                db = DECOMP[b_idx]
                cases.append((a_mag, b_mag, da, db, val))
    return cases


print("\n=== What makes bit 0 (LSB = 0.25 value) = 1? ===")
cases0 = analyze_output_bit_i(0)
for a, b, da, db, val in cases0:
    print(f"  {a}×{b}={a*b:.3f} (QI9={val}) | da={da}, db={db}")

print("\n=== What makes bit 1 (= 0.5 value) = 1? ===")
cases1 = analyze_output_bit_i(1)
for a, b, da, db, val in cases1:
    print(f"  {a}×{b}={a*b:.3f} (QI9={val}) | da={da}, db={db}")

print("\n=== What makes bit 3 (= 2 value) = 1? ===")
cases3 = analyze_output_bit_i(3)
for a, b, da, db, val in cases3[:20]:
    print(f"  {a}×{b}={a*b:.3f} (QI9={val}) | da={da}, db={db}")

# ─── Best encoding for magnitude circuit ─────────────────────────────────────

def evaluate_encoding(mag_perm: tuple):
    """
    For a given magnitude permutation, analyze how the circuit works.
    The magnitude circuit has 6 inputs (a1,a2,a3,b1,b2,b3 after remapping).
    """
    mag_tt = {}
    for a_idx in range(8):
        for b_idx in range(8):
            a_mag = MAGNITUDES[a_idx]
            b_mag = MAGNITUDES[b_idx]
            val = round(a_mag * b_mag * 4)
            bits = [(val >> (7 - i)) & 1 for i in range(8)]
            a_code = mag_perm[a_idx]
            b_code = mag_perm[b_idx]
            mag_tt[(a_code, b_code)] = bits
    return mag_tt


# ─── The "canonical" encoding based on (M, E) structure ─────────────────────

# Best encoding candidate: encode as (m_bit, e1_bit, e0_bit)
# where e1,e0 = biased exponent E+1 (from 0 to 3), m = mantissa bit
# Zero gets the "invalid" slot (m=1, e=0) = 0b100

# Magnitude index  -> (E, M) -> code (m, e1, e0)
# 0:   zero        -> None   -> 100 (invalid slot)
# 0.5: E=-1, M=0  -> (0, 0, 0) = 000
# 1:   E=0,  M=0  -> (0, 0, 1) = 001
# 1.5: E=0,  M=1  -> (1, 0, 1) = 101
# 2:   E=1,  M=0  -> (0, 1, 0) = 010
# 3:   E=1,  M=1  -> (1, 1, 0) = 110
# 4:   E=2,  M=0  -> (0, 1, 1) = 011
# 6:   E=2,  M=1  -> (1, 1, 1) = 111

CANONICAL_PERM = (0b100, 0b000, 0b001, 0b101, 0b010, 0b110, 0b011, 0b111)
print(f"\n=== Canonical (M,E+1) encoding ===")
print("Magnitude -> code:")
for i, (mag, code) in enumerate(zip(MAGNITUDES, CANONICAL_PERM)):
    m = (code >> 2) & 1
    e1 = (code >> 1) & 1
    e0 = code & 1
    d = DECOMP[i]
    print(f"  {mag:4.1f} -> {code:03b} (m={m}, e={e1}{e0}) | (E,M)={d}")

# ─── Derive the circuit equations for the canonical encoding ─────────────────

print("\n=== Circuit equations for canonical encoding ===")
print("""
Input bits: a0(sign), a1(m_a), a2(e1_a), a3(e0_a)
            b0(sign), b1(m_b), b2(e1_b), b3(e0_b)

For positive × positive (a0=0, b0=0):

1. Zero detection:
   zero_a = AND(a1, NOT(a2), NOT(a3))  [code 100 = zero]
   zero_b = AND(b1, NOT(b2), NOT(b3))
   any_zero = OR(zero_a, zero_b)

2. Mantissa:
   Ma = a1 (m bit for a)
   Mb = b1 (m bit for b)
   type0 = AND(Ma, Mb)        [K=9 case: both mantissas = 1]
   type1 = OR(Ma, Mb)         [K=3 or K=9 case: at least one mantissa = 1]

3. Exponent:
   Ea = 2*a2 + a3 - 1  (actual exponent, from biased E+1 code)
   Eb = 2*b2 + b3 - 1
   k = Ea + Eb + 2 = (a2*2+a3-1) + (b2*2+b3-1) + 2 = 2*a2+a3+2*b2+b3
   This is a 2-bit + 2-bit addition: k = a2a3_val + b2b3_val
   where a2a3_val = 2*a2+a3 ∈ {0,1,2,3} and b2b3_val ∈ {0,1,2,3}

4. k ranges from 0 to 6 (3-bit sum of two 2-bit numbers):
   k = s2*4 + s1*2 + s0*1
   Standard 2-bit adder circuit.

5. For each output bit i (0=LSB, 7=MSB):
   bit_i = 1 iff:
     (k==i AND not_any_zero) [K=1 case, k matches exactly]
     OR (k==i-1 AND type1 AND not_any_zero) [K=3 or K=9 bit at k+1]
     OR (k==i-3 AND type0 AND not_any_zero) [K=9 bit at k+3]

6. Absolute value of output:
   The 8 magnitude bits follow the above pattern.
   res0 = XOR(a0, b0)  [sign]

7. Conditional two's complement negation:
   For negative results: negate the 8 magnitude bits + 1 (ripple carry)
""")

# ─── Estimate gate count for canonical encoding ──────────────────────────────

def estimate_canonical_gates():
    """
    Estimate gate count for the canonical encoding circuit.
    This is a STRUCTURAL estimate, not from QM.
    """
    gates = {}

    # 1. Sign bit
    gates['res0 = XOR(a0,b0)'] = 1

    # 2. Zero detection (2 per input, 1 to combine)
    # zero_a = AND(a1, NOT(a2), NOT(a3)) = NOT(a2), NOT(a3), AND(a1,NOT(a2)), AND(...,NOT(a3))
    # Wait: zero_a is when code=100, meaning a1=1, a2=0, a3=0
    # zero_a = a1 AND (NOT a2) AND (NOT a3) = 3 gates: NOT(a2)=t1, NOT(a3)=t2, AND(AND(a1,t1),t2)
    # But we can simplify: AND(a1, NOR(a2, a3))... NOR not primitive, so:
    # t1 = OR(a2, a3) [1 gate], t2 = NOT(t1) [1 gate], zero_a = AND(a1, t2) [1 gate] = 3 gates
    # Similarly 3 for zero_b
    # any_zero = OR(zero_a, zero_b) = 1 gate
    # Total zero detection: 7 gates
    gates['zero_a'] = 3
    gates['zero_b'] = 3
    gates['any_zero'] = 1

    # 3. Mantissa type
    # type0 = AND(a1, b1) - BUT only valid for non-zero inputs
    # type1 = OR(a1, b1)
    # However, a1=1 for BOTH zero (code=100) and mantissa values 1.5,3,6 (codes 101,110,111)
    # So a1 ≠ mantissa in canonical encoding! a1 is the M bit ONLY for non-zero values.
    # For zero (code=100): a1=1, but it's not a mantissa=1 value.
    # So: Ma_true = a1 AND NOT(zero_a), Mb_true = b1 AND NOT(zero_b)
    # = AND(a1, NOT(zero_a))
    # But NOT(zero_a) is expensive... unless we handle zero differently.
    # Alternative: since we'll AND with any_zero at the end anyway,
    # we can use a1 as an approximation for Ma and correct later.
    # For now, assume a1 = Ma (correct for non-zero, irrelevant for zero output).
    gates['type0 = AND(a1,b1)'] = 1   # AND(Ma, Mb)
    gates['type1 = OR(a1,b1)'] = 1    # OR(Ma, Mb)

    # 4. Exponent adder: k = a2a3_val + b2b3_val (2-bit + 2-bit = 3-bit sum)
    # Standard ripple carry adder:
    # s0 = XOR(a3, b3) [1], c0 = AND(a3, b3) [1]
    # s1 = XOR(XOR(a2, b2), c0) [2], c1 = AND(a2,b2) OR AND(XOR(a2,b2),c0) [3]
    # s2 = XOR(XOR(0, 0), c1) = c1 [0 extra gates]
    # Wait: a2a3_val is a 2-bit number. Adding two 2-bit numbers:
    # k3_bit = s2 (carry out), k2 = s1, k1 = s0
    # Hmm, I need to be careful about bit ordering.
    # k = E_a + E_b + 2 = (a2*2+a3) + (b2*2+b3)
    # k0 (LSB) = XOR(a3, b3) [1 gate] = s0; carry_0 = AND(a3,b3) [1 gate]
    # k1 = XOR(XOR(a2, b2), carry_0) [2 gates];
    # carry_1 = OR(AND(a2,b2), AND(XOR(a2,b2),carry_0)) [4 gates] or just...
    #   = AND(a2,b2) OR AND(XOR(a2,b2),carry_0) = 1 AND + 1 AND + 1 OR = 3 gates
    # k2 (MSB of k) = carry_1 [0 extra]
    # Total adder: 1+1+2+3 = 7 gates, produces k0, k1, k2 = carry_1
    gates['2bit_adder'] = 7  # k0, k1, k2

    # 5. Output bit computation
    # For each bit i (0..7), output_mag_bit_i =
    #   decoder(k==i) [k decoder] AND NOT(any_zero)
    #   OR decoder(k==i-1) AND type1 AND NOT(any_zero)
    #   OR decoder(k==i-3) AND type0 AND NOT(any_zero)
    # Factor out NOT(any_zero):
    # output_mag_bit_i = NOT(any_zero) AND [decoder(k==i) OR decoder(k==i-1) AND type1 OR decoder(k==i-3) AND type0]

    # k decoder: k is a 3-bit number (values 0..6)
    # Decoding k==0..6 costs how many gates?
    # k=0: NOT(k2) AND NOT(k1) AND NOT(k0) = 4 gates (2 NOT + 2 AND, but NOTs may be shared)
    # Actually k only takes values 0..6 (never 7), so some bits are redundant.
    #
    # This is getting complex. Let me estimate:
    # For each of 8 output bits, the three "decode" operations cost ~5 gates each,
    # plus 2-3 AND/OR to combine = ~8 gates per bit = 64 gates total for output stage.
    # But with sharing of k decoder: k decoder produces 7 signals (k==0..k==6),
    # each costing ~3-4 gates, but with sharing of NOT(k_i) signals.
    # Rough estimate: k decoder = 20 gates, output combination = 3-4 per bit = 24-32 more.
    # NOT(any_zero) = 1 gate, AND with it for each bit = 8 gates.
    # Total output stage: ~55 gates (rough estimate)

    # 6. Conditional negation
    # = 3*8 - 1 = 23 gates
    gates['cond_neg'] = 23

    print("Structural gate estimate (canonical encoding):")
    total = 0
    for name, cost in gates.items():
        print(f"  {name}: {cost}")
        total += cost
    print(f"  Output computation (rough): ~55 gates")
    total += 55
    print(f"  TOTAL (rough estimate): ~{total} gates")
    return total


estimate_canonical_gates()

# ─── Can we do better? Lower bound analysis ─────────────────────────────────

print("\n=== Lower bound analysis ===")
print("""
Lower bounds on gate count:

1. Sign bit: MUST be XOR(a0,b0) = 1 gate (minimum for XOR of 2 bits)

2. The magnitude circuit has at least:
   - The product has 19 distinct non-negative values
   - log2(19) ≈ 4.2 bits needed to distinguish them
   - But we output 8 bits, not encode the value compactly

3. Information-theoretic lower bound for 6-input → 8-output function:
   - Each gate computes one boolean function of 2 inputs
   - Shannon bound: ~64/log2(4) = 32 gates just for the magnitude
   - But this is very loose

4. Zero case: to zero out 8 output bits when any input is 0,
   we need at least 8 AND gates (one per output bit)
   OR a clever circuit where zero naturally propagates.

5. The conditional negation adds at least ~8 gates (at minimum 1 per bit).

Practical lower bound estimate: ~20-30 gates minimum for a correct circuit.
The question is whether clever structure allows fewer.
""")

# ─── Key optimization: avoid conditional negation ───────────────────────────

print("=== Strategy: Direct two's complement computation ===")
print("""
Instead of:
  1. Compute unsigned magnitude M (8 bits)
  2. Apply conditional negation (23 gates)

We can directly compute the two's complement output for each bit.

For the negative values, their two's complement = 512 - |value|.
For each output bit, the truth table directly gives us the function.

With a good remapping, the 8-input functions for bits 1..8 might have
short representations that ALREADY encode the sign inversion.

Key observation: for bit i:
  pos_val: depends only on magnitude bits (a1..a3, b1..b3)
  neg_val: is NOT(pos_val_bit) XOR carry_stuff

But actually: looking at the bit patterns:
  +1 = 000000001, -1 = 111111111  → every bit is flipped + carry
  +2 = 000000010, -2 = 111111110  → flipped + carry gives 110
  etc.

The carry pattern for negation: for the value 'val':
  -val = ~val + 1
  The "+1" only changes bits from the rightmost 1 bit.

For ALL our output values, they are multiples of 2 or have the rightmost 1
at a specific position. This determines where the carry terminates.

For example: val = 1 = 000000001 → -val = 111111111
             val = 2 = 000000010 → -val = 111111110
             val = 3 = 000000011 → -val = 111111101
             val = 4 = 000000100 → -val = 111111100

In general: -val = invert all bits above LSB-1, LSB stays.
But this is exactly what two's complement does.

The insight is: for direct computation, res_bit_i is a function of ALL 8 inputs,
and with the right structure, this might be cheaper than 2-stage synthesis.
""")

# Check: what are the "difficult" bits?
print("\n=== Bit-by-bit analysis for default encoding ===")
# For default encoding, compute the truth table
default_tt = build_truth_table(tuple(range(8)))
funcs = tt_to_bit_functions(default_tt)

for bit_i in range(9):
    f = funcs[bit_i]
    ones = sum(f)
    zeros = 256 - ones
    # Count how many DISTINCT inputs matter
    relevant = 0
    for inp_bit in range(8):
        for idx in range(256):
            if f[idx] != f[idx ^ (1 << inp_bit)]:
                relevant += 1
                break
    print(f"  res{bit_i}: {ones} ones, {zeros} zeros, {relevant} relevant inputs")
