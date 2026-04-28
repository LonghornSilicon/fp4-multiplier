"""
Don't-care-aware resubstitution search.

For each gate g in the netlist, enumerate every (op, i, j) where i,j are
existing nodes (with i,j < g to avoid cycles). If the new expression's
care-set bitvector matches g's output bitvector, replace g with it. After
replacement, run DCE — if total gate count drops, accept. This is the
classic 'mfs2/mfs3' idea but bit-parallel and exhaustive at depth 1.

We also try size-1 substitutions (replace g with NOT(k) or BUF(k) for any k).

Run:  python3 sa_resub.py
"""

from __future__ import annotations
import sys, os, time, json, copy
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Reuse the seed builder + simulator from sa_search.py
from sa_search import (build_82, simulate, is_correct, compact, ALL_ONE,
                       N_IN, NOT_OP, AND_OP, OR_OP, XOR_OP, CONST0, CONST1, BUF,
                       OP_NAMES, CARE)

def all_replacements(gates, gi, base_vals):
    """Generate (new_op, in0, in1) candidates that compute the same bitvector
    as gate gi, using only nodes with index < N_IN + gi."""
    target = base_vals[N_IN + gi]
    n_avail = N_IN + gi
    out = []

    # 0-input: constants
    if target == 0:    out.append((CONST0, 0, 0, 0))
    if target == ALL_ONE: out.append((CONST1, 0, 0, 0))

    # 1-input: BUF or NOT of any earlier node
    for k in range(n_avail):
        if base_vals[k] == target:
            out.append((BUF, k, 0, 0))
        if (ALL_ONE ^ base_vals[k]) == target:
            out.append((NOT_OP, k, 0, 0))

    # 2-input: AND / OR / XOR over pairs of earlier nodes
    # 2-input enumeration is O(n^2) - feasible at n~90
    vals = [base_vals[k] for k in range(n_avail)]
    for i in range(n_avail):
        vi = vals[i]
        for j in range(i+1, n_avail):
            vj = vals[j]
            if (vi & vj) == target: out.append((AND_OP, i, j, 0))
            if (vi | vj) == target: out.append((OR_OP, i, j, 0))
            if (vi ^ vj) == target: out.append((XOR_OP, i, j, 0))
    return out


def rewrite_gate(gates, out_nodes, gi, new_op, in0, in1):
    """Replace gate gi with (new_op, in0, in1). Returns new (gates, outs)."""
    new_gates = [list(g) for g in gates]
    new_gates[gi] = [new_op, in0, in1]
    return new_gates, list(out_nodes)


def search_one_pass(gates, out_nodes, log):
    """One full pass: try every gate × every replacement. If any gives a
    smaller circuit after DCE, accept and return new (gates, outs, msg)."""
    n = len(gates)
    base_vals = simulate(gates)
    base_size = n

    best_save = 0
    best = None

    for gi in range(n):
        cur_op = gates[gi][0]
        candidates = all_replacements(gates, gi, base_vals)
        for (op, i, j, _) in candidates:
            # Skip the no-op (replacing gate with itself)
            if op == cur_op and (i, j) == (gates[gi][1], gates[gi][2]):
                continue
            ng, no = rewrite_gate(gates, out_nodes, gi, op, i, j)
            if not is_correct(ng, no):
                continue
            cg, co = compact(ng, no)
            saved = base_size - len(cg)
            if saved > best_save:
                best_save = saved
                best = (cg, co, gi, op, i, j, saved)
                # Greedy: accept first improvement to make progress fast
                msg = (f"gate#{gi} ({OP_NAMES[cur_op]}({gates[gi][1]},{gates[gi][2]})) "
                       f"-> {OP_NAMES[op]}({i},{j}) saves {saved}")
                return cg, co, msg
    return None


def run():
    gates, outs = build_82()
    assert is_correct(gates, outs)
    print(f"Seed: {len(gates)} gates, 225/225")

    log = []
    iteration = 0
    while True:
        iteration += 1
        before = len(gates)
        t0 = time.time()
        res = search_one_pass(gates, outs, log)
        dt = time.time() - t0
        if res is None:
            print(f"[iter {iteration}] No improvement found in {dt:.1f}s. Stuck at {before}.")
            break
        gates, outs, msg = res
        after = len(gates)
        line = f"[iter {iteration}] {before} -> {after} ({dt:.1f}s): {msg}"
        print(line, flush=True)
        log.append(line)
        # sanity check
        assert is_correct(gates, outs), f"After mutation, circuit broken!"

    return gates, outs, log


if __name__ == "__main__":
    t0 = time.time()
    gates, outs, log = run()
    final = len(gates)
    elapsed = time.time() - t0
    print(f"\nFinal: {final} gates in {elapsed:.1f}s")

    out_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            f"resub_result_{final}gates.json")
    with open(out_path, "w") as f:
        json.dump({"gates": gates, "outs": outs, "log": log,
                   "final_count": final, "elapsed_sec": elapsed}, f, indent=2)
    print(f"Saved to {out_path}")
