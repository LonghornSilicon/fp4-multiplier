"""
Z3-based exact circuit synthesis for FP4 multiplier.

Uses the EXACT SYNTHESIS approach: for a given truth table, find the
minimum number of 2-input gates (AND/OR/XOR) + NOT gates to implement it.

We encode the circuit as a SAT problem: does a circuit with N gates exist?
Binary search on N to find the minimum.
"""

try:
    from z3 import *
    HAS_Z3 = True
except ImportError:
    HAS_Z3 = False
    print("Z3 not available. Install with: pip install z3-solver")

from fp4_core import (
    build_truth_table, tt_to_bit_functions, search_all_remappings, MAGNITUDES
)


def exact_synth_single_output(func, max_gates=30, verbose=True):
    """
    Find minimum gates to implement a single-output boolean function
    of 8 inputs using AND, OR, XOR, NOT.

    func: list of 256 bits (function truth table, indexed by 8-bit input)
    Returns: (min_gates, circuit_description) or None if not found within max_gates
    """
    if not HAS_Z3:
        return None

    n_inputs = 8  # a0..a3, b0..b3

    for n_gates in range(0, max_gates + 1):
        if verbose:
            print(f"  Trying {n_gates} gates...", end='', flush=True)

        s = Solver()

        # Variables:
        # - gate_type[i] in {AND=0, OR=1, XOR=2} for gate i
        # - gate_left[i] in {0..n_inputs+i-1} (input to this gate)
        # - gate_right[i] in {0..n_inputs+i-1}
        # - gate_inv_left[i] in {0,1} (invert left input?)
        # - gate_inv_right[i] in {0,1} (invert right input?)
        # - output_node: which gate/input is the output
        # - output_inv: invert the output?

        # We evaluate the circuit on all 256 inputs simultaneously using bitvectors

        # Wire values as 256-bit bitvectors (one bit per input combination)
        # Input wires
        wires = []
        for k in range(n_inputs):
            # Wire k represents bit k of the 8-bit input
            # For input combination idx (0..255), bit k = (idx >> (7-k)) & 1
            val = 0
            for idx in range(256):
                if (idx >> (7 - k)) & 1:
                    val |= (1 << idx)
            wires.append(BitVecVal(val, 256))

        # Gate wires (symbolic)
        gate_type = [Int(f'gt_{i}') for i in range(n_gates)]
        gate_left = [Int(f'gl_{i}') for i in range(n_gates)]
        gate_right = [Int(f'gr_{i}') for i in range(n_gates)]
        gate_inv_l = [Bool(f'gil_{i}') for i in range(n_gates)]
        gate_inv_r = [Bool(f'gir_{i}') for i in range(n_gates)]
        output_node = Int('out_node')
        output_inv = Bool('out_inv')

        # Constraints
        for i in range(n_gates):
            s.add(gate_type[i] >= 0, gate_type[i] <= 2)
            s.add(gate_left[i] >= 0, gate_left[i] < n_inputs + i)
            s.add(gate_right[i] >= 0, gate_right[i] < n_inputs + i)
            # No self-loops or forward connections handled by < i

        s.add(output_node >= 0, output_node < n_inputs + n_gates)

        # This direct Z3 approach is too slow for 256-bit bitvectors with symbolic gates.
        # Switch to a simpler enumeration approach.
        # TODO: use a better encoding
        break  # placeholder

    return None


def estimate_gate_count_quine_mccluskey(func):
    """
    Estimate gate count using a simple prime implicant coverage.
    Returns (sop_gates, pos_gates) - gates needed in 2-level form.

    SOP gate count = sum of (AND gates for each term) + OR gates
    Each AND term of k literals needs k-1 AND gates + possible NOTs
    """
    n = 8  # 8 inputs

    # Get minterms and maxterms
    ones = [i for i, v in enumerate(func) if v == 1]
    zeros = [i for i, v in enumerate(func) if v == 0]

    if not ones:
        return (0, 0)  # constant 0
    if not zeros:
        return (0, 0)  # constant 1

    # Very rough estimate: count ones and zeros
    # SOP: need about len(ones) AND gates, one OR
    # POS: need about len(zeros) OR gates, one AND
    sop_gates = len(ones) * n + max(0, len(ones) - 1)
    pos_gates = len(zeros) * n + max(0, len(zeros) - 1)

    return (sop_gates, pos_gates)


def analyze_bit_structure(tt, perm_label="default"):
    """Analyze the structure of each output bit's truth table."""
    funcs = tt_to_bit_functions(tt)
    print(f"\n=== Analysis for {perm_label} ===")
    for i, f in enumerate(funcs):
        ones = sum(f)
        zeros = 256 - ones
        # Check special structures
        # Is it XOR-decomposable? (f(a,b) = g(a) XOR h(b))
        is_xor = True
        for a1 in range(16):
            for a2 in range(16):
                for b1 in range(16):
                    for b2 in range(16):
                        if (f[(a1 << 4) | b1] ^ f[(a1 << 4) | b2] ^
                                f[(a2 << 4) | b1] ^ f[(a2 << 4) | b2]) != 0:
                            is_xor = False
                            break
                    if not is_xor:
                        break
                if not is_xor:
                    break
            if not is_xor:
                break

        # Is it product-decomposable? (f(a,b) = g(a) AND h(b) or similar)
        # f is AND-decomposable if: whenever f=1, it only depends on one group
        # Simplification: check if output is all-0 (constant)
        is_const = (ones == 0 or ones == 256)

        print(f"  bit {i}: {ones:3d} ones, {zeros:3d} zeros | "
              f"{'XOR-decomp' if is_xor else '          '} | "
              f"{'CONSTANT' if is_const else ''}")


def find_best_remapping_and_analyze():
    """Find best remapping by exhaustive search, then analyze top candidates."""
    print("Running exhaustive remapping search...")
    results = search_all_remappings(verbose=True)

    print(f"\nTop 20 remappings by heuristic score:")
    for score, perm in results[:20]:
        print(f"  score={score:4d}, perm={list(perm)}")

    # Detailed analysis of top 5
    for score, perm in results[:5]:
        tt = build_truth_table(perm)
        label = f"perm={list(perm)} score={score}"
        analyze_bit_structure(tt, label)

    return results


if __name__ == "__main__":
    results = find_best_remapping_and_analyze()
