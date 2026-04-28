"""
Gate-level synthesis for FP4 multiplier.

Given a truth table and a remapping, this module:
1. Implements Quine-McCluskey for exact 2-level minimization
2. Implements a greedy multilevel synthesizer with gate sharing
3. Counts the final gate cost (AND/OR/XOR = 1, NOT = 1)
4. Generates the Python circuit code for the assignment

Gate model:
  NOT(x)      = 1 gate
  AND(x, y)   = 1 gate
  OR(x, y)    = 1 gate
  XOR(x, y)   = 1 gate
  Constant 0 or 1 = 0 gates
"""

from itertools import combinations
from fp4_core import (
    FP4_VALUES, MAGNITUDES, build_truth_table, tt_to_bit_functions, score_tt
)


# ─── Quine-McCluskey ─────────────────────────────────────────────────────────

def qm_minimize(ones, n_vars=8):
    """
    Quine-McCluskey minimization.
    ones: set of minterms (integers 0..2^n_vars-1)
    Returns list of prime implicants as (mask, value) tuples.
    mask: bits that matter (1=relevant), value: value of those bits
    """
    if not ones:
        return []  # always 0

    don't_cares = set()  # could add don't-cares for unused input combos
    all_minterms = set(ones)

    # Initialize: each minterm is an implicant
    implicants = {(2**n_vars - 1, m) for m in ones}

    prime_implicants = set()

    while implicants:
        next_implicants = set()
        used = set()

        imp_list = list(implicants)
        for i in range(len(imp_list)):
            for j in range(i + 1, len(imp_list)):
                mask_i, val_i = imp_list[i]
                mask_j, val_j = imp_list[j]

                if mask_i != mask_j:
                    continue

                diff = val_i ^ val_j
                if diff == 0 or (diff & (diff - 1)) != 0:
                    continue  # must differ in exactly 1 bit

                new_mask = mask_i & ~diff
                new_val = val_i & ~diff
                new_imp = (new_mask, new_val)
                next_implicants.add(new_imp)
                used.add(imp_list[i])
                used.add(imp_list[j])

        for imp in implicants:
            if imp not in used:
                prime_implicants.add(imp)

        implicants = next_implicants

    # Now find minimum cover (greedy)
    uncovered = set(ones)
    cover = []

    # Sort prime implicants by number of minterms they cover (desc)
    def implicant_minterms(imp):
        mask, val = imp
        # iterate over all combinations of don't-care bits
        result = set()
        dontcare_bits = [b for b in range(n_vars) if not (mask >> b) & 1]
        for combo in range(2 ** len(dontcare_bits)):
            m = val
            for k, bit in enumerate(dontcare_bits):
                if (combo >> k) & 1:
                    m |= (1 << bit)
            if m in all_minterms:
                result.add(m)
        return result

    pi_coverage = {imp: implicant_minterms(imp) for imp in prime_implicants}

    # Greedy set cover
    while uncovered:
        best = max(prime_implicants, key=lambda p: len(pi_coverage[p] & uncovered))
        cover.append(best)
        uncovered -= pi_coverage[best]

    return cover


def implicant_gate_cost(imp, n_vars=8):
    """
    Gate cost for a single product term (prime implicant).
    mask: relevant bits, val: values of relevant bits
    """
    mask, val = imp
    relevant = bin(mask).count('1')
    if relevant == 0:
        return 0  # constant
    if relevant == 1:
        # Single literal - free if positive, 1 NOT if negated
        bit = (mask & -mask).bit_length() - 1
        if (val >> bit) & 1:
            return 0  # positive literal
        else:
            return 1  # NOT
    # k relevant literals → k-1 AND gates + NOTs for negated literals
    n_inverted = sum(1 for b in range(n_vars) if (mask >> b) & 1 and not (val >> b) & 1)
    return n_inverted + (relevant - 1)


def sop_gate_cost(implicants, n_vars=8):
    """Total gate cost for a SOP with the given prime implicants."""
    if not implicants:
        return 0  # constant 0
    if len(implicants) == 1:
        return implicant_gate_cost(implicants[0], n_vars)
    return sum(implicant_gate_cost(imp, n_vars) for imp in implicants) + (len(implicants) - 1)


def minimize_and_count(tt, verbose=True):
    """
    Minimize each output bit independently using QM, count total gates.
    No sharing between output bits.
    Returns total_gates.
    """
    funcs = tt_to_bit_functions(tt)
    total = 0
    results = []

    for bit_idx, f in enumerate(funcs):
        ones = [i for i, v in enumerate(f) if v == 1]
        zeros = [i for i, v in enumerate(f) if v == 0]

        if not ones:
            results.append((bit_idx, 0, "constant 0"))
            continue
        if not zeros:
            results.append((bit_idx, 0, "constant 1"))
            continue

        # Try both SOP (minimize ones) and POS (minimize zeros)
        pi_sop = qm_minimize(ones)
        cost_sop = sop_gate_cost(pi_sop)

        # For POS: minimize zeros, then invert → same structure + 1 NOT
        pi_pos = qm_minimize(zeros)
        cost_pos = sop_gate_cost(pi_pos) + 1  # extra NOT for inversion

        cost = min(cost_sop, cost_pos)
        desc = f"SOP={cost_sop}, POS={cost_pos}"
        results.append((bit_idx, cost, desc))
        total += cost

    if verbose:
        for bit_idx, cost, desc in results:
            print(f"  bit {bit_idx}: {cost:3d} gates  ({desc})")
        print(f"  TOTAL (no sharing): {total} gates")

    return total, results


# ─── Shared-gate analysis ─────────────────────────────────────────────────────

def find_shared_terms(funcs, n_vars=8):
    """
    Find common sub-expressions across multiple output bits.
    This is a heuristic for multilevel synthesis.
    """
    # Collect all prime implicants for all output bits
    all_pis = {}
    for bit_idx, f in enumerate(funcs):
        ones = [i for i, v in enumerate(f) if v == 1]
        if not ones or len(ones) == 256:
            continue
        pis = qm_minimize(ones)
        all_pis[bit_idx] = pis

    # Find implicants that appear in multiple output functions
    # (same mask, same val = same sub-expression)
    from collections import Counter
    pi_usage = Counter()
    for bit_idx, pis in all_pis.items():
        for pi in pis:
            pi_usage[pi] += 1

    shared = [(count, pi) for pi, count in pi_usage.items() if count > 1]
    shared.sort(reverse=True)
    return shared, all_pis


# ─── Circuit code generation ─────────────────────────────────────────────────

def generate_circuit_code(truth_table_func, perm, n_vars=8):
    """
    Generate Python code for write_your_multiplier_here() based on the
    given truth table (as a function from 8-bit input to 9-bit output).
    Uses a simple SOP approach.
    """
    funcs = tt_to_bit_functions(truth_table_func)
    lines = []
    lines.append("def write_your_multiplier_here(a0, a1, a2, a3, b0, b1, b2, b3):")
    lines.append("    # Generated circuit")

    for bit_idx, f in enumerate(funcs):
        ones = [i for i, v in enumerate(f) if v == 1]
        if not ones:
            lines.append(f"    res{bit_idx} = False")
            continue
        if len(ones) == 256:
            lines.append(f"    res{bit_idx} = True")
            continue

        # Build SOP expression
        terms = []
        for minterm in ones:
            # minterm is 8 bits: a0(bit7) a1(bit6) a2(bit5) a3(bit4) b0(bit3) b1(bit2) b2(bit1) b3(bit0)
            literals = []
            for k, name in enumerate(['a0', 'a1', 'a2', 'a3', 'b0', 'b1', 'b2', 'b3']):
                bit_val = (minterm >> (7 - k)) & 1
                if bit_val:
                    literals.append(name)
                else:
                    literals.append(f"NOT({name})")
            # AND all literals
            term = literals[0]
            for lit in literals[1:]:
                term = f"AND({term}, {lit})"
            terms.append(term)

        if len(terms) == 1:
            expr = terms[0]
        else:
            expr = terms[0]
            for t in terms[1:]:
                expr = f"OR({expr}, {t})"
        lines.append(f"    res{bit_idx} = {expr}")

    lines.append("    return res0, res1, res2, res3, res4, res5, res6, res7, res8")
    return '\n'.join(lines)


# ─── Main analysis ───────────────────────────────────────────────────────────

def run_full_analysis(perm=None, label=""):
    """Run full analysis for a given permutation."""
    if perm is None:
        perm = tuple(range(8))
        label = "default"

    print(f"\n{'='*60}")
    print(f"Analysis: {label}, perm={list(perm)}")
    print(f"{'='*60}")

    tt = build_truth_table(perm)
    print(f"Heuristic score: {score_tt(tt)}")

    print("\nQM minimization (independent bits):")
    total_gates, results = minimize_and_count(tt, verbose=True)

    funcs = tt_to_bit_functions(tt)
    shared, all_pis = find_shared_terms(funcs)
    if shared:
        print(f"\nShared terms across output bits:")
        for count, pi in shared[:10]:
            mask, val = pi
            print(f"  used in {count} bits: mask={mask:08b} val={val:08b}")

    return total_gates


if __name__ == "__main__":
    print("FP4 Multiplier Gate Synthesis")
    print("=" * 60)

    # Analyze default encoding
    gates_default = run_full_analysis(tuple(range(8)), "Default encoding")

    # Find the best remapping
    from fp4_core import search_all_remappings
    print("\nSearching all remappings...")
    results = search_all_remappings(verbose=True)

    print(f"\nTop 5 by heuristic score:")
    best_gates = float('inf')
    best_perm = None
    for score, perm in results[:5]:
        gates = run_full_analysis(perm, f"score={score}")
        if gates < best_gates:
            best_gates = gates
            best_perm = perm

    print(f"\n{'='*60}")
    print(f"Best QM gate count: {best_gates} gates")
    print(f"Best permutation: {list(best_perm)}")
    print(f"(Note: QM gives 2-level circuits; multilevel synthesis would be better)")
