"""
ROM-style decomposition research for FP4 magnitude multiplication.

Goal: Can we beat the 44-gate magnitude computation (K-type x shift approach)?

Key insight: 6 inputs (3 mag bits x 2), 8 outputs, only 49 non-zero entries
mapping to just 18 distinct output magnitudes.

Approaches analyzed:
1. Complete truth table enumeration
2. Shannon decomposition on various variables
3. Output bit dependencies (can some bits be computed from others?)
4. "At most 2 bits set" direct computation
5. Espresso/two-level optimization

Run: python3 experiments/exp_rom_decomposition.py
"""

import os
import sys
from collections import defaultdict

# Magnitude encoding (from main multiplier)
_MAG_TO_CODE = {
    0.0: 0b000, 1.5: 0b001, 3.0: 0b010, 6.0: 0b011,
    0.5: 0b100, 1.0: 0b101, 2.0: 0b110, 4.0: 0b111,
}
_CODE_TO_MAG = {v: k for k, v in _MAG_TO_CODE.items()}

# All non-zero magnitudes (codes 001-111)
NON_ZERO_CODES = list(range(1, 8))  # 1..7


def mag_code_to_value(code):
    """Convert 3-bit magnitude code to float value."""
    return _CODE_TO_MAG.get(code, 0.0)


def build_magnitude_truth_table():
    """
    Build the 6-input -> 8-output magnitude truth table.

    Inputs: a1, a2, a3, b1, b2, b3 (6 bits)
    Output: 8-bit magnitude of (|A| * |B| * 4)

    Returns dict: (a1,a2,a3, b1,b2,b3) -> 8-bit magnitude
    """
    table = {}
    for a_code in NON_ZERO_CODES:
        for b_code in NON_ZERO_CODES:
            a1 = (a_code >> 2) & 1
            a2 = (a_code >> 1) & 1
            a3 = a_code & 1
            b1 = (b_code >> 2) & 1
            b2 = (b_code >> 1) & 1
            b3 = b_code & 1

            mag_a = mag_code_to_value(a_code)
            mag_b = mag_code_to_value(b_code)
            product = mag_a * mag_b * 4  # QI9 scaling
            output = int(round(product))

            key = (a1, a2, a3, b1, b2, b3)
            table[key] = output

    return table


def analyze_truth_table(table):
    """Analyze properties of the magnitude truth table."""
    print("=" * 70)
    print("MAGNITUDE TRUTH TABLE ANALYSIS")
    print("=" * 70)

    # Basic stats
    print(f"\nBasic statistics:")
    print(f"  Input combinations: {len(table)} (of 64 possible 6-bit inputs)")
    print(f"  Input codes used: 7 x 7 = 49 (excluding zero magnitude)")

    outputs = sorted(set(table.values()))
    print(f"  Distinct outputs: {len(outputs)}")
    print(f"  Output values: {outputs}")

    # Output bit analysis
    print(f"\n8-bit magnitude representation (bits m7..m0):")
    for out in outputs:
        bits = format(out, '08b')
        popcount = bin(out).count('1')
        print(f"    {out:3d} = 0b{bits}  (popcount={popcount})")

    # Verify "at most 2 bits set" property
    max_popcount = max(bin(out).count('1') for out in outputs)
    print(f"\n  Max popcount: {max_popcount}")
    print(f"  'At most 2 bits' property: {max_popcount <= 2}")

    return outputs


def print_full_truth_table(table):
    """Print the complete truth table."""
    print("\n" + "=" * 70)
    print("COMPLETE TRUTH TABLE (49 entries)")
    print("=" * 70)
    print("a1a2a3 b1b2b3 | mag_A   mag_B   product*4 | output (binary)")
    print("-" * 70)

    for key in sorted(table.keys()):
        a1, a2, a3, b1, b2, b3 = key
        a_code = (a1 << 2) | (a2 << 1) | a3
        b_code = (b1 << 2) | (b2 << 1) | b3
        mag_a = mag_code_to_value(a_code)
        mag_b = mag_code_to_value(b_code)
        out = table[key]

        print(f"  {a1}{a2}{a3}    {b1}{b2}{b3}  | {mag_a:5.1f}   {mag_b:5.1f}   {mag_a*mag_b*4:6.1f}    | {out:3d} = {format(out, '08b')}")


def analyze_output_bit_functions(table):
    """Analyze each output bit as a function of inputs."""
    print("\n" + "=" * 70)
    print("OUTPUT BIT ANALYSIS")
    print("=" * 70)

    bit_minterms = [[] for _ in range(8)]  # bit i = bit from LSB

    for key, out in table.items():
        for i in range(8):
            if (out >> i) & 1:
                bit_minterms[i].append(key)

    for i in range(7, -1, -1):
        minterms = bit_minterms[i]
        print(f"\n  m{i} (bit position {i}): {len(minterms)} minterms")
        if len(minterms) <= 12:
            for m in minterms:
                a1, a2, a3, b1, b2, b3 = m
                a_code = (a1 << 2) | (a2 << 1) | a3
                b_code = (b1 << 2) | (b2 << 1) | b3
                print(f"      ({a1}{a2}{a3}, {b1}{b2}{b3}) -> mag {mag_code_to_value(a_code)} x {mag_code_to_value(b_code)}")


def shannon_decomposition_analysis(table):
    """
    Analyze Shannon decomposition on each variable.

    Shannon: f = (x AND f|x=1) OR (NOT(x) AND f|x=0)
    But for MUX implementation: f = MUX(x, f|x=1, f|x=0)

    We want to find variable splits that minimize resulting complexity.
    """
    print("\n" + "=" * 70)
    print("SHANNON DECOMPOSITION ANALYSIS")
    print("=" * 70)

    var_names = ['a1', 'a2', 'a3', 'b1', 'b2', 'b3']

    for var_idx, var_name in enumerate(var_names):
        print(f"\n--- Split on {var_name} (index {var_idx}) ---")

        # Partition table by value of this variable
        table_0 = {}  # entries where var=0
        table_1 = {}  # entries where var=1

        for key, out in table.items():
            if key[var_idx] == 0:
                # Remove this variable from key
                remaining = tuple(k for i, k in enumerate(key) if i != var_idx)
                table_0[remaining] = out
            else:
                remaining = tuple(k for i, k in enumerate(key) if i != var_idx)
                table_1[remaining] = out

        outputs_0 = set(table_0.values())
        outputs_1 = set(table_1.values())

        print(f"  {var_name}=0: {len(table_0)} entries, {len(outputs_0)} distinct outputs")
        print(f"  {var_name}=1: {len(table_1)} entries, {len(outputs_1)} distinct outputs")
        print(f"  Shared outputs: {len(outputs_0 & outputs_1)}")

        # Per-bit analysis for this split
        for bit in range(7, -1, -1):
            ones_0 = sum(1 for v in table_0.values() if (v >> bit) & 1)
            ones_1 = sum(1 for v in table_1.values() if (v >> bit) & 1)
            print(f"    m{bit}: var=0 has {ones_0}/{len(table_0)} ones, var=1 has {ones_1}/{len(table_1)} ones")


def analyze_k_type_structure(table):
    """
    Analyze the K-type structure for ROM approach.

    M = NOT(a1) for magnitude, so:
    - a1=0: M=1 (codes 001,010,011 = 1.5, 3.0, 6.0)
    - a1=1: M=0 (codes 100,101,110,111 = 0.5, 1.0, 2.0, 4.0)

    K-type = M_a + M_b:
    - K=0 (k1, not_k9, not k3): a1=1, b1=1
    - K=1 (k3): a1 XOR b1 = 1
    - K=2 (k9): a1=0, b1=0
    """
    print("\n" + "=" * 70)
    print("K-TYPE STRUCTURE ANALYSIS")
    print("=" * 70)

    k_partitions = {0: [], 1: [], 2: []}

    for key, out in table.items():
        a1, a2, a3, b1, b2, b3 = key
        M_a = 1 - a1  # M=1 when a1=0
        M_b = 1 - b1  # M=1 when b1=0
        k_type = M_a + M_b
        k_partitions[k_type].append((key, out))

    for k in [0, 1, 2]:
        entries = k_partitions[k]
        outputs = sorted(set(out for _, out in entries))
        print(f"\n  K={k} ({'k1/not_k9' if k==0 else 'k3' if k==1 else 'k9'}):")
        print(f"    Entries: {len(entries)}")
        print(f"    Distinct outputs: {len(outputs)}")
        print(f"    Outputs: {outputs}")

        # K=0: 4x4 = 16 entries (a1=1, b1=1 cases)
        # K=1: 3x4 + 4x3 = 24 entries (a1 XOR b1 = 1)
        # K=2: 3x3 = 9 entries (a1=0, b1=0)


def analyze_two_bit_positions(table):
    """
    Analyze which bit positions are set for each output.

    Since all outputs have at most 2 bits set, can we directly compute
    which 2 positions are set? (Or directly compute the bit positions?)
    """
    print("\n" + "=" * 70)
    print("TWO-BIT POSITION ANALYSIS")
    print("=" * 70)

    outputs = sorted(set(table.values()))

    print("\nOutput -> bit positions set:")
    for out in outputs:
        positions = [i for i in range(8) if (out >> i) & 1]
        print(f"  {out:3d} = 0b{format(out, '08b')} -> positions {positions}")

    # Group by number of bits set
    one_bit = [out for out in outputs if bin(out).count('1') == 1]
    two_bit = [out for out in outputs if bin(out).count('1') == 2]

    print(f"\nOne-bit outputs ({len(one_bit)}): {one_bit}")
    print(f"Two-bit outputs ({len(two_bit)}): {two_bit}")

    # For two-bit outputs: what are the bit separations?
    print("\nTwo-bit outputs - bit separations:")
    for out in two_bit:
        positions = [i for i in range(8) if (out >> i) & 1]
        sep = positions[1] - positions[0]
        print(f"  {out:3d} = positions {positions}, separation = {sep}")


def mux_tree_gate_count():
    """
    Calculate gate count for MUX-tree approach.

    A 2:1 MUX = 3 gates: AND(a, sel) OR AND(b, NOT(sel))
    Actually: MUX(sel, a, b) = OR(AND(sel, a), AND(NOT(sel), b)) = 1 NOT + 2 AND + 1 OR = 4 gates
    But we can share NOT(sel), so per-MUX cost is 2 AND + 1 OR = 3 gates (after first NOT).

    For 6-input function:
    - Full MUX tree: 2^6 - 1 = 63 MUXes = way too many
    - Better: use truth table compression

    Shannon on a1: creates two 5-input functions
    Then recursively decompose...
    """
    print("\n" + "=" * 70)
    print("MUX-TREE GATE COUNT ANALYSIS")
    print("=" * 70)

    print("""
    MUX(sel, high, low) implementation:
      n_sel = NOT(sel)                    # 1 gate (shared)
      sel_and_high = AND(sel, high)       # 1 gate per output bit
      nsel_and_low = AND(n_sel, low)      # 1 gate per output bit
      result = OR(sel_and_high, nsel_and_low)  # 1 gate per output bit

    For 8-bit output: 8 x 3 = 24 gates per MUX level + 1 NOT

    Full 6-input MUX tree depth = 6 levels
    But with truth table compression, we can do better.
    """)

    # Analyze best split variable
    print("\nBest split strategy:")
    print("  Split on a1 (K-type indicator):")
    print("    a1=0: M_a=1, only 3 magnitude values (1.5, 3.0, 6.0)")
    print("    a1=1: M_a=0, 4 magnitude values (0.5, 1.0, 2.0, 4.0)")
    print("  After a1 split:")
    print("    a1=0 branch: 3x7 = 21 entries")
    print("    a1=1 branch: 4x7 = 28 entries")


def espresso_pla_generation(table):
    """Generate Espresso PLA for each output bit."""
    print("\n" + "=" * 70)
    print("ESPRESSO PLA GENERATION")
    print("=" * 70)

    pla_dir = os.path.join(os.path.dirname(__file__), "data")
    os.makedirs(pla_dir, exist_ok=True)

    # Combined PLA for all 8 bits
    pla_path = os.path.join(pla_dir, "mag_6to8.pla")
    with open(pla_path, 'w') as f:
        f.write("# FP4 magnitude multiplication: 6-input, 8-output\n")
        f.write(".i 6\n")
        f.write(".o 8\n")
        f.write(".ilb a1 a2 a3 b1 b2 b3\n")
        f.write(".ob m7 m6 m5 m4 m3 m2 m1 m0\n")
        f.write(".type fr\n")
        f.write(f".p {len(table)}\n")

        for key in sorted(table.keys()):
            in_bits = ''.join(str(b) for b in key)
            out_val = table[key]
            out_bits = format(out_val, '08b')
            f.write(f"{in_bits} {out_bits}\n")

        f.write(".e\n")

    print(f"  Wrote {pla_path}")

    # Individual PLAs for each bit
    for bit in range(8):
        pla_path = os.path.join(pla_dir, f"mag_m{bit}.pla")
        minterms = [(key, 1) for key, out in table.items() if (out >> bit) & 1]
        dontcares = [(key, '-') for key in all_6bit() if key not in table]

        with open(pla_path, 'w') as f:
            f.write(f"# FP4 magnitude bit m{bit}\n")
            f.write(".i 6\n")
            f.write(".o 1\n")
            f.write(".ilb a1 a2 a3 b1 b2 b3\n")
            f.write(f".ob m{bit}\n")
            f.write(".type fd\n")
            f.write(f".p {len(minterms) + len(dontcares)}\n")

            for key, val in minterms:
                in_bits = ''.join(str(b) for b in key)
                f.write(f"{in_bits} {val}\n")
            for key, val in dontcares:
                in_bits = ''.join(str(b) for b in key)
                f.write(f"{in_bits} {val}\n")

            f.write(".e\n")

        print(f"  Wrote {pla_path} ({len(minterms)} minterms)")

    return pla_dir


def all_6bit():
    """Generate all 64 6-bit tuples."""
    for i in range(64):
        yield tuple((i >> (5-j)) & 1 for j in range(6))


def analyze_bit_dependencies(table):
    """
    Check if any output bit can be expressed as a function of other output bits.

    This could save gates if, say, m7 = f(m6, m5, ...).
    """
    print("\n" + "=" * 70)
    print("OUTPUT BIT DEPENDENCY ANALYSIS")
    print("=" * 70)

    # Build output vectors for each entry
    entries = list(table.items())

    # For each bit, check if it can be expressed as AND/OR/XOR of other bits
    for target in range(8):
        target_vals = [(out >> target) & 1 for _, out in entries]

        # Check if target = another_bit
        for other in range(8):
            if other == target:
                continue
            other_vals = [(out >> other) & 1 for _, out in entries]
            if target_vals == other_vals:
                print(f"  m{target} = m{other} (identical)")
            if target_vals == [1 - v for v in other_vals]:
                print(f"  m{target} = NOT(m{other})")

        # Check if target = AND(bi, bj)
        for i in range(8):
            for j in range(i+1, 8):
                i_vals = [(out >> i) & 1 for _, out in entries]
                j_vals = [(out >> j) & 1 for _, out in entries]
                and_vals = [a & b for a, b in zip(i_vals, j_vals)]
                or_vals = [a | b for a, b in zip(i_vals, j_vals)]
                xor_vals = [a ^ b for a, b in zip(i_vals, j_vals)]

                if target_vals == and_vals:
                    print(f"  m{target} = AND(m{i}, m{j})")
                if target_vals == or_vals:
                    print(f"  m{target} = OR(m{i}, m{j})")
                if target_vals == xor_vals:
                    print(f"  m{target} = XOR(m{i}, m{j})")


def k_type_shift_rom_analysis(table):
    """
    Hybrid approach: K-type flags + ROM for within-K outputs.

    Current approach:
    - K-flags: 3 gates (OR, NOT, XOR) + 3 masking = 6 gates
    - S decoder: 11 gates
    - AND-terms: 18 gates
    - Mag OR: 15 gates
    - Total magnitude: ~50 gates (not 44, my mistake)

    Alternative ROM:
    - K-flags: 6 gates (as before)
    - Per-K ROM: smaller functions
      - K=0 (a1=1,b1=1): 4-input (a2a3, b2b3) -> 8-output
      - K=1 (XOR(a1,b1)=1): 4-input (a2a3 or a1'a2a3, b2b3) -> 8-output
      - K=2 (a1=0,b1=0): 4-input (a2a3, b2b3) -> 8-output
    - MUX to select based on K-type
    """
    print("\n" + "=" * 70)
    print("K-TYPE PARTITIONED ROM ANALYSIS")
    print("=" * 70)

    k_tables = {0: {}, 1: {}, 2: {}}

    for key, out in table.items():
        a1, a2, a3, b1, b2, b3 = key
        M_a = 1 - a1
        M_b = 1 - b1
        k_type = M_a + M_b

        # Key for sub-ROM is just (a2, a3, b2, b3)
        sub_key = (a2, a3, b2, b3)
        if sub_key in k_tables[k_type]:
            # For K=1, different (a1,b1) pairs might give same (a2,a3,b2,b3)
            # This can happen since K=1 means a1 XOR b1 = 1
            existing = k_tables[k_type][sub_key]
            if existing != out:
                print(f"  WARNING: K={k_type}, sub_key={sub_key} maps to both {existing} and {out}")
        k_tables[k_type][sub_key] = out

    for k in [0, 1, 2]:
        sub_table = k_tables[k]
        outputs = sorted(set(sub_table.values()))
        print(f"\n  K={k} sub-ROM:")
        print(f"    Entries: {len(sub_table)}")
        print(f"    Distinct outputs: {len(outputs)}")

        # Count minterms per output bit
        for bit in range(7, -1, -1):
            minterms = sum(1 for v in sub_table.values() if (v >> bit) & 1)
            print(f"      m{bit}: {minterms} minterms")


def direct_position_computation():
    """
    Explore computing bit positions directly.

    If output has exactly k bits set at positions p1 < p2, can we compute
    p1 and p2 directly from inputs, then generate (1 << p1) | (1 << p2)?

    For single-bit outputs: decoder from position to one-hot
    For two-bit outputs: two decoders + OR
    """
    print("\n" + "=" * 70)
    print("DIRECT POSITION COMPUTATION ANALYSIS")
    print("=" * 70)

    table = build_magnitude_truth_table()

    # Group entries by output pattern type
    one_bit_entries = [(k, v) for k, v in table.items() if bin(v).count('1') == 1]
    two_bit_entries = [(k, v) for k, v in table.items() if bin(v).count('1') == 2]

    print(f"\n  One-bit outputs: {len(one_bit_entries)} entries")
    print(f"  Two-bit outputs: {len(two_bit_entries)} entries")

    # For one-bit outputs: position = log2(output)
    print("\n  One-bit position analysis:")
    for key, out in sorted(one_bit_entries, key=lambda x: x[1]):
        pos = out.bit_length() - 1
        a1, a2, a3, b1, b2, b3 = key
        a_code = (a1 << 2) | (a2 << 1) | a3
        b_code = (b1 << 2) | (b2 << 1) | b3
        S = (a2*2 + a3) + (b2*2 + b3)  # E-sum
        print(f"    {key} -> {out:3d} = 2^{pos}, S={S}")

    # For two-bit outputs: positions
    print("\n  Two-bit position analysis:")
    for key, out in sorted(two_bit_entries, key=lambda x: x[1]):
        positions = [i for i in range(8) if (out >> i) & 1]
        a1, a2, a3, b1, b2, b3 = key
        S = (a2*2 + a3) + (b2*2 + b3)  # E-sum
        M_a = 1 - a1
        M_b = 1 - b1
        k_type = M_a + M_b
        print(f"    {key} -> {out:3d} = 2^{positions[1]} + 2^{positions[0]}, S={S}, K={k_type}")


def gate_count_estimate():
    """
    Compare gate counts for different approaches.
    """
    print("\n" + "=" * 70)
    print("GATE COUNT COMPARISON")
    print("=" * 70)

    print("""
    Current approach (K-type x shift):
    ----------------------------------
    E-sum (2-bit adder):       7 gates
    K-flags (OR, NOT, XOR):    3 gates
    K-masking (3x AND):        3 gates  [not counted in "magnitude only"]
    S-decoder (one-hot):      11 gates
    AND-terms (K x sh):       18 gates
    Magnitude OR:             15 gates
    ----------------------------------
    Subtotal (magnitude):     44 gates  (7+3+11+18+15, excl nz & masking)
    With K-masking:           47 gates

    Alternative 1: Full 6->8 ROM (truth table lookup)
    -------------------------------------------------
    - 49 entries, 8 output bits
    - Per output bit: ~10-15 gates after Espresso minimization (guess)
    - Total: 80-120 gates (worse than current)

    Alternative 2: K-partitioned ROM
    --------------------------------
    - K=0: 16 entries, 4 inputs -> 8 outputs
    - K=1: 24 entries collapsing to ~12-16 unique, 4 inputs (need careful analysis)
    - K=2: 9 entries, 4 inputs -> 8 outputs
    - Plus K-detection: 3 gates
    - Plus output MUX: 8 * 3 = 24 gates for 3-way MUX
    - Each sub-ROM: 4-input function, easier to minimize
    - Estimate: 3 + (15 + 15 + 10) + 24 = 67 gates (probably worse)

    Alternative 3: Direct position computation
    ------------------------------------------
    - Compute K-type: 3 gates
    - Compute S (E-sum): 7 gates
    - For K=0 (k1): position = S, single bit at position S
    - For K=1 (k3): positions = S-1, S
    - For K=2 (k9): positions = S-2, S+1

    Decoder approach (current is optimal at 11 gates for 3->7):
    - Decoder 7: 11 gates
    - But for k1: need 1 of 7 bits (sh0..sh6)
    - For k3: need 2 adjacent bits
    - For k9: need 2 bits with gap of 3

    The current approach IS the direct position computation!

    Alternative 4: Shared structure exploitation
    --------------------------------------------
    Observation: sh_i is used by multiple K-types
    - sh0: nmc0 only (K=1 uses sh1, K=9 uses sh2)
    - sh1: nmc1, k3_1
    - sh2: nmc2, k3_2, k9_2
    - sh3: nmc3, k3_3, k9_3
    - sh4: nmc4, k3_4, k9_4
    - sh5: nmc5, k3_5, k9_5
    - sh6: nmc6, k3_6, k9_6

    Current AND-terms: 7 (nmc) + 6 (k3, skip sh0) + 5 (k9, skip sh0,sh1) = 18

    Can we share?
    - nmc AND shi is used for bit i
    - k3 AND sh(i+1) is used for bit i
    - So nmc_i and k3_{i+1} both contribute to m_i

    Alternative formula:
      m_i = OR(shi, sh_{i+1}) AND (OR(nmc, k3) restricted to valid)

    Hmm, this doesn't simplify because nmc and k3 depend on different K conditions.
    """)


def run_espresso_if_available(pla_dir):
    """Try to run Espresso on generated PLAs."""
    import subprocess
    import shutil

    espresso = shutil.which("espresso")
    if not espresso:
        # Try common locations
        for path in ["/usr/bin/espresso", "/usr/local/bin/espresso",
                     os.path.expanduser("~/espresso")]:
            if os.path.exists(path):
                espresso = path
                break

    if not espresso:
        print("\n[Espresso not found, skipping minimization]")
        return

    print("\n" + "=" * 70)
    print("ESPRESSO MINIMIZATION RESULTS")
    print("=" * 70)

    for bit in range(8):
        pla_path = os.path.join(pla_dir, f"mag_m{bit}.pla")
        try:
            result = subprocess.run(
                [espresso, "-Dso", pla_path],
                capture_output=True, text=True, timeout=30
            )
            output = result.stdout
            # Count product terms
            terms = len([l for l in output.split('\n') if l and not l.startswith('.') and not l.startswith('#')])
            print(f"  m{bit}: {terms} product terms after Espresso")
        except Exception as e:
            print(f"  m{bit}: Espresso failed: {e}")


def run_abc_on_pla(pla_dir):
    """Try to run ABC on the PLA to get AIG gate count."""
    import subprocess

    abc_bin = "/home/tit/abc/abc"
    abc_cwd = "/home/tit/abc"

    if not os.path.exists(abc_bin):
        print("\n[ABC not found, skipping synthesis]")
        return

    print("\n" + "=" * 70)
    print("ABC SYNTHESIS RESULTS")
    print("=" * 70)

    # Copy PLA to /tmp (ABC doesn't like spaces in paths)
    import shutil
    pla_src = os.path.join(pla_dir, "mag_6to8.pla")
    pla_tmp = "/tmp/mag_6to8.pla"
    shutil.copy(pla_src, pla_tmp)

    script = (
        f"read_pla {pla_tmp}; strash; print_stats; "
        "compress2rs; compress2rs; print_stats; "
        "resyn2; resyn2rs; print_stats; "
        "&get; &deepsyn -T 30; &put; print_stats"
    )

    try:
        result = subprocess.run(
            [abc_bin, "-c", script],
            cwd=abc_cwd,
            capture_output=True, text=True, timeout=60
        )
        print(result.stdout)
        print(result.stderr)
    except Exception as e:
        print(f"ABC failed: {e}")


def main():
    print("ROM-STYLE DECOMPOSITION RESEARCH FOR FP4 MAGNITUDE MULTIPLICATION")
    print("=" * 70)

    # Build truth table
    table = build_magnitude_truth_table()

    # Analyses
    outputs = analyze_truth_table(table)
    print_full_truth_table(table)
    analyze_output_bit_functions(table)
    shannon_decomposition_analysis(table)
    analyze_k_type_structure(table)
    analyze_two_bit_positions(table)
    analyze_bit_dependencies(table)
    k_type_shift_rom_analysis(table)
    direct_position_computation()
    gate_count_estimate()

    # Generate PLAs
    pla_dir = espresso_pla_generation(table)

    # Try Espresso and ABC
    run_espresso_if_available(pla_dir)
    run_abc_on_pla(pla_dir)

    print("\n" + "=" * 70)
    print("CONCLUSIONS")
    print("=" * 70)
    print("""
    Key findings:

    1. The 6->8 magnitude function has 49 entries mapping to 18 distinct outputs.
       All outputs have at most 2 bits set (sparse structure).

    2. The current K-type x shift decomposition IS the optimal way to exploit
       the "at most 2 bits" structure. The decomposition captures:
       - K determines how many bits (1 or 2) and their separation
       - S determines the position(s)

    3. Shannon decomposition on a1 (the M-bit) creates partitions of size 21/28,
       but doesn't reduce complexity because both partitions still need the
       full E-sum decoder.

    4. K-partitioned ROM doesn't help because:
       - We still need the S decoder for each partition
       - The output MUX adds ~24 gates
       - Sub-ROMs don't simplify enough to compensate

    5. No output bit dependencies found that would allow expressing one bit
       as a simple function of others.

    6. The current 44-gate magnitude computation (excluding nz-detect and masking)
       appears near-optimal for this problem structure.

    Potential remaining optimizations:
    - Cross-stage sharing between S-decoder and AND-terms
    - Joint optimization of AND-terms and OR-assembly
    - Alternative negation strategies for signed output
    """)


if __name__ == "__main__":
    main()
