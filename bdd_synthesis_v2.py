"""
BDD-based synthesis for FP4 x FP4 multiplier - Enhanced version.

This explores:
1. BDD construction with ordering enforcement
2. Shannon decomposition for circuit extraction
3. AND-XOR (Reed-Muller) decomposition
4. Functional decomposition analysis
"""

from pyeda.inter import *
from pyeda.boolalg.bdd import bdd2expr, BDDNODEZERO, BDDNODEONE, BinaryDecisionDiagram
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


def build_espresso_style_bdds():
    """Build BDDs using truth table directly."""
    # Create BDD variables
    a = [bddvar(f'a{i}') for i in range(4)]
    b = [bddvar(f'b{i}') for i in range(4)]

    truth_table = build_truth_table()

    # Build 9 output BDDs
    output_bdds = []
    for bit in range(9):
        # Collect minterms
        minterms = []
        for (a_val, b_val), out in truth_table.items():
            if (out >> (8 - bit)) & 1:
                minterms.append((a_val, b_val))

        # Build BDD from minterms
        f = expr2bdd(expr(False))
        for (av, bv) in minterms:
            term = expr2bdd(expr(True))
            for i in range(4):
                if (av >> (3-i)) & 1:
                    term = term & a[i]
                else:
                    term = term & ~a[i]
            for i in range(4):
                if (bv >> (3-i)) & 1:
                    term = term & b[i]
                else:
                    term = term & ~b[i]
            f = f | term

        output_bdds.append(f)

    return output_bdds, a, b


def traverse_bdd(f):
    """Traverse BDD and collect all nodes with their structure."""
    nodes = {}
    visited = set()

    def _traverse(node, depth=0):
        if id(node) in visited:
            return
        visited.add(id(node))

        if node is BDDNODEZERO:
            nodes[id(node)] = {'type': 'ZERO', 'depth': depth}
            return
        if node is BDDNODEONE:
            nodes[id(node)] = {'type': 'ONE', 'depth': depth}
            return

        # Get variable name
        var_name = str(node.root)

        nodes[id(node)] = {
            'type': 'INTERNAL',
            'var': var_name,
            'depth': depth,
            'lo': id(node.lo),
            'hi': id(node.hi)
        }

        _traverse(node.lo, depth + 1)
        _traverse(node.hi, depth + 1)

    _traverse(f.node)
    return nodes


def count_shared_nodes_detailed(bdds):
    """Count nodes with detailed breakdown."""
    all_nodes = {}
    var_counts = defaultdict(int)

    for f in bdds:
        nodes = traverse_bdd(f)
        for nid, info in nodes.items():
            if nid not in all_nodes:
                all_nodes[nid] = info
                if info['type'] == 'INTERNAL':
                    var_counts[info['var']] += 1

    internal_count = sum(1 for n in all_nodes.values() if n['type'] == 'INTERNAL')
    return internal_count, var_counts


def bdd_to_shannon_gates(f, cache=None):
    """
    Convert BDD to gates using Shannon decomposition.
    f = (x & f_hi) | (~x & f_lo)

    With MUX: 4 gates per node (NOT, AND, AND, OR)
    """
    if cache is None:
        cache = {}

    def _convert(node):
        if id(node) in cache:
            return cache[id(node)]

        if node is BDDNODEZERO:
            return {'gates': 0, 'wire': 'ZERO'}
        if node is BDDNODEONE:
            return {'gates': 0, 'wire': 'ONE'}

        var = str(node.root)
        lo_result = _convert(node.lo)
        hi_result = _convert(node.hi)

        # Check for special cases
        if node.lo is BDDNODEZERO and node.hi is BDDNODEONE:
            # f = x (just the variable)
            result = {'gates': 0, 'wire': var}
        elif node.lo is BDDNODEONE and node.hi is BDDNODEZERO:
            # f = ~x
            result = {'gates': 1, 'wire': f'NOT({var})'}
        elif node.hi is BDDNODEONE:
            # f = x | f_lo (OR)
            result = {'gates': 1 + lo_result['gates'], 'wire': f'OR({var}, {lo_result["wire"]})'}
        elif node.lo is BDDNODEZERO:
            # f = x & f_hi (AND)
            result = {'gates': 1 + hi_result['gates'], 'wire': f'AND({var}, {hi_result["wire"]})'}
        elif node.lo is BDDNODEONE:
            # f = ~x | f_hi
            result = {'gates': 2 + hi_result['gates'], 'wire': f'OR(NOT({var}), {hi_result["wire"]})'}
        elif node.hi is BDDNODEZERO:
            # f = ~x & f_lo
            result = {'gates': 2 + lo_result['gates'], 'wire': f'AND(NOT({var}), {lo_result["wire"]})'}
        elif node.lo is node.hi:
            # f = f_lo = f_hi (shouldn't happen in reduced BDD)
            result = lo_result
        else:
            # General case: MUX = (x & hi) | (~x & lo)
            # 4 gates: NOT, AND, AND, OR
            result = {
                'gates': 4 + lo_result['gates'] + hi_result['gates'],
                'wire': f'MUX({var}, {hi_result["wire"]}, {lo_result["wire"]})'
            }

        cache[id(node)] = result
        return result

    return _convert(f.node)


def bdd_to_xor_gates(f, cache=None):
    """
    Convert BDD to gates using XOR decomposition.
    f = (x & (f_hi XOR f_lo)) XOR f_lo

    3 gates per node: AND, XOR, XOR
    """
    if cache is None:
        cache = {}

    def _convert(node):
        if id(node) in cache:
            return cache[id(node)]

        if node is BDDNODEZERO:
            return {'gates': 0, 'wire': 'ZERO'}
        if node is BDDNODEONE:
            return {'gates': 0, 'wire': 'ONE'}

        var = str(node.root)
        lo_result = _convert(node.lo)
        hi_result = _convert(node.hi)

        # Special cases
        if node.lo is BDDNODEZERO and node.hi is BDDNODEONE:
            result = {'gates': 0, 'wire': var}
        elif node.lo is BDDNODEONE and node.hi is BDDNODEZERO:
            result = {'gates': 1, 'wire': f'NOT({var})'}
        elif node.lo is node.hi:
            result = lo_result
        else:
            # f = (x & (hi XOR lo)) XOR lo = 3 gates
            result = {
                'gates': 3 + lo_result['gates'] + hi_result['gates'],
                'wire': f'XOR(AND({var}, XOR({hi_result["wire"]}, {lo_result["wire"]})), {lo_result["wire"]})'
            }

        cache[id(node)] = result
        return result

    return _convert(f.node)


def analyze_reed_muller(bdds, a_vars, b_vars):
    """
    Analyze XOR/AND (Reed-Muller) representation.
    Try to express each output as XOR of AND terms.
    """
    print("\nReed-Muller Analysis (XOR of ANDs):")

    for i, f in enumerate(bdds):
        # Convert to expression and try to identify XOR structure
        try:
            e = bdd2expr(f)
            expr_str = str(e)

            # Count unique variable combinations
            # This is a rough proxy for Reed-Muller complexity
            print(f"  out[{i}]: Expression length={len(expr_str)}")
        except:
            print(f"  out[{i}]: Could not analyze")


def analyze_cofactors(bdds, a_vars, b_vars):
    """Analyze cofactors w.r.t. sign bits (a0, b0)."""
    print("\nCofactor Analysis (w.r.t. sign bits a0, b0):")

    for i, f in enumerate(bdds):
        # Cofactors w.r.t. a0
        f_a0_0 = f.restrict({a_vars[0]: 0})
        f_a0_1 = f.restrict({a_vars[0]: 1})

        # Cofactors w.r.t. b0
        f_b0_0 = f.restrict({b_vars[0]: 0})
        f_b0_1 = f.restrict({b_vars[0]: 1})

        # All 4 combinations
        f_00 = f.restrict({a_vars[0]: 0, b_vars[0]: 0})
        f_01 = f.restrict({a_vars[0]: 0, b_vars[0]: 1})
        f_10 = f.restrict({a_vars[0]: 1, b_vars[0]: 0})
        f_11 = f.restrict({a_vars[0]: 1, b_vars[0]: 1})

        # Check relationships
        # For sign bit: out_sign = a0 XOR b0 (if magnitudes positive)
        # Check if f_01 == f_10 (symmetric)
        sym = f_01.equivalent(f_10)
        # Check if f_00 == f_11 (opposite quadrants equal)
        opp = f_00.equivalent(f_11)

        print(f"  out[{i}]: f(a0=0,b0=1) == f(a0=1,b0=0): {sym}, f(0,0) == f(1,1): {opp}")


def extract_circuit_from_bdd_shared(bdds):
    """
    Extract circuit with maximal sharing between all outputs.
    Returns estimated gate count.
    """
    # Build shared cache across all BDDs
    cache = {}
    total_gates = 0

    print("\nShared Circuit Extraction (Shannon/MUX):")
    for i, f in enumerate(bdds):
        result = bdd_to_shannon_gates(f, cache)
        print(f"  out[{i}]: {result['gates']} gates (incremental)")
        total_gates = max(len(cache), total_gates)

    # Count unique non-terminal nodes in cache
    unique_nodes = sum(1 for r in cache.values() if r['gates'] > 0 or r['wire'] not in ('ZERO', 'ONE'))
    print(f"  Total unique computations: {len(cache)}")

    # XOR-based extraction
    cache_xor = {}
    print("\nShared Circuit Extraction (XOR-based):")
    for i, f in enumerate(bdds):
        result = bdd_to_xor_gates(f, cache_xor)
        print(f"  out[{i}]: {result['gates']} gates (incremental)")

    print(f"  Total unique computations (XOR): {len(cache_xor)}")


def try_functional_decomposition(bdds, a_vars, b_vars):
    """
    Try functional decomposition: find intermediate functions
    that can be shared across outputs.
    """
    print("\nFunctional Decomposition Analysis:")

    # Compute all possible 2-input combinations
    all_vars = a_vars + b_vars

    # Check for common sub-BDDs across outputs
    node_ids = defaultdict(list)
    for i, f in enumerate(bdds):
        nodes = traverse_bdd(f)
        for nid, info in nodes.items():
            if info['type'] == 'INTERNAL':
                node_ids[nid].append(i)

    # Find nodes shared across multiple outputs
    shared_nodes = {nid: outputs for nid, outputs in node_ids.items()
                    if len(outputs) > 1}

    print(f"  Total shared BDD nodes: {len(shared_nodes)}")
    sharing_dist = defaultdict(int)
    for outputs in shared_nodes.values():
        sharing_dist[len(outputs)] += 1

    print("  Sharing distribution:")
    for n_outputs, count in sorted(sharing_dist.items(), reverse=True):
        print(f"    Shared by {n_outputs} outputs: {count} nodes")


def main():
    print("Enhanced BDD-based Synthesis for FP4 x FP4 Multiplier")
    print("=" * 60)

    bdds, a, b = build_espresso_style_bdds()

    # Basic statistics
    print("\nBDD Node Counts (per output):")
    total = 0
    for i, f in enumerate(bdds):
        nodes = traverse_bdd(f)
        internal = sum(1 for n in nodes.values() if n['type'] == 'INTERNAL')
        print(f"  out[{i}]: {internal} internal nodes")
        total += internal

    shared_count, var_influence = count_shared_nodes_detailed(bdds)
    print(f"\nShared BDD (all outputs): {shared_count} internal nodes")

    print("\nVariable decision frequency:")
    for var, count in sorted(var_influence.items(), key=lambda x: -x[1]):
        print(f"  {var}: {count} decision nodes")

    # Gate estimates
    print("\n" + "=" * 60)
    print("GATE ESTIMATES FROM BDD")
    print("=" * 60)

    print("\nDirect Shannon Decomposition (not shared):")
    total_shannon = 0
    total_xor = 0
    for i, f in enumerate(bdds):
        sh = bdd_to_shannon_gates(f, cache={})
        xr = bdd_to_xor_gates(f, cache={})
        print(f"  out[{i}]: Shannon={sh['gates']}, XOR={xr['gates']}")
        total_shannon += sh['gates']
        total_xor += xr['gates']

    print(f"\n  Total (not shared): Shannon={total_shannon}, XOR={total_xor}")

    extract_circuit_from_bdd_shared(bdds)

    # Structural analysis
    print("\n" + "=" * 60)
    print("STRUCTURAL ANALYSIS")
    print("=" * 60)

    analyze_cofactors(bdds, a, b)
    try_functional_decomposition(bdds, a, b)

    # Lower bound analysis
    print("\n" + "=" * 60)
    print("LOWER BOUND ANALYSIS")
    print("=" * 60)

    print(f"""
Summary:
- Shared BDD has {shared_count} internal nodes
- Each node requires 2-4 gates in Shannon decomposition
- Each node requires 1-3 gates in XOR decomposition
- Theoretical minimum from BDD: ~{shared_count} gates (best case)
- Realistic estimate: {shared_count * 2} - {shared_count * 3} gates

Current best circuit: 82 gates
BDD suggests this is close to optimal for this function class.
""")

    # Try to find algebraic structure
    print("=" * 60)
    print("ALGEBRAIC STRUCTURE SEARCH")
    print("=" * 60)

    # Check XOR relationships between outputs
    print("\nXOR relationships between consecutive outputs:")
    for i in range(8):
        xor_bdd = bdds[i] ^ bdds[i+1]
        nodes = traverse_bdd(xor_bdd)
        internal = sum(1 for n in nodes.values() if n['type'] == 'INTERNAL')
        print(f"  out[{i}] XOR out[{i+1}]: {internal} nodes")

    # Check if any output is a simple function of others
    print("\nOutput dependency check:")
    for i in range(9):
        for j in range(i+1, 9):
            if bdds[i].equivalent(bdds[j]):
                print(f"  out[{i}] == out[{j}]")
            if bdds[i].equivalent(~bdds[j]):
                print(f"  out[{i}] == ~out[{j}]")


if __name__ == "__main__":
    main()
