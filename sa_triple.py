"""3-perturbation random sampling. With ~67 candidates per netlist,
67^3 = 300k triples — exhaustive infeasible. Random sampling instead."""

from __future__ import annotations
import sys, os, time, json, random
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sa_search import simulate, is_correct, compact, ALL_ONE
from sa_anneal import all_replacements, greedy_descend, load_best_path
from sa_pair import collect_perturbations, apply_perturb


def run(time_limit=600):
    gates, outs, best_count = load_best_path()
    print(f"Start: {best_count} gates")
    assert is_correct(gates, outs)

    perts = collect_perturbations(gates)
    print(f"|P_1| = {len(perts)}")

    t0 = time.time()
    tried = 0
    while time.time() - t0 < time_limit:
        # Sample 3 random perturbations
        triple = random.sample(perts, 3) if len(perts) >= 3 else random.choices(perts, k=3)
        # Apply in sequence
        cur = [list(g) for g in gates]
        ok = True
        for p in triple:
            cur = apply_perturb(cur, p)
            if not is_correct(cur, outs):
                ok = False
                break
        tried += 1
        if not ok: continue

        ng, no = greedy_descend(cur, outs)
        if len(ng) < best_count:
            print(f"[{tried}] BREAKTHROUGH: {best_count} -> {len(ng)}", flush=True)
            print(f"   triple: {triple}")
            best_count = len(ng)
            gates, outs = ng, no
            out_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                    f"triple_result_{best_count}gates.json")
            with open(out_path, "w") as f:
                json.dump({"gates": gates, "outs": outs,
                           "final_count": best_count, "elapsed_sec": time.time()-t0,
                           "tried": tried}, f, indent=2)
            perts = collect_perturbations(gates)
            print(f"  re-collected |P_1| = {len(perts)}")

        if tried % 500 == 0:
            print(f"  [{tried}] still {best_count}, t={time.time()-t0:.1f}s", flush=True)

    return best_count, tried


if __name__ == "__main__":
    seed = int(sys.argv[1]) if len(sys.argv) > 1 else 99
    tlim = int(sys.argv[2]) if len(sys.argv) > 2 else 600
    random.seed(seed)
    print(f"Seed={seed}, time_limit={tlim}s")
    best, tried = run(tlim)
    print(f"\nFinal: {best} gates after {tried} triples")
