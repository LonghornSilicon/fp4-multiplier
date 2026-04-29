"""
Algebraic re-derivation of the FP4xFP4 multiplier.

Plan:
  1. Compute the truth table for all 9 outputs under Longhorn's sigma.
  2. Compute the ANF (Reed-Muller) of each output.
  3. Take the union of monomials across all 9 outputs (each monomial is
     a product of input bits over GF(2)).
  4. Build a maximally-shared evaluation tree:
       - For each monomial of degree d, allocate d-1 AND gates, sharing
         intermediate products with other monomials.
       - For each output, XOR together its monomials (m-1 XORs each).
  5. Count gates and report.

This is structurally orthogonal to Longhorn's (2*lb + ma) decomposition.
The hope: if max-sharing AND-XOR synthesis from ANF is significantly
smaller than 63, we have an immediate sub-63 win. If it is larger, we
have evidence that the AND-XOR basis alone is insufficient and the
NOT/OR primitives Longhorn uses contribute essential compression.
"""
from __future__ import annotations
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from itertools import combinations
from collections import defaultdict, Counter
from analysis.lower_bound import build_funcs_under_sigma, compute_anf


VAR_NAMES = ['a0', 'a1', 'a2', 'a3', 'b0', 'b1', 'b2', 'b3']


def mono_str(m):
    if not m:
        return "1"
    return "*".join(VAR_NAMES[i] for i in sorted(m))


def greedy_shared_and_synthesis(monomials):
    """Greedy: build all monomials with max sharing.
    Strategy: build by ascending degree. For each monomial m, find the best
    "parent" — an already-built monomial that is a subset of m of maximum
    size, then chain ANDs from parent to m one variable at a time.

    Returns (and_gates, anf_eval_dict) where:
      and_gates is a list of (out_name, kind, in1, in2). kind always "AND".
      anf_eval_dict[mono] = wire_name carrying that monomial's value.
    """
    sorted_monos = sorted(monomials, key=lambda m: (len(m), tuple(sorted(m))))
    eval_wires = {frozenset(): "ONE"}  # constant 1
    for i, name in enumerate(VAR_NAMES):
        eval_wires[frozenset({i})] = name
    and_gates = []
    next_id = 0
    for m in sorted_monos:
        if m in eval_wires:
            continue
        # Find best parent: largest already-evaluated proper subset of m.
        parent = max(
            (s for s in eval_wires if s.issubset(m) and s != m),
            key=len, default=frozenset()
        )
        # Chain ANDs from parent to m one variable at a time.
        cur_set = parent
        cur_wire = eval_wires[parent]
        remaining = sorted(m - parent)
        for v in remaining:
            new_set = cur_set | {v}
            if new_set in eval_wires:
                cur_set = new_set
                cur_wire = eval_wires[new_set]
                continue
            new_wire = f"p{next_id}"
            next_id += 1
            and_gates.append((new_wire, "AND", cur_wire, VAR_NAMES[v]))
            eval_wires[new_set] = new_wire
            cur_set = new_set
            cur_wire = new_wire
    return and_gates, eval_wires


def xor_tree(wires, prefix="x"):
    """Build a balanced XOR tree over the given list of wire names.
    Returns (gates, root_wire). gates: list of (out, "XOR", a, b)."""
    if not wires:
        return [], "ZERO"
    if len(wires) == 1:
        return [], wires[0]
    gates = []
    next_id = [0]

    def gen():
        return f"{prefix}{next_id[0]}"

    cur = list(wires)
    while len(cur) > 1:
        nxt = []
        for i in range(0, len(cur), 2):
            if i + 1 == len(cur):
                nxt.append(cur[i])
            else:
                w = gen()
                next_id[0] += 1
                gates.append((w, "XOR", cur[i], cur[i + 1]))
                nxt.append(w)
        cur = nxt
    return gates, cur[0]


def main():
    funcs = build_funcs_under_sigma()
    anfs = [compute_anf(f) for f in funcs]

    print("# Algebraic synthesis report\n")

    # Stats
    union = set()
    for a in anfs:
        union |= a
    print(f"Distinct monomials across all 9 outputs: {len(union)}")
    print(f"Total monomial count (sum over outputs):  {sum(len(a) for a in anfs)}")
    print(f"Average sharing factor: {sum(len(a) for a in anfs)/max(1,len(union)):.2f}\n")

    deg_dist = Counter(len(m) for m in union)
    print("Monomial degree distribution (union):")
    for d in sorted(deg_dist):
        print(f"  degree {d}: {deg_dist[d]}")

    # Synthesis
    and_gates, eval_wires = greedy_shared_and_synthesis(union)
    n_and = len(and_gates)
    print(f"\nAND2 gates needed to build all distinct monomials (greedy chain sharing): {n_and}")

    # XOR trees per output
    n_xor = 0
    n_constant_outputs = 0
    for i, anf in enumerate(anfs):
        if not anf:
            n_constant_outputs += 1
            continue
        wires = [eval_wires[m] for m in anf]
        # Constant 1 contribution: if "ONE" appears, it's a constant flip.
        # Build XOR tree.
        gates, root = xor_tree(wires, prefix=f"y{i}_x")
        n_xor += len(gates)

    print(f"XOR2 gates (sum of per-output XOR trees): {n_xor}")
    print(f"Constant outputs (always 0): {n_constant_outputs}")
    print(f"\nTotal gates from AND-XOR-only synthesis: {n_and + n_xor}")
    print()
    print("(Note: this assumes pure AND/XOR/NOT basis; OR2 is not used.")
    print(" Some monomials may include the constant 1 (contributing to a")
    print(" final NOT or constant XOR), which would add up to 9 NOT gates.)")
    print()
    print("Comparison: our 63-gate solution = 24 AND + 22 XOR + 12 OR + 5 NOT.")
    print()
    if n_and + n_xor < 63:
        print(f"*** {n_and + n_xor} < 63: PURE AND-XOR ALREADY BEATS THE NETLIST ***")
    else:
        print(f"AND-XOR baseline ({n_and + n_xor}) >= 63 -> Longhorn's use of OR/NOT")
        print("encodes essential algebraic shortcuts the pure ANF synthesis misses.")


if __name__ == "__main__":
    main()
