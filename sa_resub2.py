"""
Stronger resubstitution with:
  - best-improvement search (try ALL gates, take biggest saving)
  - multi-pass with random gate-order restarts
  - depth-2 substitutions (replace one gate with a 2-gate expression IF the
    transitive DCE saves >= 2 gates).

Operates on the 81-gate result from sa_resub.py.
"""

from __future__ import annotations
import sys, os, time, json, random, copy
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sa_search import (build_82, simulate, is_correct, compact, ALL_ONE,
                       N_IN, NOT_OP, AND_OP, OR_OP, XOR_OP, CONST0, CONST1, BUF,
                       OP_NAMES, CARE)


def all_replacements(gates, gi, base_vals):
    """Single-gate replacements: const, BUF, NOT, or 2-input op over earlier nodes."""
    target = base_vals[N_IN + gi]
    n_avail = N_IN + gi
    out = []

    if target == 0:    out.append((CONST0, 0, 0))
    if target == ALL_ONE: out.append((CONST1, 0, 0))

    for k in range(n_avail):
        if base_vals[k] == target:           out.append((BUF, k, 0))
        if (ALL_ONE ^ base_vals[k]) == target: out.append((NOT_OP, k, 0))

    vals = [base_vals[k] for k in range(n_avail)]
    for i in range(n_avail):
        vi = vals[i]
        for j in range(i+1, n_avail):
            vj = vals[j]
            if (vi & vj) == target: out.append((AND_OP, i, j))
            if (vi | vj) == target: out.append((OR_OP, i, j))
            if (vi ^ vj) == target: out.append((XOR_OP, i, j))
    return out


def try_global_pass(gates, out_nodes, randomize_order=False):
    """Best-improvement search: scan ALL gates, find biggest single-rewrite saving."""
    n = len(gates)
    base_vals = simulate(gates)
    base_size = n

    order = list(range(n))
    if randomize_order:
        random.shuffle(order)

    best = None
    best_save = 0

    for gi in order:
        cur = gates[gi]
        candidates = all_replacements(gates, gi, base_vals)
        for (op, i, j) in candidates:
            if op == cur[0] and i == cur[1] and j == cur[2]:
                continue
            new_gates = [list(g) for g in gates]
            new_gates[gi] = [op, i, j]
            if not is_correct(new_gates, out_nodes):
                continue
            cg, co = compact(new_gates, out_nodes)
            saved = base_size - len(cg)
            if saved > best_save:
                best_save = saved
                best = (cg, co, gi, op, i, j, saved, cur)
                if saved >= 2:
                    return best  # take big wins immediately

    return best


def two_gate_pass(gates, out_nodes):
    """For each pair of gates (g1, g2), try replacing both with new expressions
    such that total gates after DCE drops by >= 2.

    This is O(N^2 * |candidates|^2) — slow but tractable at N~80.
    To make it feasible we restrict to: rewrite g1 to one of its top-3 single
    candidates, then rewrite g2 to its best candidate post-rewrite.
    """
    n = len(gates)
    base_vals = simulate(gates)
    base_size = n

    # Pre-compute single-gate candidates (cheap)
    cand_per_gate = {}
    for gi in range(n):
        cand_per_gate[gi] = all_replacements(gates, gi, base_vals)

    best = None
    best_save = 0

    # Order gates by "least bitvector entropy" — gates whose value can be many
    # things are good leaders.
    gate_order = list(range(n))
    random.shuffle(gate_order)

    tried = 0
    for g1 in gate_order:
        # Try replacing g1 with each of its candidates (limit to first 6)
        for (op1, i1, j1) in cand_per_gate[g1][:6]:
            cur1 = gates[g1]
            if op1 == cur1[0] and i1 == cur1[1] and j1 == cur1[2]:
                continue
            ng = [list(g) for g in gates]
            ng[g1] = [op1, i1, j1]
            if not is_correct(ng, out_nodes):
                continue
            # Now try second-pass single rewrite on the new netlist
            # Compact first, then re-run single-pass
            cg, co = compact(ng, out_nodes)
            saved1 = base_size - len(cg)
            best2 = try_global_pass(cg, co, randomize_order=False)
            if best2 is not None:
                cg2, co2 = best2[0], best2[1]
                saved2 = len(cg) - len(cg2)
                total_save = saved1 + saved2
                if total_save > best_save:
                    best_save = total_save
                    best = (cg2, co2, total_save,
                            f"g{g1}→{OP_NAMES[op1]}({i1},{j1}) then "
                            f"g{best2[2]}→{OP_NAMES[best2[3]]}({best2[4]},{best2[5]})")
                    if total_save >= 2:
                        return best
            tried += 1
            if tried > 80:
                return best

    return best


def load_seed(path=None):
    if path is None:
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            "resub_result_81gates.json")
    if not os.path.exists(path):
        return None
    with open(path) as f:
        d = json.load(f)
    gates = [list(g) for g in d["gates"]]
    outs = list(d["outs"])
    return gates, outs


def run():
    seed = load_seed()
    if seed is None:
        gates, outs = build_82()
    else:
        gates, outs = seed
    assert is_correct(gates, outs), "Seed broken!"
    print(f"Seed: {len(gates)} gates")

    log = []
    iteration = 0
    t_total = time.time()

    while time.time() - t_total < 600:
        iteration += 1
        before = len(gates)

        # Try single-gate first (cheap)
        t0 = time.time()
        res = try_global_pass(gates, outs, randomize_order=True)
        dt = time.time() - t0
        if res and (before - len(res[0])) > 0:
            gates, outs = res[0], res[1]
            line = f"[iter {iteration}] {before}->{len(gates)} ({dt:.1f}s) [single]: g{res[2]} {OP_NAMES[res[3]]}({res[4]},{res[5]}) save {res[6]}"
            print(line, flush=True)
            log.append(line)
            assert is_correct(gates, outs)
            continue

        # Single-pass found nothing — try two-gate
        print(f"[iter {iteration}] single-pass exhausted at {before}, trying 2-gate...", flush=True)
        t0 = time.time()
        res2 = two_gate_pass(gates, outs)
        dt = time.time() - t0
        if res2 and (before - len(res2[0])) > 0:
            gates, outs = res2[0], res2[1]
            line = f"[iter {iteration}] {before}->{len(gates)} ({dt:.1f}s) [two-gate]: {res2[3]}"
            print(line, flush=True)
            log.append(line)
            assert is_correct(gates, outs)
            continue

        print(f"[iter {iteration}] No improvement at depth 1 or 2. Stuck at {before}.", flush=True)
        break

    return gates, outs, log


if __name__ == "__main__":
    t0 = time.time()
    gates, outs, log = run()
    final = len(gates)
    elapsed = time.time() - t0
    print(f"\nFinal: {final} gates in {elapsed:.1f}s")

    out_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            f"resub2_result_{final}gates.json")
    with open(out_path, "w") as f:
        json.dump({"gates": gates, "outs": outs, "log": log,
                   "final_count": final, "elapsed_sec": elapsed}, f, indent=2)
    print(f"Saved to {out_path}")
