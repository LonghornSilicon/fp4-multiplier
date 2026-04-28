"""
Advanced BDD synthesis for FP4 x FP4 multiplier.

Explores:
1. Factored BDD decomposition
2. Sifting for optimal variable order
3. AND-INVERTER decomposition (like ABC)
4. Custom circuit extraction with better sharing
"""

from pyeda.inter import *
from pyeda.boolalg.bdd import bdd2expr, BDDNODEZERO, BDDNODEONE, BinaryDecisionDiagram
from collections import defaultdict
import itertools

# FP4 value table
FP4_TABLE = [0.0, 0.5, 1.0, 1.5, 2.0, 3.0, 4.0, 6.0,
             0.0, -0.5, -1.0, -1.5, -2.0, -3.0, -4.0, -6.0]


def build_truth_table():
    """Build the FP4 multiplier truth table."""
    table = {}
    for a_orig in range(16):
        for b_orig in range(16):
            a_val = FP4_TABLE[a_orig]
            b_val = FP4_TABLE[b_orig]
            qi9 = int(round(a_val * b_val * 4))
            qi9_masked = qi9 & 0x1FF
            table[(a_orig, b_orig)] = qi9_masked
    return table


def build_bdds():
    """Build BDDs for all outputs."""
    a = [bddvar(f'a{i}') for i in range(4)]
    b = [bddvar(f'b{i}') for i in range(4)]

    truth_table = build_truth_table()

    output_bdds = []
    for bit in range(9):
        f = expr2bdd(expr(False))
        for (a_val, b_val), out in truth_table.items():
            if (out >> (8 - bit)) & 1:
                term = expr2bdd(expr(True))
                for i in range(4):
                    if (a_val >> (3-i)) & 1:
                        term = term & a[i]
                    else:
                        term = term & ~a[i]
                for i in range(4):
                    if (b_val >> (3-i)) & 1:
                        term = term & b[i]
                    else:
                        term = term & ~b[i]
                f = f | term
        output_bdds.append(f)

    return output_bdds, a, b


def collect_all_nodes(bdds):
    """Collect all unique BDD nodes from all outputs."""
    all_nodes = {}
    visited = set()

    def _collect(node):
        if id(node) in visited:
            return
        visited.add(id(node))
        all_nodes[id(node)] = node

        if node is BDDNODEZERO or node is BDDNODEONE:
            return

        _collect(node.lo)
        _collect(node.hi)

    for f in bdds:
        _collect(f.node)

    return all_nodes


def extract_aig_circuit(bdds):
    """
    Extract AND-INVERTER Graph from BDDs.
    This is closer to what ABC does.

    Key insight: f = ITE(x, f_hi, f_lo) = (x AND f_hi) OR (NOT x AND f_lo)
    In AIG: OR(a,b) = NOT(AND(NOT a, NOT b))
    So: f = NOT(AND(NOT(AND(x, f_hi)), NOT(AND(NOT x, f_lo))))
         = 3 ANDs + 4 NOTs = 7 gates per node (naive)

    Better: f = NOT(AND(NOT(AND(x, f_hi)), AND(NOT x, NOT f_lo)))
    when f_lo is already inverted...

    Actually, for AIG we should use decomposition:
    f = (x AND f_hi) OR (NOT x AND f_lo)
      = NOT(NOT(x AND f_hi) AND NOT(NOT x AND f_lo))
      = NOT(AND(NAND(x, f_hi), NAND(NOT x, f_lo)))

    With inverter bubbles absorbed, each MUX needs 3 AND gates.
    """
    cache = {}  # node_id -> (result_wire, is_inverted, and_count)
    and_gates = []
    not_gates = []

    def _extract(node, need_inverted=False):
        key = (id(node), need_inverted)
        if key in cache:
            return cache[key]

        if node is BDDNODEZERO:
            result = ('ZERO', False, 0) if not need_inverted else ('ONE', False, 0)
        elif node is BDDNODEONE:
            result = ('ONE', False, 0) if not need_inverted else ('ZERO', False, 0)
        elif node.lo is BDDNODEZERO and node.hi is BDDNODEONE:
            # f = x
            var = str(node.root)
            if need_inverted:
                result = (f'NOT_{var}', True, 1)
                not_gates.append(var)
            else:
                result = (var, False, 0)
        elif node.lo is BDDNODEONE and node.hi is BDDNODEZERO:
            # f = NOT x
            var = str(node.root)
            if need_inverted:
                result = (var, False, 0)
            else:
                result = (f'NOT_{var}', True, 1)
                not_gates.append(var)
        else:
            var = str(node.root)
            lo_wire, _, lo_ands = _extract(node.lo, False)
            hi_wire, _, hi_ands = _extract(node.hi, False)

            # MUX using AND-OR
            # f = (var AND hi) OR (NOT var AND lo)
            # AIG: NOT(AND(NOT(AND(var, hi)), NOT(AND(NOT var, lo))))

            gate_id = len(and_gates)

            if node.lo is BDDNODEZERO:
                # f = var AND hi
                and_gates.append((var, hi_wire))
                result = (f'AND_{gate_id}', False, 1 + lo_ands + hi_ands)
            elif node.hi is BDDNODEZERO:
                # f = NOT var AND lo
                and_gates.append((f'NOT_{var}', lo_wire))
                result = (f'AND_{gate_id}', False, 2 + lo_ands + hi_ands)  # +1 for NOT
            elif node.lo is BDDNODEONE:
                # f = var OR hi = NOT(AND(NOT var, NOT hi))
                # Actually: f = (NOT var) implies hi = NOT var OR hi
                and_gates.append((f'NOT_{var}', f'NOT_{hi_wire}'))
                result = (f'NOT_AND_{gate_id}', False, 3 + lo_ands + hi_ands)
            elif node.hi is BDDNODEONE:
                # f = var OR lo
                and_gates.append((f'NOT_{var}', f'NOT_{lo_wire}'))
                result = (f'NOT_AND_{gate_id}', False, 3 + lo_ands + hi_ands)
            else:
                # General MUX: 3 ANDs + 2 NOTs in AIG
                # (var AND hi) OR ((NOT var) AND lo)
                # = NOT(NAND(var, hi) AND NAND(NOT var, lo))
                and1 = len(and_gates)
                and_gates.append((var, hi_wire))
                and2 = len(and_gates)
                and_gates.append((f'NOT_{var}', lo_wire))
                # OR via NAND-NAND
                and3 = len(and_gates)
                and_gates.append((f'NOT_AND_{and1}', f'NOT_AND_{and2}'))
                result = (f'NOT_AND_{and3}', False, 5 + lo_ands + hi_ands)

            if need_inverted:
                result = (f'NOT_{result[0]}', True, result[2] + 1)

        cache[key] = result
        return result

    # Extract all outputs
    total_gates = 0
    print("AIG Extraction:")
    for i, f in enumerate(bdds):
        wire, inv, gates = _extract(f.node, False)
        print(f"  out[{i}]: ~{gates} AIG gates (incremental)")
        total_gates += gates

    print(f"\n  Total AND gates created: {len(and_gates)}")
    print(f"  Estimated total gates (AND + NOT): {len(and_gates) + len(set(not_gates))}")

    return and_gates, not_gates


def analyze_sign_structure(bdds, a, b):
    """
    Deeper analysis of sign bit structure.
    The output sign = a0 XOR b0 when result is non-zero.
    """
    print("\n" + "=" * 60)
    print("SIGN BIT STRUCTURE ANALYSIS")
    print("=" * 60)

    sign_xor = a[0] ^ b[0]  # a0 XOR b0

    # Check how each output relates to sign_xor
    print("\nRelationship of each output to (a0 XOR b0):")
    for i, f in enumerate(bdds):
        # Compute f when sign is positive vs negative
        f_pos = f.restrict({a[0]: 0, b[0]: 0})  # both positive
        f_neg_a = f.restrict({a[0]: 1, b[0]: 0})  # a negative
        f_neg_b = f.restrict({a[0]: 0, b[0]: 1})  # b negative
        f_both = f.restrict({a[0]: 1, b[0]: 1})  # both negative

        # Check if f_neg_a == f_neg_b (symmetry in sign)
        sym = f_neg_a.equivalent(f_neg_b)
        # Check if f_pos == f_both (both-same gives same as both-positive)
        same = f_pos.equivalent(f_both)

        print(f"  out[{i}]: neg_a==neg_b: {sym}, pos==both_neg: {same}")


def compute_exact_minterm_sharing(bdds):
    """
    Compute how many minterms are shared between pairs of outputs.
    """
    print("\n" + "=" * 60)
    print("MINTERM SHARING ANALYSIS")
    print("=" * 60)

    truth_table = build_truth_table()

    # For each output, collect minterms
    output_minterms = []
    for bit in range(9):
        minterms = set()
        for (a_val, b_val), out in truth_table.items():
            if (out >> (8 - bit)) & 1:
                minterms.add((a_val, b_val))
        output_minterms.append(minterms)

    print("\nMinterm counts per output:")
    for i, m in enumerate(output_minterms):
        print(f"  out[{i}]: {len(m)} minterms")

    print("\nMinterm intersection between outputs (shared ON-set):")
    for i in range(9):
        shared = []
        for j in range(9):
            if i != j:
                intersection = len(output_minterms[i] & output_minterms[j])
                if intersection > 0:
                    shared.append(f"out[{j}]:{intersection}")
        if shared:
            print(f"  out[{i}]: {', '.join(shared)}")


def try_reed_muller_synthesis(bdds, a, b):
    """
    Try Reed-Muller (XOR-AND) decomposition.
    Express each function as XOR of product terms.
    """
    print("\n" + "=" * 60)
    print("REED-MULLER SYNTHESIS")
    print("=" * 60)

    truth_table = build_truth_table()

    # For Reed-Muller, we use the algebraic normal form (ANF)
    # f = XOR of (coefficient * product_term) for all 2^n terms

    # We'll compute the ANF coefficients
    n = 8  # 8 input variables

    for bit in range(9):
        # Truth table for this output (in standard order)
        tt = []
        for i in range(256):
            a_val = i >> 4
            b_val = i & 0xF
            out = truth_table[(a_val, b_val)]
            tt.append((out >> (8 - bit)) & 1)

        # Compute ANF via Mobius transform
        anf = tt[:]
        for i in range(n):
            step = 1 << i
            for j in range(0, 256, 2 * step):
                for k in range(step):
                    anf[j + k + step] ^= anf[j + k]

        # Count non-zero ANF coefficients
        nonzero = sum(anf)
        # Find max degree term
        max_degree = 0
        for i, c in enumerate(anf):
            if c:
                degree = bin(i).count('1')
                max_degree = max(max_degree, degree)

        print(f"  out[{bit}]: {nonzero} ANF terms, max degree {max_degree}")

        # If few terms, show them
        if nonzero <= 10:
            terms = []
            for i, c in enumerate(anf):
                if c:
                    if i == 0:
                        terms.append("1")
                    else:
                        vars_in_term = []
                        for v in range(8):
                            if (i >> v) & 1:
                                if v < 4:
                                    vars_in_term.append(f'a{v}')
                                else:
                                    vars_in_term.append(f'b{v-4}')
                        terms.append('*'.join(vars_in_term))
            print(f"       Terms: {' XOR '.join(terms)}")


def factored_form_analysis(bdds):
    """
    Analyze potential for factored form optimization.
    """
    print("\n" + "=" * 60)
    print("FACTORED FORM ANALYSIS")
    print("=" * 60)

    for i, f in enumerate(bdds):
        e = bdd2expr(f)

        # Convert to DNF and CNF
        try:
            dnf = e.to_dnf()
            cnf = e.to_cnf()

            # Count terms
            dnf_str = str(dnf)
            cnf_str = str(cnf)

            # Simple heuristic: count Or(...) at top level
            if 'Or' in dnf_str:
                n_products = dnf_str.count('And') + 1
            else:
                n_products = 1

            if 'And' in cnf_str:
                n_sums = cnf_str.count('Or') + 1
            else:
                n_sums = 1

            print(f"  out[{i}]: ~{n_products} product terms (DNF), ~{n_sums} sum terms (CNF)")
        except Exception as ex:
            print(f"  out[{i}]: Error - {ex}")


def estimate_circuit_from_bdd_properly(bdds):
    """
    Properly estimate circuit cost with full sharing.
    """
    print("\n" + "=" * 60)
    print("PROPER SHARED CIRCUIT ESTIMATE")
    print("=" * 60)

    # Collect all unique BDD nodes
    all_nodes = collect_all_nodes(bdds)

    # Filter out terminals
    internal_nodes = {nid: node for nid, node in all_nodes.items()
                      if node is not BDDNODEZERO and node is not BDDNODEONE}

    print(f"Total unique internal BDD nodes: {len(internal_nodes)}")

    # Best case: each node = 1 gate (if we had perfect MUX primitive)
    # With MUX decomposition: 4 gates (NOT, AND, AND, OR)
    # With XOR decomposition: 3 gates (XOR, AND, XOR)
    # With clever sharing: ~2 gates per node on average

    # Count by structure
    just_var = 0  # x or NOT x
    and_with_zero = 0  # x AND f or NOT x AND f
    or_with_one = 0  # x OR f or NOT x OR f
    full_mux = 0

    for node in internal_nodes.values():
        lo, hi = node.lo, node.hi
        if lo is BDDNODEZERO and hi is BDDNODEONE:
            just_var += 1
        elif lo is BDDNODEONE and hi is BDDNODEZERO:
            just_var += 1
        elif lo is BDDNODEZERO or hi is BDDNODEZERO:
            and_with_zero += 1
        elif lo is BDDNODEONE or hi is BDDNODEONE:
            or_with_one += 1
        else:
            full_mux += 1

    print(f"\nNode type distribution:")
    print(f"  Just variable (x or ~x): {just_var}")
    print(f"  AND with zero (x&f or ~x&f): {and_with_zero}")
    print(f"  OR with one (x|f or ~x|f): {or_with_one}")
    print(f"  Full MUX: {full_mux}")

    # Gate estimate:
    # just_var: 0-1 gates (0 if positive, 1 NOT if negated)
    # and_with_zero: 1-2 gates (AND, maybe NOT)
    # or_with_one: 1-2 gates (OR, maybe NOT)
    # full_mux: 3-4 gates

    low_estimate = (just_var * 0.5 + and_with_zero * 1.5 + or_with_one * 1.5 + full_mux * 3)
    high_estimate = (just_var * 1 + and_with_zero * 2 + or_with_one * 2 + full_mux * 4)

    print(f"\nGate estimate range: {int(low_estimate)} - {int(high_estimate)}")
    print(f"Current best hand-optimized: 82 gates")

    # The BDD doesn't naturally capture the XOR-based sign handling
    # that the hand circuit uses
    print("\nNote: BDD decomposition doesn't naturally find XOR structures")
    print("that the hand-optimized circuit exploits.")


def main():
    print("Advanced BDD Synthesis for FP4 x FP4 Multiplier")
    print("=" * 60)

    bdds, a, b = build_bdds()

    # Run all analyses
    estimate_circuit_from_bdd_properly(bdds)
    analyze_sign_structure(bdds, a, b)
    compute_exact_minterm_sharing(bdds)
    try_reed_muller_synthesis(bdds, a, b)
    extract_aig_circuit(bdds)
    factored_form_analysis(bdds)


if __name__ == "__main__":
    main()
