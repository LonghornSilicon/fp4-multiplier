"""
Log-domain approach analysis for FP4xFP4 -> QI9 multiplication.

Key insight: FP4 magnitudes are all 1.5^M x 2^E where M in {0,1}, E in {-1,0,1,2}.
In log domain, multiplication becomes addition:
  log2(a x b) = log2(a) + log2(b)

The question: Can we encode each FP4 magnitude as a fixed-point log value,
add them, then decode to QI9 output with fewer than 82 gates total?

Run: python experiments/exp_log_domain.py
"""

import math
import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from eval_circuit import FP4_TABLE

# =============================================================================
# Part 1: Mathematical Analysis
# =============================================================================

def analyze_log_structure():
    """Analyze the log2 values of all FP4 magnitudes and products."""
    print("="*70)
    print("PART 1: LOG-DOMAIN MATHEMATICAL ANALYSIS")
    print("="*70)

    # Non-zero FP4 magnitudes
    magnitudes = [0.5, 1.0, 1.5, 2.0, 3.0, 4.0, 6.0]

    print("\n--- FP4 Magnitude Log2 Values ---")
    for m in magnitudes:
        log_val = math.log2(m)
        print(f"  {m:4.1f}  ->  log2 = {log_val:+.6f}")

    # Key observation: log2(1.5) = 0.5849625... is irrational
    log_1_5 = math.log2(1.5)
    print(f"\nlog2(1.5) = {log_1_5:.10f} (irrational!)")

    # All products and their log2 values
    print("\n--- All Non-Zero Products and Log2 Values ---")
    products = set()
    log_products = {}
    for a in magnitudes:
        for b in magnitudes:
            p = a * b
            products.add(p)
            log_products[p] = math.log2(p)

    for p in sorted(products):
        qi9_mag = int(round(p * 4))  # The actual output we need
        print(f"  {p:5.2f} (QI9: {qi9_mag:3d})  ->  log2 = {log_products[p]:+.6f}")

    print(f"\nTotal distinct products: {len(products)}")

    return magnitudes, log_products


def analyze_fixed_point_precision():
    """Determine minimum fixed-point precision needed to distinguish products."""
    print("\n" + "="*70)
    print("PART 2: FIXED-POINT PRECISION REQUIREMENTS")
    print("="*70)

    magnitudes = [0.5, 1.0, 1.5, 2.0, 3.0, 4.0, 6.0]
    products = {}
    for a in magnitudes:
        for b in magnitudes:
            p = a * b
            products[p] = math.log2(p)

    sorted_prods = sorted(products.keys())

    # Find minimum gap between log values
    min_gap = float('inf')
    min_pair = None
    for i in range(len(sorted_prods) - 1):
        p1, p2 = sorted_prods[i], sorted_prods[i+1]
        gap = abs(products[p2] - products[p1])
        if gap < min_gap:
            min_gap = gap
            min_pair = (p1, p2)

    print(f"\nMinimum log2 gap: {min_gap:.10f}")
    print(f"  Between: {min_pair[0]} and {min_pair[1]}")
    print(f"  log2({min_pair[0]}) = {products[min_pair[0]]:.10f}")
    print(f"  log2({min_pair[1]}) = {products[min_pair[1]]:.10f}")

    # What fractional bits do we need?
    bits_needed = math.ceil(-math.log2(min_gap))
    print(f"\nFractional bits needed: ~{bits_needed}")

    # But wait - this is for distinguishing arbitrary log values.
    # Let's check: do any two products with DIFFERENT QI9 outputs have the same log?
    print("\n--- QI9 Output Collision Check ---")
    qi9_map = {}
    for p in sorted_prods:
        qi9 = int(round(p * 4))
        if qi9 not in qi9_map:
            qi9_map[qi9] = []
        qi9_map[qi9].append(p)

    collisions = [(k, v) for k, v in qi9_map.items() if len(v) > 1]
    if collisions:
        print(f"WARNING: {len(collisions)} QI9 values have multiple product sources!")
        for qi9, prods in collisions:
            print(f"  QI9={qi9}: products {prods}")
    else:
        print("No collisions - each product maps to unique QI9")

    return products


def analyze_decomposition():
    """
    The key insight: log2(mag) = M * log2(1.5) + E * log2(2) = M * 0.585 + E

    Since log2(2) = 1 exactly, the integer part is just E.
    The fractional part depends only on M:
      M=0: frac = 0
      M=1: frac = log2(1.5) = 0.5849625...

    For products:
      log2(a*b) = (Ma+Mb)*log2(1.5) + (Ea+Eb)

    M_sum in {0, 1, 2}, so:
      M_sum=0: frac = 0
      M_sum=1: frac = 0.5849625
      M_sum=2: frac = 1.1699250 = 1 + 0.1699250
    """
    print("\n" + "="*70)
    print("PART 3: DECOMPOSITION ANALYSIS (Ma+Mb, Ea+Eb)")
    print("="*70)

    log_1_5 = math.log2(1.5)  # ~0.585

    # Magnitude -> (M, E) mapping
    mag_to_ME = {
        0.5: (0, -1),
        1.0: (0, 0),
        1.5: (1, 0),
        2.0: (0, 1),
        3.0: (1, 1),
        4.0: (0, 2),
        6.0: (1, 2),
    }

    print("\n--- Magnitude Decomposition ---")
    for mag, (M, E) in sorted(mag_to_ME.items()):
        log_val = M * log_1_5 + E
        actual = math.log2(mag)
        print(f"  {mag:4.1f} = 1.5^{M} * 2^{E:+d}  =>  log2 = {M}*0.585 + {E} = {log_val:.4f} (actual: {actual:.4f})")

    print("\n--- Product Decomposition ---")
    print("  M_sum  E_sum  | K-factor   | log2(K)    | Products")
    print("  " + "-"*60)

    # K-factor: 1.5^M_sum
    # K=1 when M_sum=0, K=1.5 when M_sum=1, K=2.25 when M_sum=2
    for M_sum in [0, 1, 2]:
        K = 1.5 ** M_sum
        log_K = M_sum * log_1_5
        print(f"  {M_sum:5d}  any    | {K:10.4f} | {log_K:+10.6f} | (shift by E_sum)")

    print("\n--- This is EXACTLY what the current circuit does! ---")
    print("  M_sum=0: K=1.00 (nmc)  -> product = 1 * 2^E_sum")
    print("  M_sum=1: K=1.50 (k3)   -> product = 3/2 * 2^E_sum = 3 * 2^(E_sum-1)")
    print("  M_sum=2: K=2.25 (k9)   -> product = 9/4 * 2^E_sum = 9 * 2^(E_sum-2)")


def analyze_log_encoding_options():
    """
    Explore concrete log encodings and gate costs.
    """
    print("\n" + "="*70)
    print("PART 4: LOG ENCODING OPTIONS")
    print("="*70)

    log_1_5 = math.log2(1.5)  # 0.5849625...

    # Option A: Separate M and E representation (current approach)
    print("\n--- Option A: Factored (M, E) representation (CURRENT) ---")
    print("  Input: 3-bit magnitude code -> (M, E) extraction")
    print("  M is bit 0 (a1), E is encoded in bits 1-2 (a2, a3)")
    print("  Product: M_sum = M_a + M_b (2 bits), E_sum = E_a + E_b (3 bits)")
    print("  This IS a log encoding! Just represented in factored form.")
    print("  Cost: 7 (E-adder) + 6 (K-flags) = 13 gates for 'addition'")

    # Option B: Direct fixed-point log
    print("\n--- Option B: Direct fixed-point log representation ---")

    # We need log2 range from -1 (0.5) to 2.585 (6.0)
    # With 3 fractional bits, we can represent multiples of 0.125
    # With 4 fractional bits, multiples of 0.0625

    for frac_bits in [3, 4, 5]:
        print(f"\n  {frac_bits} fractional bits (LSB = 1/{2**frac_bits}):")
        scale = 2 ** frac_bits

        magnitudes = [0.5, 1.0, 1.5, 2.0, 3.0, 4.0, 6.0]
        encodings = {}
        for m in magnitudes:
            log_val = math.log2(m)
            # Need to handle negative logs (0.5 -> -1)
            # Use signed representation
            encoded = round(log_val * scale)
            encodings[m] = encoded
            print(f"    {m:4.1f}: log2={log_val:+.4f} -> encoded={encoded:+4d} (binary: {encoded & ((1<<(3+frac_bits))-1):0{3+frac_bits}b})")

        # Check for collisions
        unique_codes = set(encodings.values())
        if len(unique_codes) < len(encodings):
            print(f"    WARNING: Collisions detected!")

    # The problem: log2(1.5) is irrational, so no finite precision is exact
    print("\n--- The Fundamental Problem ---")
    print("  log2(1.5) = 0.5849625007211561... is IRRATIONAL")
    print("  Any fixed-point encoding is approximate.")
    print("  But the QI9 output only has 18 distinct magnitudes, so")
    print("  we just need enough precision to not confuse them.")


def analyze_direct_product_encoding():
    """
    Key insight: we don't need to store actual log values.
    We need an encoding where ADD gives us enough info to decode QI9.

    Currently: (M, E') encoding where M in {0,1}, E' in {0,1,2,3}
    Product: M_sum in {0,1,2}, E_sum in {0,...,6}

    This is a 2x7 = 14-entry table.
    But there are only 18 distinct output magnitudes.
    """
    print("\n" + "="*70)
    print("PART 5: DIRECT PRODUCT ENCODING ANALYSIS")
    print("="*70)

    # Current encoding (from multiplier.py)
    mag_to_code = {
        0.0: 0b000, 1.5: 0b001, 3.0: 0b010, 6.0: 0b011,
        0.5: 0b100, 1.0: 0b101, 2.0: 0b110, 4.0: 0b111,
    }

    # Extract M and E' from code
    def extract_ME(code):
        if code == 0:
            return (None, None)  # zero
        # From the encoding:
        # code bit 2 (MSB): 0 = M=1 (1.5x family), 1 = M=0 (power-of-2 family)
        # code bits 1-0: E' = E + 1
        M = 0 if (code >> 2) & 1 else 1
        E_prime = code & 0b011
        return (M, E_prime)

    print("\n--- Current Code -> (M, E') Extraction ---")
    for mag in [0.5, 1.0, 1.5, 2.0, 3.0, 4.0, 6.0]:
        code = mag_to_code[mag]
        M, E_prime = extract_ME(code)
        print(f"  {mag:4.1f}: code={code:03b} -> M={M}, E'={E_prime}")

    # Alternative: what if we encode log2 * some scale?
    print("\n--- Alternative Encoding: log2(mag) * scale ---")
    print("  The goal: find a scale where SUM of encodings directly indexes output")

    # For this to work, we need:
    # encode(a) + encode(b) = unique index for each distinct product

    magnitudes = [0.5, 1.0, 1.5, 2.0, 3.0, 4.0, 6.0]
    products = set()
    for a in magnitudes:
        for b in magnitudes:
            products.add(a * b)

    print(f"\n  7 magnitudes, 49 products, {len(products)} distinct values")
    print(f"  Product range: {min(products)} to {max(products)}")
    print(f"  QI9 magnitude range: {int(min(products)*4)} to {int(max(products)*4)}")

    # Try various scales
    print("\n  Testing scales where sum gives unique product index:")
    for scale in [1, 2, 3, 4, 5, 6, 7, 8, 10, 12, 16]:
        encodings = {m: round(math.log2(m) * scale) for m in magnitudes}
        sums = {}
        collision = False
        for a in magnitudes:
            for b in magnitudes:
                s = encodings[a] + encodings[b]
                p = a * b
                if s in sums and sums[s] != p:
                    collision = True
                    break
                sums[s] = p
            if collision:
                break

        if not collision:
            # Check encoding range
            enc_min = min(encodings.values())
            enc_max = max(encodings.values())
            sum_min = 2 * enc_min
            sum_max = 2 * enc_max
            bits_needed = max(abs(sum_min), abs(sum_max)).bit_length() + 1  # +1 for sign
            print(f"    scale={scale:2d}: works! enc_range=[{enc_min},{enc_max}], sum_range=[{sum_min},{sum_max}], ~{bits_needed} bits")


def analyze_gate_costs():
    """
    Concrete gate cost comparison.
    """
    print("\n" + "="*70)
    print("PART 6: GATE COST ANALYSIS")
    print("="*70)

    print("\n--- Current Circuit Breakdown (82 gates) ---")
    current = {
        "sign XOR": 1,
        "nz detection (5 gates)": 5,
        "E-sum (2-bit adder)": 7,
        "K-flags (OR, NOT, XOR)": 3,
        "K-masking (3 ANDs)": 3,
        "S-decoder (one-hot from E-sum)": 11,
        "AND-terms (18 K x sh)": 18,
        "Mag OR assembly": 15,
        "Conditional negation": 18,
        "Sign mask (AND)": 1,
    }
    for k, v in current.items():
        print(f"    {k}: {v}")
    print(f"    TOTAL: {sum(current.values())}")

    print("\n--- Log-Domain Alternative ---")
    print("  The fundamental challenge: we need to DECODE the log-sum back to QI9")

    print("\n  Option 1: Direct fixed-point log encoding")
    print("    Encode: 3-bit code -> ~5-bit fixed-point log2 value")
    print("    Cost: This is a 3->5 decoder, ~8-10 gates per operand x 2")
    print("    Add: 5-bit adder, ~12-15 gates")
    print("    Decode: 6-bit sum -> 8-bit magnitude + sign bit")
    print("           This is a ~40+ gate ROM/decoder")
    print("    Estimated: 16 + 15 + 40 = 71 gates (BEFORE sign handling)")
    print("    BUT: still need conditional negation (~18 gates)")
    print("    Total estimate: ~90+ gates -- WORSE than current")

    print("\n  Option 2: Keep (M, E) factored representation")
    print("    This IS the current approach!")
    print("    M_sum encodes the 'fractional log part'")
    print("    E_sum encodes the 'integer log part' (shift)")
    print("    The S-decoder is the 'decode log back to position' step")

    print("\n--- Why Log-Domain Doesn't Help Here ---")
    print("  1. The current circuit IS a log-domain approach (factored form)")
    print("  2. The factored (M, E) representation is more efficient than")
    print("     direct fixed-point because:")
    print("     - M and E are computed separately (no irrational arithmetic)")
    print("     - K-flags directly select magnitude pattern (no decoder)")
    print("     - E-sum directly indexes bit positions (no anti-log)")
    print("  3. Any pure fixed-point log approach needs:")
    print("     - Encode: ~16 gates (2x 3->5 bit transform)")
    print("     - Add: ~15 gates (5-bit signed add)")
    print("     - Decode: ~40 gates (6-bit -> 8-bit magnitude lookup)")
    print("     - Conditional neg: ~18 gates")
    print("     Total: ~89 gates minimum")


def analyze_antilog_decoder():
    """
    Analyze what the anti-log decoder would need to produce.
    """
    print("\n" + "="*70)
    print("PART 7: ANTILOG DECODER REQUIREMENTS")
    print("="*70)

    magnitudes = [0.5, 1.0, 1.5, 2.0, 3.0, 4.0, 6.0]

    # All possible sums of log2 values
    products_info = []
    for a in magnitudes:
        for b in magnitudes:
            p = a * b
            log_sum = math.log2(a) + math.log2(b)
            qi9 = int(round(p * 4))
            products_info.append((log_sum, p, qi9))

    # Sort by log_sum
    products_info.sort()

    print("\n--- Log-Sum to QI9 Mapping (sorted by log_sum) ---")
    seen_qi9 = set()
    distinct_info = []
    for log_sum, p, qi9 in products_info:
        if qi9 not in seen_qi9:
            seen_qi9.add(qi9)
            distinct_info.append((log_sum, p, qi9))

    print(f"  {'log_sum':>10s}  {'product':>8s}  {'QI9':>5s}  {'binary':>10s}")
    print("  " + "-"*40)
    for log_sum, p, qi9 in distinct_info:
        print(f"  {log_sum:+10.6f}  {p:8.4f}  {qi9:5d}  {qi9:08b}")

    print(f"\n  {len(distinct_info)} distinct output magnitudes")
    print(f"  Decoder needs: 6-bit input (log_sum range) -> 8-bit magnitude")
    print(f"  This is a large ROM/PLA: ~40 gates minimum")

    # Compare with current S-decoder
    print("\n--- Current S-decoder (11 gates) ---")
    print("  S (E-sum) ranges 0..6 -> 7 one-hot outputs")
    print("  Each output enables a specific bit position")
    print("  K-type (3 values) determines which positions to OR together")
    print("  Total: 11 (decoder) + 18 (AND terms) + 15 (OR assembly) = 44 gates")

    print("\n--- The Equivalence ---")
    print("  S-decoder + K-type gating IS the anti-log decoder, just factored!")
    print("  Current: (K-type, S) -> 8-bit magnitude uses 44 gates")
    print("  Direct: log_sum -> 8-bit magnitude would need ~40-50 gates")
    print("  No savings possible here.")


def main():
    analyze_log_structure()
    analyze_fixed_point_precision()
    analyze_decomposition()
    analyze_log_encoding_options()
    analyze_direct_product_encoding()
    analyze_gate_costs()
    analyze_antilog_decoder()

    print("\n" + "="*70)
    print("CONCLUSION")
    print("="*70)
    print("""
The current 82-gate circuit already implements a log-domain approach:
  - M (mantissa type) encodes the fractional part of log2(magnitude)
  - E' (shifted exponent) encodes the integer part of log2(magnitude)
  - K-flags (k9, k3, nmc) are 3-way one-hot encoding of M_sum
  - S-decoder produces one-hot encoding of E_sum

Converting to an explicit fixed-point log representation would INCREASE
gate count because:

1. ENCODING cost: 3-bit code -> fixed-point log
   Current: FREE (M and E' already extracted from bit positions)
   Log: ~8-10 gates per operand to compute log2 approximation

2. ADDITION cost: sum of logs
   Current: 7-gate 2-bit adder for E', 3-gate K-flag computation
   Log: ~12-15 gate 5-bit signed adder

3. DECODING cost: log-sum back to magnitude bits
   Current: 11 (S-decoder) + 33 (K-gated AND/OR assembly) = 44 gates
   Log: ~40-50 gates for 6-bit -> 8-bit decoder

The factored (M, E) representation is superior because:
  - No irrational arithmetic (log2(1.5) = 0.585... never computed)
  - Natural bit-position alignment (shifts are position selection)
  - K-type gating is cheaper than full decoder (3 cases, not 18)

VERDICT: Log-domain approach does NOT offer gate savings.
The current architecture is already optimal for this decomposition.
    """)


def prototype_log_domain_circuit():
    """
    Prototype a concrete log-domain circuit to verify gate counts.

    Using scale=3 (the minimum that works):
      0.5 -> log2=-1.00 -> enc=-3
      1.0 -> log2= 0.00 -> enc= 0
      1.5 -> log2= 0.58 -> enc= 2 (rounded from 1.75)
      2.0 -> log2= 1.00 -> enc= 3
      3.0 -> log2= 1.58 -> enc= 5 (rounded from 4.75)
      4.0 -> log2= 2.00 -> enc= 6
      6.0 -> log2= 2.58 -> enc= 8 (rounded from 7.75)

    Sum range: -6 to +16 (needs 5-bit signed)
    """
    print("\n" + "="*70)
    print("PART 8: CONCRETE LOG-DOMAIN PROTOTYPE")
    print("="*70)

    # Step 1: Encoder 3-bit magnitude code -> 4-bit signed log
    # Current magnitude encoding:
    #   000 -> 0 (zero)
    #   001 -> 1.5 -> log_enc=2
    #   010 -> 3.0 -> log_enc=5
    #   011 -> 6.0 -> log_enc=8
    #   100 -> 0.5 -> log_enc=-3
    #   101 -> 1.0 -> log_enc=0
    #   110 -> 2.0 -> log_enc=3
    #   111 -> 4.0 -> log_enc=6

    print("\n--- Step 1: Encoder Truth Table ---")
    print("  code  mag   log2    enc(scale=3)")
    print("  " + "-"*35)
    encodings = {
        0b000: None,  # zero
        0b001: 2,   # 1.5
        0b010: 5,   # 3.0
        0b011: 8,   # 6.0
        0b100: -3,  # 0.5
        0b101: 0,   # 1.0
        0b110: 3,   # 2.0
        0b111: 6,   # 4.0
    }
    mag_vals = {0b000: 0, 0b001: 1.5, 0b010: 3.0, 0b011: 6.0,
                0b100: 0.5, 0b101: 1.0, 0b110: 2.0, 0b111: 4.0}
    for code in range(8):
        mag = mag_vals[code]
        enc = encodings[code]
        log_val = math.log2(mag) if mag > 0 else float('-inf')
        enc_str = f"{enc:+3d}" if enc is not None else " --"
        print(f"  {code:03b}  {mag:4.1f}  {log_val:+6.3f}  {enc_str}")

    # Encoder analysis:
    # enc_bit3 (sign): 1 only for code=100 (0.5)
    # enc_bit2: 1 for codes 011,100,101,110,111 (enc>=4 or enc<0)
    #           Actually: 1 for 011(8), 010(5), 111(6), 100(-3)
    # This is getting complex...

    print("\n--- Encoder Gate Analysis ---")
    print("  The encoder maps 3-bit code to ~5-bit signed value.")
    print("  Looking at the bit patterns:")
    for i in range(5):
        print(f"\n  enc_bit{i} (value {2**i if i<4 else 'sign'}):")
        for code in range(8):
            enc = encodings[code]
            if enc is None:
                bit = '-'
            else:
                # Two's complement for negative
                enc_tc = enc if enc >= 0 else (enc + 16)
                bit = (enc_tc >> i) & 1
            print(f"    code={code:03b} -> bit{i}={bit}")

    print("\n  Encoder cost estimate:")
    print("    Need to implement 5 output functions of 3 input bits")
    print("    This is similar to the S-decoder (7-output from 3-bit)")
    print("    Estimate: ~8-12 gates per operand")

    # Step 2: Addition (5-bit signed)
    print("\n--- Step 2: Log Sum Adder ---")
    print("  Sum of two ~5-bit signed values -> 6-bit signed result")
    print("  5-bit ripple-carry adder: ~10 gates (2 per bit)")
    print("  But we have redundancy since we know the input distribution")
    print("  Optimistic estimate: ~8 gates")

    # Step 3: Decoder (6-bit log_sum -> 8-bit magnitude)
    print("\n--- Step 3: Antilog Decoder ---")

    # Build the truth table
    magnitudes = [0.5, 1.0, 1.5, 2.0, 3.0, 4.0, 6.0]
    enc_from_mag = {0.5: -3, 1.0: 0, 1.5: 2, 2.0: 3, 3.0: 5, 4.0: 6, 6.0: 8}

    sum_to_qi9 = {}
    for a in magnitudes:
        for b in magnitudes:
            s = enc_from_mag[a] + enc_from_mag[b]
            qi9 = int(round(a * b * 4))
            if s in sum_to_qi9:
                assert sum_to_qi9[s] == qi9, f"Collision at sum={s}!"
            sum_to_qi9[s] = qi9

    print("  log_sum -> QI9 magnitude truth table:")
    for s in sorted(sum_to_qi9.keys()):
        qi9 = sum_to_qi9[s]
        print(f"    sum={s:+3d} -> QI9={qi9:3d} ({qi9:08b})")

    print(f"\n  {len(sum_to_qi9)} entries in decoder")
    print("  Sum range: -6 to +16 (23 values, only 18 used)")
    print("  Output: 8-bit magnitude")
    print("  This is an 18-entry ROM: 5-input, 8-output")
    print("  Minimal AND-OR PLA estimate: ~30-40 gates")

    # Compare with current factored approach
    print("\n--- Comparison with Current (M,E) Factored Approach ---")
    print("  Current factored approach:")
    print("    E-sum (2-bit adder): 7 gates")
    print("    K-flags (M handling): 6 gates")
    print("    S-decoder: 11 gates")
    print("    K x S gating: 18 gates")
    print("    Mag OR assembly: 15 gates")
    print("    Subtotal (mag computation): 57 gates")
    print()
    print("  Log-domain approach:")
    print("    Encoder (2x): ~16-24 gates")
    print("    Log adder: ~8-10 gates")
    print("    Antilog decoder: ~30-40 gates")
    print("    Subtotal (mag computation): ~54-74 gates")
    print()
    print("  The log-domain approach is NOT clearly better, and likely worse")
    print("  due to the large antilog decoder requirements.")


def synthesize_log_decoder_with_abc():
    """
    Actually synthesize the antilog decoder with ABC to get real gate count.
    """
    print("\n" + "="*70)
    print("PART 9: ABC SYNTHESIS OF ANTILOG DECODER")
    print("="*70)

    import subprocess
    import shutil

    ABC_BIN = "/home/tit/abc/abc"
    ABC_CWD = "/home/tit/abc"

    if not os.path.exists(ABC_BIN):
        print("  ABC not available, skipping synthesis")
        return

    # Build PLA for antilog decoder
    magnitudes = [0.5, 1.0, 1.5, 2.0, 3.0, 4.0, 6.0]
    enc_from_mag = {0.5: -3, 1.0: 0, 1.5: 2, 2.0: 3, 3.0: 5, 4.0: 6, 6.0: 8}

    sum_to_qi9 = {}
    for a in magnitudes:
        for b in magnitudes:
            s = enc_from_mag[a] + enc_from_mag[b]
            qi9 = int(round(a * b * 4))
            sum_to_qi9[s] = qi9

    # Write PLA file
    pla_path = "/tmp/antilog_decoder.pla"
    with open(pla_path, "w") as f:
        f.write(".i 5\n")  # 5-bit signed input (sum range -6 to +16)
        f.write(".o 8\n")  # 8-bit magnitude output
        f.write(".ilb s4 s3 s2 s1 s0\n")  # MSB is sign
        f.write(".ob m7 m6 m5 m4 m3 m2 m1 m0\n")
        f.write(".type fr\n")

        entries = []
        for s, qi9 in sorted(sum_to_qi9.items()):
            # Convert sum to 5-bit two's complement
            s_tc = s if s >= 0 else (s + 32)
            in_bits = f"{s_tc:05b}"
            out_bits = f"{qi9:08b}"
            entries.append(f"{in_bits} {out_bits}")

        f.write(f".p {len(entries)}\n")
        for entry in entries:
            f.write(entry + "\n")
        f.write(".e\n")

    print(f"  Wrote PLA: {pla_path}")
    print(f"  {len(sum_to_qi9)} entries")

    # Run ABC
    script = (
        f"read_pla {pla_path}; strash; print_stats; "
        "compress2rs; compress2rs; compress2rs; compress2rs; "
        "dch; resyn2; resyn2rs; "
        "compress2rs; compress2rs; "
        "&get; &deepsyn -T 30; &put; "
        "print_stats"
    )

    try:
        proc = subprocess.run(
            [ABC_BIN, "-c", script],
            cwd=ABC_CWD,
            capture_output=True, text=True, timeout=60,
        )
        output = proc.stdout + proc.stderr

        # Extract final gate count
        import re
        ands = [int(m.group(1)) for m in re.finditer(r"and\s*=\s*(\d+)", output)]
        if ands:
            print(f"  ABC synthesis result: {min(ands)} AND gates")
        else:
            print("  Could not parse ABC output")
            print(output[-1000:])

    except Exception as e:
        print(f"  ABC synthesis failed: {e}")


def synthesize_full_log_circuit():
    """
    Synthesize the full log-domain circuit:
    1. Two encoders (3-bit -> 5-bit each)
    2. Adder (5-bit + 5-bit -> 6-bit)
    3. Antilog decoder (6-bit -> 8-bit)
    """
    print("\n" + "="*70)
    print("PART 10: FULL LOG-DOMAIN CIRCUIT SYNTHESIS")
    print("="*70)

    import subprocess

    ABC_BIN = "/home/tit/abc/abc"
    ABC_CWD = "/home/tit/abc"

    if not os.path.exists(ABC_BIN):
        print("  ABC not available, skipping synthesis")
        return

    # Build full truth table: 6-bit input (a2,a1,a0,b2,b1,b0) -> 8-bit output
    # This is the magnitude part only (no sign handling)

    mag_vals = {0b000: 0, 0b001: 1.5, 0b010: 3.0, 0b011: 6.0,
                0b100: 0.5, 0b101: 1.0, 0b110: 2.0, 0b111: 4.0}

    pla_path = "/tmp/log_full_mag.pla"
    with open(pla_path, "w") as f:
        f.write(".i 6\n")
        f.write(".o 8\n")
        f.write(".ilb a2 a1 a0 b2 b1 b0\n")
        f.write(".ob m7 m6 m5 m4 m3 m2 m1 m0\n")
        f.write(".type fr\n")

        entries = []
        for a_code in range(8):
            for b_code in range(8):
                a_mag = mag_vals[a_code]
                b_mag = mag_vals[b_code]

                if a_mag == 0 or b_mag == 0:
                    qi9 = 0
                else:
                    qi9 = int(round(a_mag * b_mag * 4))

                in_bits = f"{a_code:03b}{b_code:03b}"
                out_bits = f"{qi9:08b}"
                entries.append(f"{in_bits} {out_bits}")

        f.write(f".p {len(entries)}\n")
        for entry in entries:
            f.write(entry + "\n")
        f.write(".e\n")

    print(f"  Wrote full magnitude PLA: {pla_path}")
    print(f"  64 entries (8x8 input combinations)")

    # Run ABC with aggressive optimization
    script = (
        f"read_pla {pla_path}; strash; print_stats; "
        "compress2rs; compress2rs; compress2rs; compress2rs; "
        "dch; resyn2; resyn2rs; "
        "compress2rs; compress2rs; compress2rs; "
        "&get; &deepsyn -T 60; &put; "
        "compress2rs; resyn2; "
        "print_stats"
    )

    try:
        proc = subprocess.run(
            [ABC_BIN, "-c", script],
            cwd=ABC_CWD,
            capture_output=True, text=True, timeout=120,
        )
        output = proc.stdout + proc.stderr

        import re
        ands = [int(m.group(1)) for m in re.finditer(r"and\s*=\s*(\d+)", output)]
        if ands:
            best_and = min(ands)
            print(f"  ABC result for 6-bit -> 8-bit magnitude: {best_and} AND gates")
        else:
            print("  Could not parse ABC output")
            print(output[-1000:])

    except Exception as e:
        print(f"  ABC synthesis failed: {e}")

    # Compare with current factored implementation
    print("\n--- Comparison ---")
    print("  Current factored approach (magnitude only):")
    print("    E-sum adder: 7 gates")
    print("    K-flags + masking: 6 gates")
    print("    S-decoder: 11 gates")
    print("    K x S gating: 18 gates")
    print("    Mag OR assembly: 15 gates")
    print("    Total: 57 gates")
    print()
    print("  Any monolithic 6-bit -> 8-bit synthesis is competing against")
    print("  a hand-designed factored approach that exploits structure.")
    print()
    print("  The log-domain insight was correct but the current circuit")
    print("  ALREADY exploits it via the factored (M, E) representation!")


if __name__ == "__main__":
    main()
    prototype_log_domain_circuit()
    synthesize_log_decoder_with_abc()
    synthesize_full_log_circuit()
