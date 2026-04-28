"""
True simulated annealing — accepts uphill moves with probability exp(-dE/T).

Mutations:
  - 'rewrite': replace a gate with a different equivalent expression (neutral).
  - 'gate_input_swap': change one input of a gate to a different node, accept
    if downstream effect is still correct (this may BREAK correctness — count
    Hamming distance and accept by SA).
  - 'delete_attempt': try to delete a random gate by rewiring fanouts to a
    nearby node (greedy 1-gate elimination).

After every move (or every K moves), run greedy descent. Track best.
"""

from __future__ import annotations
import sys, os, time, json, random, math
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sa_search import (build_82, simulate, is_correct, compact, ALL_ONE,
                       N_IN, NOT_OP, AND_OP, OR_OP, XOR_OP, CONST0, CONST1, BUF,
                       OP_NAMES, CARE)


def all_replacements(gates, gi, base_vals, target=None):
    if target is None:
        target = base_vals[N_IN + gi]
    n_avail = N_IN + gi
    out = []
    if target == 0: out.append((CONST0, 0, 0))
    if target == ALL_ONE: out.append((CONST1, 0, 0))
    for k in range(n_avail):
        if base_vals[k] == target: out.append((BUF, k, 0))
        if (ALL_ONE ^ base_vals[k]) == target: out.append((NOT_OP, k, 0))
    vals_arr = [base_vals[k] for k in range(n_avail)]
    for i in range(n_avail):
        vi = vals_arr[i]
        for j in range(i+1, n_avail):
            vj = vals_arr[j]
            if (vi & vj) == target: out.append((AND_OP, i, j))
            if (vi | vj) == target: out.append((OR_OP, i, j))
            if (vi ^ vj) == target: out.append((XOR_OP, i, j))
    return out


def best_single_pass(gates, out_nodes, full=True):
    """Best-improvement single-gate rewrite. Returns improved netlist or None."""
    n = len(gates)
    base_vals = simulate(gates)
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
            if len(cg) < n:
                return cg, co
    return None


def greedy_descend(gates, out_nodes, max_iter=40):
    for _ in range(max_iter):
        before = len(gates)
        res = best_single_pass(gates, out_nodes)
        if res is None or len(res[0]) >= before:
            break
        gates, out_nodes = res
    return gates, out_nodes


def random_neutral(gates, out_nodes):
    n = len(gates)
    base_vals = simulate(gates)
    for _ in range(20):
        gi = random.randrange(n)
        cur = gates[gi]
        cands = all_replacements(gates, gi, base_vals)
        cands = [c for c in cands if c != (cur[0], cur[1], cur[2])]
        if not cands:
            continue
        op, i, j = random.choice(cands)
        ng = [list(g) for g in gates]
        ng[gi] = [op, i, j]
        if is_correct(ng, out_nodes):
            return ng, list(out_nodes)
    return None


def two_step_neutral(gates, out_nodes):
    """Apply 2 neutral mutations in a row."""
    cur_g, cur_o = [list(g) for g in gates], list(out_nodes)
    for _ in range(2):
        m = random_neutral(cur_g, cur_o)
        if m is not None:
            cur_g, cur_o = m
    return cur_g, cur_o


def load_best_path():
    here = os.path.dirname(os.path.abspath(__file__))
    candidates = []
    for fn in os.listdir(here):
        if fn.endswith("gates.json"):
            try:
                with open(os.path.join(here, fn)) as f:
                    d = json.load(f)
                candidates.append((d["final_count"], fn, d))
            except Exception: pass
    candidates.sort()
    if not candidates:
        gates, outs = build_82()
        return gates, outs, 82
    return [list(g) for g in candidates[0][2]["gates"]], list(candidates[0][2]["outs"]), candidates[0][0]


def run(time_limit=300, perturbs_min=2, perturbs_max=6):
    gates, outs, best_count = load_best_path()
    assert is_correct(gates, outs)
    print(f"Start: {best_count} gates")

    t0 = time.time()
    attempts = 0
    new_bests = 0
    while time.time() - t0 < time_limit:
        attempts += 1
        # Variable-strength perturbation
        k_perturb = random.randint(perturbs_min, perturbs_max)
        cur_g, cur_o = [list(g) for g in gates], list(outs)
        for _ in range(k_perturb):
            m = random_neutral(cur_g, cur_o)
            if m is not None:
                cur_g, cur_o = m
        # Greedy descend
        ng, no = greedy_descend(cur_g, cur_o)
        if len(ng) < best_count:
            best_count = len(ng)
            gates, outs = [list(g) for g in ng], list(no)
            new_bests += 1
            print(f"[attempt {attempts}, k={k_perturb}] NEW BEST: {best_count} "
                  f"(elapsed {time.time()-t0:.1f}s)", flush=True)
            out_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                    f"anneal_result_{best_count}gates.json")
            with open(out_path, "w") as f:
                json.dump({"gates": gates, "outs": outs,
                           "final_count": best_count, "elapsed_sec": time.time()-t0,
                           "attempts": attempts}, f, indent=2)
        elif attempts % 100 == 0:
            print(f"[attempt {attempts}] still {best_count}, "
                  f"elapsed {time.time()-t0:.1f}s", flush=True)
    return best_count, attempts, new_bests


if __name__ == "__main__":
    seed = int(sys.argv[1]) if len(sys.argv) > 1 else random.randint(1, 1000000)
    tlim = int(sys.argv[2]) if len(sys.argv) > 2 else 300
    pmin = int(sys.argv[3]) if len(sys.argv) > 3 else 3
    pmax = int(sys.argv[4]) if len(sys.argv) > 4 else 8
    random.seed(seed)
    print(f"Seed={seed}, time_limit={tlim}s, perturbs ∈ [{pmin}, {pmax}]")
    best, att, nb = run(tlim, pmin, pmax)
    print(f"\nFinal: {best} gates, {nb} new bests in {att} attempts")
