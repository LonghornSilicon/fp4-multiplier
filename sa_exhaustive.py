"""
Exhaustive 1-perturbation search:
  For every (gate, candidate-rewrite) pair in the netlist, apply the rewrite,
  then run greedy descent. If the result is smaller than the current best,
  accept and recurse. This is more systematic than random SA.
"""

from __future__ import annotations
import sys, os, time, json, random
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sa_search import (build_82, simulate, is_correct, compact, ALL_ONE,
                       N_IN, NOT_OP, AND_OP, OR_OP, XOR_OP, CONST0, CONST1, BUF,
                       OP_NAMES)
from sa_anneal import all_replacements, best_single_pass, greedy_descend, load_best_path


def exhaustive_pass(gates, out_nodes, time_limit=300, callback=None):
    """For every (gate, candidate) rewrite, try it then descend."""
    base_count = len(gates)
    base_vals = simulate(gates)
    n = len(gates)

    # Collect all (gi, op, i, j) candidates that are NEUTRAL
    # (preserve correctness on care set).
    perturbations = []
    for gi in range(n):
        cur = gates[gi]
        cands = all_replacements(gates, gi, base_vals)
        for c in cands:
            if c == (cur[0], cur[1], cur[2]): continue
            perturbations.append((gi, c[0], c[1], c[2]))

    print(f"Total neutral 1-perturbations: {len(perturbations)}")
    random.shuffle(perturbations)

    t0 = time.time()
    for idx, (gi, op, i, j) in enumerate(perturbations):
        if time.time() - t0 > time_limit:
            print(f"Time limit hit after {idx} perturbations")
            break
        ng = [list(g) for g in gates]
        ng[gi] = [op, i, j]
        if not is_correct(ng, out_nodes):
            continue
        new_g, new_o = greedy_descend(ng, out_nodes)
        if len(new_g) < base_count:
            print(f"[{idx}/{len(perturbations)}] BREAKTHROUGH: {base_count} -> "
                  f"{len(new_g)} via g{gi} -> {OP_NAMES[op]}({i},{j})")
            if callback: callback(new_g, new_o)
            return new_g, new_o
        if idx % 100 == 0:
            print(f"  [{idx}/{len(perturbations)}] no improvement, t={time.time()-t0:.1f}s",
                  flush=True)
    return None


def run(time_limit=600):
    gates, outs, best_count = load_best_path()
    print(f"Start: {best_count} gates")
    assert is_correct(gates, outs)

    iteration = 0
    t0 = time.time()
    while time.time() - t0 < time_limit:
        iteration += 1
        before = len(gates)
        print(f"\n[iter {iteration}] starting from {before} gates")
        result = exhaustive_pass(gates, outs, time_limit=time_limit-(time.time()-t0))
        if result is None:
            print(f"[iter {iteration}] No 1-perturb breakthrough at {before}.")
            break
        gates, outs = result
        # Save
        out_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                f"exhaustive_result_{len(gates)}gates.json")
        with open(out_path, "w") as f:
            json.dump({"gates": gates, "outs": outs,
                       "final_count": len(gates), "elapsed_sec": time.time()-t0,
                       "iteration": iteration}, f, indent=2)
        print(f"Saved {out_path}")

    return gates, outs


if __name__ == "__main__":
    seed = int(sys.argv[1]) if len(sys.argv) > 1 else 42
    tlim = int(sys.argv[2]) if len(sys.argv) > 2 else 600
    random.seed(seed)
    g, o = run(tlim)
    print(f"\nFinal: {len(g)} gates")
