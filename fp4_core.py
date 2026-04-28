"""
FP4 Multiplier Core: truth tables, remapping, gate counting utilities.
"""
import itertools

# All 16 FP4 values in default encoding order (index = 4-bit code)
FP4_VALUES = [
    0, 0.5, 1, 1.5, 2, 3, 4, 6,      # 0b0000..0b0111 (positive / +0)
    0, -0.5, -1, -1.5, -2, -3, -4, -6 # 0b1000..0b1111 (negative / -0)
]

# The 8 distinct magnitudes (indices 0..7 for 3-bit code)
MAGNITUDES = [0, 0.5, 1, 1.5, 2, 3, 4, 6]


def fp4_product_qi9(a_val: float, b_val: float) -> int:
    """Return 4*a*b as a 9-bit two's complement integer."""
    qi9 = int(round(a_val * b_val * 4))
    assert -256 <= qi9 <= 255, f"Overflow: {a_val}*{b_val}*4={qi9}"
    return qi9 & 0x1FF  # mask to 9 bits (two's complement)


def qi9_to_bits(qi9: int):
    """9-bit integer -> list of bits [res0(MSB)..res8(LSB)]."""
    return [(qi9 >> (8 - i)) & 1 for i in range(9)]


def build_truth_table(mag_perm: tuple) -> dict:
    """
    Build truth table for a magnitude permutation.

    mag_perm[i] = new 3-bit code assigned to MAGNITUDES[i]
    Sign bit stays: 0=positive, 1=negative (most significant input bit).

    Returns dict: (a_code4, b_code4) -> list of 9 bits [MSB..LSB]
    """
    # map each of the 16 default fp4 indices to a new 4-bit code
    remap = {}
    for orig_idx in range(16):
        val = FP4_VALUES[orig_idx]
        sign = 1 if val < 0 else 0
        mag_idx = MAGNITUDES.index(abs(val))
        new_code = (sign << 3) | mag_perm[mag_idx]
        remap[orig_idx] = new_code

    table = {}
    for a_orig in range(16):
        for b_orig in range(16):
            a_code = remap[a_orig]
            b_code = remap[b_orig]
            qi9 = fp4_product_qi9(FP4_VALUES[a_orig], FP4_VALUES[b_orig])
            table[(a_code, b_code)] = qi9_to_bits(qi9)
    return table


def tt_to_bit_functions(tt: dict):
    """
    Convert truth table to 9 boolean functions.
    Returns list of 9 lists, each of length 256 (indexed by (a<<4)|b).
    """
    funcs = [[0] * 256 for _ in range(9)]
    for (a, b), bits in tt.items():
        idx = (a << 4) | b
        for i, bit in enumerate(bits):
            funcs[i][idx] = bit
    return funcs


def score_tt(tt: dict) -> int:
    """
    Fast complexity heuristic: sum of min(|ones|,|zeros|) over all 9 output bits.
    Lower = simpler. Used for ranking remappings.
    """
    funcs = tt_to_bit_functions(tt)
    total = 0
    for f in funcs:
        ones = sum(f)
        total += min(ones, 256 - ones)
    return total


def score_tt_detailed(tt: dict):
    """Return per-bit (ones_count, zeros_count) for analysis."""
    funcs = tt_to_bit_functions(tt)
    return [(sum(f), 256 - sum(f)) for f in funcs]


def search_all_remappings(verbose=True):
    """
    Try all 8! = 40320 magnitude permutations, return sorted list of
    (score, mag_perm).
    """
    results = []
    for i, perm in enumerate(itertools.permutations(range(8))):
        tt = build_truth_table(perm)
        s = score_tt(tt)
        results.append((s, perm))
        if verbose and i % 5000 == 0:
            print(f"  {i}/40320 done, best so far: {min(results)[0]}")
    results.sort()
    return results


if __name__ == "__main__":
    # Show default encoding stats
    default_perm = tuple(range(8))  # identity mapping
    tt = build_truth_table(default_perm)
    print("=== Default encoding ===")
    for i, (ones, zeros) in enumerate(score_tt_detailed(tt)):
        print(f"  bit {i}: {ones} ones, {zeros} zeros")
    print(f"  Heuristic score: {score_tt(tt)}")

    print("\n=== Searching all remappings ===")
    results = search_all_remappings(verbose=True)
    print(f"\nTop 10 remappings:")
    for score, perm in results[:10]:
        print(f"  score={score}, perm={perm}")

    print(f"\nBottom 5 (worst):")
    for score, perm in results[-5:]:
        print(f"  score={score}, perm={perm}")
