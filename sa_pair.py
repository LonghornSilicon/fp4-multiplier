"""
2-perturbation exhaustive search.

For each pair of (gate, candidate-rewrite) perturbations, apply both,
then run greedy descent. With ~67 candidate single rewrites at 81 gates,
that's ~4500 pairs, each followed by descent.

Also includes "structural" moves:
  - Swap inputs of a gate with NOT(input).
  - Replace a gate (op, i, j) with NOT(op, NOT(i), j) or similar via
    De Morgan identities — these expand by 1-2 gates but enable deeper
    sharing.
"""

from __future__ import annotations
import sys, os, time, json, random, itertools
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sa_search import (build_82, simulate, is_correct, compact, ALL_ONE,
                       N_IN, NOT_OP, AND_OP, OR_OP, XOR_OP, CONST0, CONST1, BUF,
                       OP_NAMES)
from sa_anneal import all_replacements, greedy_descend, load_best_path


def collect_perturbations(gates, base_vals=None):
    """List all neutral 1-gate rewrites for this netlist."""
    if base_vals is None:
        base_vals = simulate(gates)
    perturbations = []
    for gi in range(len(gates)):
        cur = gates[gi]
        cands = all_replacements(gates, gi, base_vals)
        for c in cands:
            if c == (cur[0], cur[1], cur[2]): continue
            perturbations.append((gi, c[0], c[1], c[2]))
    return perturbations


def apply_perturb(gates, p):
    gi, op, i, j = p
    ng = [list(g) for g in gates]
    ng[gi] = [op, i, j]
    return ng


def run_pair(time_limit=900):
    gates, outs, best_count = load_best_path()
    print(f"Start: {best_count} gates")
    assert is_correct(gates, outs)

    t0 = time.time()
    perts = collect_perturbations(gates)
    print(f"|P_1| = {len(perts)}")

    # Try every pair (p1, p2)
    pairs = list(itertools.product(perts, perts))
    random.shuffle(pairs)
    print(f"|P_2 pairs| = {len(pairs)}")

    tried = 0
    for (p1, p2) in pairs:
        if time.time() - t0 > time_limit:
            print(f"Time limit at {tried} pairs")
            break
        tried += 1
        # Apply p1
        g1 = apply_perturb(gates, p1)
        if not is_correct(g1, outs): continue
        # Apply p2 on top of p1 — same gate index validation
        g2 = apply_perturb(g1, p2)
        if not is_correct(g2, outs): continue
        # Greedy descend
        ng, no = greedy_descend(g2, outs)
        if len(ng) < best_count:
            print(f"[{tried}] BREAKTHROUGH: {best_count} -> {len(ng)} via "
                  f"p1=({p1}) p2=({p2})", flush=True)
            best_count = len(ng)
            gates, outs = ng, no
            out_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                    f"pair_result_{best_count}gates.json")
            with open(out_path, "w") as f:
                json.dump({"gates": gates, "outs": outs,
                           "final_count": best_count, "elapsed_sec": time.time()-t0,
                           "tried": tried}, f, indent=2)
            # Re-collect perturbations and continue
            perts = collect_perturbations(gates)
            pairs = list(itertools.product(perts, perts))
            random.shuffle(pairs)
            continue
        if tried % 200 == 0:
            print(f"  [{tried}] still {best_count}, t={time.time()-t0:.1f}s",
                  flush=True)
    return best_count, tried


if __name__ == "__main__":
    seed = int(sys.argv[1]) if len(sys.argv) > 1 else 17
    tlim = int(sys.argv[2]) if len(sys.argv) > 2 else 900
    random.seed(seed)
    print(f"Seed={seed}, time_limit={tlim}s")
    best, tried = run_pair(tlim)
    print(f"\nFinal: {best} gates after {tried} pairs")
