"""
SA with neutral perturbations:
  1. Apply a random neutral mutation (replace a gate with an equivalent
     expression — same care-set bitvector, possibly different structure).
  2. Run greedy resub from the new netlist.
  3. If the result is smaller than current best, keep it.

Many random restarts. Track best discovered netlist persistently.
"""

from __future__ import annotations
import sys, os, time, json, random, copy
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sa_search import (build_82, simulate, is_correct, compact, ALL_ONE,
                       N_IN, NOT_OP, AND_OP, OR_OP, XOR_OP, CONST0, CONST1, BUF,
                       OP_NAMES, CARE)


def all_replacements(gates, gi, base_vals):
    target = base_vals[N_IN + gi]
    n_avail = N_IN + gi
    out = []
    if target == 0: out.append((CONST0, 0, 0))
    if target == ALL_ONE: out.append((CONST1, 0, 0))
    for k in range(n_avail):
        if base_vals[k] == target: out.append((BUF, k, 0))
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


def best_single_pass(gates, out_nodes):
    """Best-improvement single-gate rewrite."""
    n = len(gates)
    base_vals = simulate(gates)
    best_save = 0
    best = None
    order = list(range(n))
    random.shuffle(order)
    for gi in order:
        cur = gates[gi]
        cands = all_replacements(gates, gi, base_vals)
        random.shuffle(cands)
        for (op, i, j) in cands:
            if op == cur[0] and i == cur[1] and j == cur[2]:
                continue
            ng = [list(g) for g in gates]
            ng[gi] = [op, i, j]
            if not is_correct(ng, out_nodes):
                continue
            cg, co = compact(ng, out_nodes)
            saved = n - len(cg)
            if saved > best_save:
                best_save = saved
                best = (cg, co, gi, op, i, j, saved, cur)
                if saved >= 1:
                    return best
    return best


def greedy_descend(gates, out_nodes, max_iter=60):
    """Run single-pass best-improvement until stuck."""
    log = []
    for _ in range(max_iter):
        before = len(gates)
        res = best_single_pass(gates, out_nodes)
        if res is None or before - len(res[0]) <= 0:
            return gates, out_nodes, log
        gates, out_nodes = res[0], res[1]
        log.append((before, len(gates)))
        assert is_correct(gates, out_nodes)
    return gates, out_nodes, log


def random_neutral_mutation(gates, out_nodes):
    """Pick a random gate, replace with a different expression of the same
    care-set bitvector. Returns mutated (gates, outs) or None if no neutral
    move available for the chosen gate."""
    n = len(gates)
    base_vals = simulate(gates)
    order = list(range(n))
    random.shuffle(order)
    for gi in order:
        cur = gates[gi]
        cands = all_replacements(gates, gi, base_vals)
        # Filter to candidates that are DIFFERENT from current op
        cands = [c for c in cands
                 if not (c[0] == cur[0] and c[1] == cur[1] and c[2] == cur[2])]
        if not cands:
            continue
        op, i, j = random.choice(cands)
        ng = [list(g) for g in gates]
        ng[gi] = [op, i, j]
        if is_correct(ng, out_nodes):
            return ng, list(out_nodes)
    return None


def load_best():
    """Load the smallest known netlist from any *_result_*gates.json file."""
    here = os.path.dirname(os.path.abspath(__file__))
    candidates = []
    for fn in os.listdir(here):
        if fn.endswith("gates.json") and ("resub" in fn or "sa_" in fn or "perturb" in fn):
            try:
                with open(os.path.join(here, fn)) as f:
                    d = json.load(f)
                candidates.append((d["final_count"], fn, d))
            except Exception:
                continue
    candidates.sort()
    if not candidates:
        gates, outs = build_82()
        return gates, outs, 82
    n, fn, d = candidates[0]
    print(f"Loaded {fn}: {n} gates")
    return [list(g) for g in d["gates"]], list(d["outs"]), n


def run(time_limit=300, perturbs_per_attempt=1):
    gates, outs, best_count = load_best()
    assert is_correct(gates, outs)
    best_gates, best_outs = [list(g) for g in gates], list(outs)
    print(f"Start best: {best_count} gates")

    t0 = time.time()
    attempts = 0
    accepted = 0
    while time.time() - t0 < time_limit:
        attempts += 1
        # 1. Apply k neutral perturbations
        cur_gates = [list(g) for g in best_gates]
        cur_outs = list(best_outs)
        for _ in range(perturbs_per_attempt):
            mut = random_neutral_mutation(cur_gates, cur_outs)
            if mut is not None:
                cur_gates, cur_outs = mut
        # 2. Greedy descend
        new_gates, new_outs, log = greedy_descend(cur_gates, cur_outs)
        new_count = len(new_gates)
        if new_count < best_count:
            best_count = new_count
            best_gates = [list(g) for g in new_gates]
            best_outs = list(new_outs)
            accepted += 1
            print(f"[attempt {attempts}] NEW BEST: {best_count} gates "
                  f"(elapsed {time.time()-t0:.1f}s, log {log})", flush=True)
            # Save immediately
            out_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                    f"perturb_result_{best_count}gates.json")
            with open(out_path, "w") as f:
                json.dump({"gates": best_gates, "outs": best_outs,
                           "final_count": best_count, "elapsed_sec": time.time()-t0,
                           "attempts": attempts}, f, indent=2)
        elif attempts % 50 == 0:
            print(f"[attempt {attempts}] still {best_count}, elapsed {time.time()-t0:.1f}s",
                  flush=True)
    return best_gates, best_outs, best_count, attempts


if __name__ == "__main__":
    seed_arg = int(sys.argv[1]) if len(sys.argv) > 1 else 12345
    time_limit = int(sys.argv[2]) if len(sys.argv) > 2 else 240
    perturbs = int(sys.argv[3]) if len(sys.argv) > 3 else 2
    random.seed(seed_arg)
    print(f"Seed={seed_arg}, time_limit={time_limit}s, perturbs/attempt={perturbs}")
    g, o, n, a = run(time_limit, perturbs)
    print(f"\nFinal: {n} gates after {a} attempts")
