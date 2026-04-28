"""
BDD-based synthesis for FP4 x FP4 multiplier.

This script:
1. Builds BDDs for all 9 output functions
2. Tries multiple variable orderings
3. Analyzes BDD structure for circuit extraction
4. Estimates gate counts from BDD decomposition
"""

from pyeda.inter import *
from pyeda.boolalg.bdd import bdd2expr, BDDNODEZERO, BDDNODEONE
import itertools
from collections import defaultdict

# FP4 value table: index 0..15 -> float
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
            assert -256 <= qi9 <= 255
            qi9_masked = qi9 & 0x1FF  # 9-bit two's complement
            table[(a_orig, b_orig)] = qi9_masked
    return table


def build_output_functions(var_order):
    """
    Build BDD functions for all 9 outputs with given variable order.

    var_order: list of 8 strings like ['a0', 'a1', 'a2', 'a3', 'b0', 'b1', 'b2', 'b3']
               or permuted versions
    """
    # Create BDD variables in the specified order
    var_map = {}
    bdd_vars = []
    for i, name in enumerate(var_order):
        v = bddvar(name)
        var_map[name] = v
        bdd_vars.append(v)

    a = [var_map[f'a{i}'] for i in range(4)]
    b = [var_map[f'b{i}'] for i in range(4)]

    truth_table = build_truth_table()

    # Build 9 output functions
    output_bdds = []
    for bit in range(9):
        # Collect minterms for this output bit
        on_terms = []
        for (a_val, b_val), out in truth_table.items():
            if (out >> (8 - bit)) & 1:
                # Build the minterm
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
                on_terms.append(term)

        # OR all minterms
        if on_terms:
            f = on_terms[0]
            for t in on_terms[1:]:
                f = f | t
        else:
            f = expr2bdd(expr(False))

        output_bdds.append(f)

    return output_bdds, var_map


def count_bdd_nodes(f):
    """Count the number of nodes in a BDD (excluding terminal nodes)."""
    visited = set()

    def _count(node):
        if node in visited:
            return 0
        if node is BDDNODEZERO or node is BDDNODEONE:
            return 0
        visited.add(node)
        cnt = 1
        cnt += _count(node.lo)
        cnt += _count(node.hi)
        return cnt

    return _count(f.node)


def count_shared_bdd_nodes(bdds):
    """Count total nodes when BDDs are shared (multi-output BDD)."""
    visited = set()

    def _visit(node):
        if node in visited:
            return 0
        if node is BDDNODEZERO or node is BDDNODEONE:
            return 0
        visited.add(node)
        cnt = 1
        cnt += _visit(node.lo)
        cnt += _visit(node.hi)
        return cnt

    total = 0
    for f in bdds:
        total += _visit(f.node)
    return total


def bdd_to_circuit_cost(f):
    """
    Estimate circuit cost from BDD using Shannon decomposition.
    Each internal BDD node becomes: MUX = (x AND hi) OR (NOT x AND lo)
    Cost: 1 NOT + 2 AND + 1 OR = 4 gates per node

    With better decomposition using XOR:
    f = (x AND (hi XOR lo)) XOR lo
    Cost: 1 AND + 2 XOR = 3 gates per node (if XOR available)

    We'll report both estimates.
    """
    n_nodes = count_bdd_nodes(f)
    mux_cost = 4 * n_nodes  # NOT + 2 AND + OR
    xor_cost = 3 * n_nodes  # AND + 2 XOR
    return n_nodes, mux_cost, xor_cost


def shared_bdd_circuit_cost(bdds):
    """Estimate circuit cost for shared multi-output BDD."""
    n_nodes = count_shared_bdd_nodes(bdds)
    mux_cost = 4 * n_nodes
    xor_cost = 3 * n_nodes
    return n_nodes, mux_cost, xor_cost


def analyze_variable_influence(bdds, var_names):
    """Analyze how much each variable influences the BDD size."""
    results = {}
    for var_name in var_names:
        # Count how many nodes test this variable
        count = 0
        visited = set()

        def _count_var(node):
            nonlocal count
            if node in visited:
                return
            if node is BDDNODEZERO or node is BDDNODEONE:
                return
            visited.add(node)
            if str(node.root) == var_name:
                count += 1
            _count_var(node.lo)
            _count_var(node.hi)

        for f in bdds:
            _count_var(f.node)

        results[var_name] = count
    return results


def try_ordering(order_name, var_order):
    """Try a specific variable ordering and report statistics."""
    print(f"\n{'='*60}")
    print(f"Variable ordering: {order_name}")
    print(f"Order: {' < '.join(var_order)}")
    print('='*60)

    bdds, var_map = build_output_functions(var_order)

    # Per-output statistics
    total_nodes = 0
    print("\nPer-output BDD statistics:")
    print(f"{'Output':<8} {'Nodes':>8} {'MUX cost':>10} {'XOR cost':>10}")
    print("-" * 40)

    for i, f in enumerate(bdds):
        nodes, mux, xor = bdd_to_circuit_cost(f)
        total_nodes += nodes
        print(f"out[{i}]    {nodes:>8} {mux:>10} {xor:>10}")

    # Shared statistics
    shared_nodes, shared_mux, shared_xor = shared_bdd_circuit_cost(bdds)

    print("-" * 40)
    print(f"Sum      {total_nodes:>8} {4*total_nodes:>10} {3*total_nodes:>10}")
    print(f"Shared   {shared_nodes:>8} {shared_mux:>10} {shared_xor:>10}")

    # Variable influence
    print("\nVariable influence (nodes testing each variable):")
    influence = analyze_variable_influence(bdds, var_order)
    for var_name in var_order:
        print(f"  {var_name}: {influence[var_name]}")

    return {
        'order_name': order_name,
        'var_order': var_order,
        'total_nodes_sum': total_nodes,
        'shared_nodes': shared_nodes,
        'shared_mux_cost': shared_mux,
        'shared_xor_cost': shared_xor,
        'influence': influence,
        'bdds': bdds
    }


def main():
    print("BDD-based Synthesis for FP4 x FP4 Multiplier")
    print("=" * 60)

    # Define different variable orderings to try
    orderings = {
        # Interleaved orderings
        'interleaved_01': ['a0', 'b0', 'a1', 'b1', 'a2', 'b2', 'a3', 'b3'],
        'interleaved_10': ['b0', 'a0', 'b1', 'a1', 'b2', 'a2', 'b3', 'a3'],

        # Grouped orderings
        'grouped_a_first': ['a0', 'a1', 'a2', 'a3', 'b0', 'b1', 'b2', 'b3'],
        'grouped_b_first': ['b0', 'b1', 'b2', 'b3', 'a0', 'a1', 'a2', 'a3'],

        # Sign bits first (a0, b0 are sign bits in FP4)
        'sign_first': ['a0', 'b0', 'a1', 'a2', 'a3', 'b1', 'b2', 'b3'],

        # Exponent bits together, mantissa separate
        # In FP4 E2M1: bit0=sign, bit1-2=exp, bit3=mantissa
        'exp_mant_grouped': ['a1', 'a2', 'b1', 'b2', 'a3', 'b3', 'a0', 'b0'],

        # Reverse interleaved
        'rev_interleaved': ['a3', 'b3', 'a2', 'b2', 'a1', 'b1', 'a0', 'b0'],

        # Sign last
        'sign_last': ['a1', 'a2', 'a3', 'b1', 'b2', 'b3', 'a0', 'b0'],

        # LSB first
        'lsb_first': ['a3', 'a2', 'a1', 'a0', 'b3', 'b2', 'b1', 'b0'],

        # Alternate by importance (sign, then exp, then mantissa)
        'semantic': ['a0', 'b0', 'a1', 'b1', 'a2', 'b2', 'a3', 'b3'],  # Same as interleaved_01
    }

    results = []
    for name, order in orderings.items():
        try:
            result = try_ordering(name, order)
            results.append(result)
        except Exception as e:
            print(f"Error with ordering {name}: {e}")

    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY: All orderings compared")
    print("=" * 60)
    print(f"{'Ordering':<20} {'Shared Nodes':>12} {'MUX gates':>10} {'XOR gates':>10}")
    print("-" * 55)

    results.sort(key=lambda x: x['shared_nodes'])
    for r in results:
        print(f"{r['order_name']:<20} {r['shared_nodes']:>12} {r['shared_mux_cost']:>10} {r['shared_xor_cost']:>10}")

    best = results[0]
    print(f"\nBest ordering: {best['order_name']}")
    print(f"Shared BDD nodes: {best['shared_nodes']}")
    print(f"Estimated gates (MUX): {best['shared_mux_cost']}")
    print(f"Estimated gates (XOR): {best['shared_xor_cost']}")

    # Deeper analysis of best ordering
    print("\n" + "=" * 60)
    print("STRUCTURAL ANALYSIS of best ordering")
    print("=" * 60)

    # Try to extract circuit from BDD
    print("\nConverting BDDs to expressions...")
    for i, f in enumerate(best['bdds']):
        try:
            e = bdd2expr(f)
            # Count literals and operators
            expr_str = str(e)
            n_and = expr_str.count('And')
            n_or = expr_str.count('Or')
            n_not = expr_str.count('Not') + expr_str.count('~')
            print(f"  out[{i}]: ~{n_not} ANDs, ~{n_or} ORs, ~{n_not} NOTs (rough)")
        except Exception as ex:
            print(f"  out[{i}]: Could not convert to expr: {ex}")

    return results


if __name__ == "__main__":
    main()
