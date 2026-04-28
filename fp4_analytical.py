"""
Analytical approach to FP4 multiplier circuit design.

Key insight:
  All non-zero FP4 magnitudes are of the form 1.5^M * 2^E where:
    M (mantissa bit) in {0, 1}  →  factor 1 or 1.5
    E (exponent) in {-1, 0, 1, 2}

  Product×4 = 4 * (1.5^Ma * 2^Ea) * (1.5^Mb * 2^Eb)
             = (1.5^(Ma+Mb)) * 2^(Ea+Eb+2)

  Where Ma+Mb in {0,1,2} determines the "type":
    0 → 1×  (binary pattern: ...0001...)
    1 → 3×  (binary pattern: ...0011... shifted)
    2 → 9×  (binary pattern: ...1001... shifted)

  The shift k = Ea+Eb+2 determines WHERE in the 9-bit output.

This script:
  1. Derives the exact boolean functions for the circuit
  2. Tries to minimize gate count analytically
  3. Tests multiple remappings with structure-aware analysis
"""

from fp4_core import (
    FP4_VALUES, MAGNITUDES, build_truth_table,
    tt_to_bit_functions, score_tt, score_tt_detailed
)

# ─── Magnitude decomposition ────────────────────────────────────────────────

def decompose_magnitude(mag: float):
    """Return (E, M) where mag = 1.5^M * 2^E. Returns None for zero."""
    if mag == 0:
        return None
    for E in range(-1, 3):
        for M in range(2):
            if abs(mag - (1.5 ** M) * (2 ** E)) < 1e-9:
                return (E, M)
    raise ValueError(f"Cannot decompose {mag}")


# Decompose all magnitudes
print("Magnitude decompositions (E, M):")
for m in MAGNITUDES:
    d = decompose_magnitude(m)
    print(f"  {m:4.1f} -> {d}")


def build_multiplication_table():
    """
    Build table of all non-zero magnitude products * 4.
    Returns: {(mag_a, mag_b): product_qi9} for non-zero inputs.
    """
    table = {}
    for a in MAGNITUDES[1:]:  # skip 0
        for b in MAGNITUDES[1:]:
            ea, ma = decompose_magnitude(a)
            eb, mb = decompose_magnitude(b)
            k = ea + eb + 2  # shift
            t = ma + mb       # type: 0,1,2
            # output value = {1,3,9}[t] * 2^k
            base = [1, 3, 9][t]
            val = base * (2 ** k)
            table[(a, b)] = val
    return table


# ─── Remapping design strategies ────────────────────────────────────────────

def encoding_to_bits(perm):
    """Show human-readable encoding table."""
    print("Magnitude encoding:")
    for i, mag in enumerate(MAGNITUDES):
        bits = perm[i]
        print(f"  {mag:4.1f} -> {bits:03b} ({bits})")


def try_structured_remappings():
    """
    Try specific structured remappings based on mathematical insight.
    Returns list of (score, perm, description).
    """
    candidates = []

    # ── Strategy 1: Default FP4 encoding ──
    # 0→000, 0.5→001, 1→010, 1.5→011, 2→100, 3→101, 4→110, 6→111
    perm = (0, 1, 2, 3, 4, 5, 6, 7)
    tt = build_truth_table(perm)
    candidates.append((score_tt(tt), perm, "Default FP4"))

    # ── Strategy 2: Zero at 0b111, 0.5 at 0b000 ──
    # Keep M bit = a3, exponent in (a1, a2)
    # 0→111, 0.5→000, 1→001, 1.5→101, 2→010, 3→110, 4→011, 6→111
    # Problem: zero at same code as 6 in this scheme. Let me pick differently.
    # 0→110, 0.5→000, 1→001, 1.5→101, 2→010, 3→011, 4→100, 6→111
    # Indices: [0,0.5,1,1.5,2,3,4,6] -> [110,000,001,101,010,011,100,111]
    perm = (0b110, 0b000, 0b001, 0b101, 0b010, 0b011, 0b100, 0b111)
    tt = build_truth_table(perm)
    candidates.append((score_tt(tt), perm, "Zero=110, M-split"))

    # ── Strategy 3: Encode by (E+1, M) with zero at special code ──
    # E ∈ {-1,0,1,2} → E+1 ∈ {0,1,2,3} (2 bits)
    # M ∈ {0,1} (1 bit)
    # Bit layout: (M, E+1 MSB, E+1 LSB) = (a3, a2, a1) in original notation
    # But 0.5 has E=-1 so E+1=0, M=0 → 0b000
    # 0 (zero) has no (E,M) → assign to 0b110 (E+1=3 but M=0 would be 4, not valid)
    # Actually: 0b000 = (M=0,E+1=0): 0.5
    #           0b001 = (M=0,E+1=1): wait, bit order (M,E1,E0) means...
    # Let me use layout (a3=M, a2=E1, a1=E0):
    # E+1=0, M=0 → (0,0,0)=000: 0.5
    # E+1=1, M=0 → (0,0,1)=001: 1        (a3=0, a2=0, a1=1)
    # E+1=2, M=0 → (0,1,0)=010: 2
    # E+1=3, M=0 → (0,1,1)=011: 4
    # E+1=1, M=1 → (1,0,1)=101: 1.5      (SKIP E=0 only for M=1 since value would be 0.75)
    # Actually: M=1 values are 1.5,3,6 with E=0,1,2 → E+1=1,2,3
    # E+1=1, M=1 → (1,0,1)=101: 1.5
    # E+1=2, M=1 → (1,1,0)=110: 3
    # E+1=3, M=1 → (1,1,1)=111: 6
    # Zero → 0b100 (E+1=2 means E=1, M=1 would be 3, but we assign 0 here → "invalid" slot)
    #           Actually: (1,0,0)=100 = M=1,E+1=0. This is invalid as a value (0.75 not in FP4)
    # So zero goes to 0b100!
    # Magnitudes [0, 0.5, 1, 1.5, 2, 3, 4, 6]
    # Codes      [100, 000, 001, 101, 010, 110, 011, 111]
    perm = (0b100, 0b000, 0b001, 0b101, 0b010, 0b110, 0b011, 0b111)
    tt = build_truth_table(perm)
    candidates.append((score_tt(tt), perm, "E+1 biased, M=a3 (invalid slot for 0)"))

    # ── Strategy 4: Zero at 0b000 (easy zero detect = NOR all bits) ──
    # 0→000, then pack others
    # 0.5→001, 1→010, 2→100, 4→110 (pure powers of 2, no M-bit)
    # 1.5→011, 3→101, 6→111 (×1.5 values)
    perm = (0b000, 0b001, 0b010, 0b011, 0b100, 0b101, 0b110, 0b111)
    tt = build_truth_table(perm)
    candidates.append((score_tt(tt), perm, "Default (same as strategy 1)"))

    # ── Strategy 5: Logarithmic-ish encoding ──
    # Assign codes by log value: log2(val)+1 rounded
    # 0→000 (special), 0.5→1=001, 1→2=010, 1.5→3=011, 2→4=100,
    # 3→5=101, 4→6=110, 6→7=111
    perm = (0b000, 0b001, 0b010, 0b011, 0b100, 0b101, 0b110, 0b111)
    # Same as default!

    # ── Strategy 6: Put zero at 0b111, reverse order ──
    perm = (0b111, 0b110, 0b101, 0b100, 0b011, 0b010, 0b001, 0b000)
    tt = build_truth_table(perm)
    candidates.append((score_tt(tt), perm, "Reversed order, zero=111"))

    # ── Strategy 7: Group purely by M bit (half vs non-half) ──
    # M=0 values {0.5,1,2,4}: codes 000,001,010,011
    # M=1 values {1.5,3,6}:   codes 100,101,110
    # Zero: 111
    # Magnitudes [0, 0.5, 1, 1.5, 2, 3, 4, 6]
    #   codes    [111, 000, 001, 100, 010, 101, 011, 110]
    perm = (0b111, 0b000, 0b001, 0b100, 0b010, 0b101, 0b011, 0b110)
    tt = build_truth_table(perm)
    candidates.append((score_tt(tt), perm, "M-grouped, zero=111"))

    # ── Strategy 8: zero at 0b100, logical exponent ──
    # zero=100, 0.5=000, 1=001, 2=010, 4=011 (M=0, E=0..3 → codes 000,001,010,011)
    # 1.5=101, 3=110, 6=111 (M=1, E=0..2 → codes 101,110,111)
    # Magnitudes [0, 0.5, 1, 1.5, 2, 3, 4, 6]
    perm = (0b100, 0b000, 0b001, 0b101, 0b010, 0b110, 0b011, 0b111)
    tt = build_truth_table(perm)
    candidates.append((score_tt(tt), perm, "Zero=100, E as lower 2 bits"))

    # ── Strategy 9: Optimized for sign-extension ──
    # Insight: negative values are -1 to -6 times themselves.
    # If we encode such that zero gives all-zero bits in magnitude,
    # and the M bit is the LSB (a3 in original), we can XOR out the sign easily.
    # zero=000, 0.5=001, 1=010, 1.5=011, 2=100, 3=101, 4=110, 6=111
    # (same as default but let's check variations)

    # ── Strategy 10: Powers of 2 get sparse codes, ×1.5 get dense codes ──
    # The ×1.5 case (K=3) produces two adjacent bits in output.
    # The K=9 case produces a specific 4-bit pattern.
    # Try: M-values close to the "1" values to exploit sharing

    candidates.sort(key=lambda x: x[0])
    print("\n=== Structured remapping results ===")
    for score, perm, desc in candidates:
        print(f"  {score:4d}: {list(perm):30s}  {desc}")

    return candidates


def analyze_output_structure():
    """Detailed analysis of what each output bit actually depends on."""
    print("\n=== Output bit structure analysis (default encoding) ===")
    perm = tuple(range(8))
    tt = build_truth_table(perm)
    funcs = tt_to_bit_functions(tt)

    # For each output bit, show which inputs matter
    for bit_idx in range(9):
        f = funcs[bit_idx]
        ones = sum(f)
        if ones == 0:
            print(f"bit {bit_idx}: ALWAYS 0")
            continue
        if ones == 256:
            print(f"bit {bit_idx}: ALWAYS 1")
            continue

        # Check which input bits are "relevant" (flip affects output)
        relevant_inputs = []
        for inp_bit in range(8):
            # Does toggling inp_bit ever change the output?
            matters = False
            for idx in range(256):
                flipped = idx ^ (1 << inp_bit)
                if f[idx] != f[flipped]:
                    matters = True
                    break
            if matters:
                inp_name = f"a{inp_bit // 4}" if inp_bit < 4 else f"b{inp_bit - 4}"
                # Reorder: a0..a3 = bits 7..4, b0..b3 = bits 3..0
                actual_name = f"{'a' if inp_bit < 4 else 'b'}{inp_bit % 4}"
                relevant_inputs.append(actual_name)

        print(f"bit {bit_idx}: {ones:3d}/256 ones | depends on: {relevant_inputs}")


def derive_circuit_for_best_remap():
    """
    For the best known remapping, try to derive an explicit circuit.
    """
    from fp4_core import search_all_remappings
    print("\n=== Finding best remapping ===")
    results = search_all_remappings(verbose=True)
    best_score, best_perm = results[0]
    print(f"\nBest: score={best_score}, perm={list(best_perm)}")

    tt = build_truth_table(best_perm)

    # Show magnitude encoding
    print("\nBest magnitude encoding:")
    for i, mag in enumerate(MAGNITUDES):
        bits = best_perm[i]
        print(f"  {mag:4.1f} -> {bits:03b}")

    # Detailed bit analysis
    analyze_output_structure()

    return best_perm, best_score


if __name__ == "__main__":
    print("=" * 60)
    print("FP4 Multiplier - Analytical Approach")
    print("=" * 60)

    # Show decompositions
    build_multiplication_table()

    # Try structured remappings
    candidates = try_structured_remappings()

    # Analyze output structure with default encoding
    analyze_output_structure()

    # Find best via exhaustive search
    best_perm, best_score = derive_circuit_for_best_remap()
