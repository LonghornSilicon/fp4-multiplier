"""
Experiment A2: Apply TWO XOR re-associations simultaneously, then run eSLIM.

Single-perturb (exp_a_parallel.py) gives the same eSLIM convergence basin
patterns we already see at the canonical. Multi-perturb might land in basins
unreachable by either single move, akin to the 65→64 unlock that needed a
single specific perturbation (w_75) plus eSLIM. At 64, we may need a *pair*.

This driver:
  1. Picks all C(N, 2) pairs of XOR-XOR locations (N=12 → 66 pairs).
  2. For each pair, applies both perturbations sequentially and writes a
     perturbed BLIF.
  3. Runs eSLIM with selected (size, seed) settings on each.
  4. Reports any sub-64 contest result.
"""
from __future__ import annotations
import argparse, sys, os, time
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor, as_completed
from itertools import combinations

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from exp_a_xor_reassoc import (
    parse_gate_blif, write_gate_blif, find_xor_xor_locations,
    reassoc_at, flatten_blif, run_eslim, translate_to_gates,
    LONGHORN, ESLIM, WORK,
)

REPO = Path(__file__).resolve().parent.parent


def apply_two(gates, loc_a, loc_b):
    """Apply re-association at loc_a, then loc_b. The second perturbation's
    indices may need adjustment if the first changed gate indices."""
    g1 = reassoc_at(gates, *loc_a)
    # Re-find xor-xor locations in the perturbed netlist; loc_b's original
    # indices may be invalidated. Find the corresponding loc by output names.
    out_to_idx = {gg["out"]: i for i, gg in enumerate(g1)}

    # Original loc_b: (target_idx, pos, parent_idx) — translate via output names
    target_out = gates[loc_b[0]]["out"]
    parent_out = gates[loc_b[2]]["out"]
    if target_out not in out_to_idx or parent_out not in out_to_idx:
        return None  # second perturbation's gates were touched/removed
    new_target_idx = out_to_idx[target_out]
    new_parent_idx = out_to_idx[parent_out]
    # Verify it's still a valid XOR-XOR pattern at new positions
    target_g = g1[new_target_idx]
    parent_g = g1[new_parent_idx]
    if target_g["kind"] != "XOR" or parent_g["kind"] != "XOR":
        return None
    # Find which input of target points to parent
    new_pos = None
    for k, inp in enumerate(target_g["ins"]):
        if inp == parent_g["out"]:
            new_pos = k; break
    if new_pos is None:
        return None  # connection broken by first perturbation

    g2 = reassoc_at(g1, new_target_idx, new_pos, new_parent_idx)
    return g2


def _job(args_tuple):
    (pi, pj, size, seed, tb, flat_blif, in_names, out_names) = args_tuple
    out_eslim = WORK / f"par2_{pi:02d}_{pj:02d}_s{size}_seed{seed}_out.blif"
    t0 = time.time()
    res = run_eslim(Path(flat_blif), out_eslim, tb, size, seed)
    dt = time.time() - t0
    contest = None; err = None
    if res["ok"]:
        try:
            out_gate = WORK / f"par2_{pi:02d}_{pj:02d}_s{size}_seed{seed}_gates.blif"
            contest = translate_to_gates(out_eslim, out_gate, list(in_names), list(out_names))
        except Exception as e:
            err = str(e)
    return {
        "pair": (pi, pj), "size": size, "seed": seed,
        "init": res.get("init_gates_internal"),
        "final": res.get("final_gates_internal"),
        "contest": contest, "ok": res["ok"], "elapsed": dt, "err": err,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--time-budget", type=int, default=90)
    ap.add_argument("--sizes", type=int, nargs="+", default=[6, 8])
    ap.add_argument("--seeds", type=int, nargs="+", default=[1, 7777, 13371337])
    ap.add_argument("--max-pairs", type=int, default=30)
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--canonical", default=str(LONGHORN / "src/fp4_mul.blif"))
    ap.add_argument("--ledger", default=str(REPO / "experiments_eslim/exp_a2_ledger.tsv"))
    args = ap.parse_args()

    print(f"Reading: {args.canonical}")
    inputs, outputs, gates = parse_gate_blif(Path(args.canonical))
    base_count = len(gates)
    print(f"  baseline: {base_count} gates")

    locs = find_xor_xor_locations(gates)
    print(f"  XOR-XOR singles: {len(locs)}")
    pairs = list(combinations(range(len(locs)), 2))[:args.max_pairs]
    print(f"  pairs to try: {len(pairs)}")

    print("Generating perturbed BLIFs...")
    flat_paths = []
    for k, (pi, pj) in enumerate(pairs):
        try:
            perturbed = apply_two(gates, locs[pi], locs[pj])
            if perturbed is None:
                flat_paths.append(None); continue
        except Exception as e:
            print(f"  pair#{k}: {e}")
            flat_paths.append(None); continue
        var_blif = WORK / f"par2_{pi:02d}_{pj:02d}.blif"
        flat_blif = WORK / f"par2_{pi:02d}_{pj:02d}_flat.blif"
        write_gate_blif(var_blif, inputs, outputs, perturbed)
        try:
            flatten_blif(var_blif, flat_blif)
            flat_paths.append(str(flat_blif))
        except Exception as e:
            print(f"  pair#{k} flatten: {e}")
            flat_paths.append(None)

    valid = sum(1 for p in flat_paths if p is not None)
    print(f"  Valid perturbed BLIFs: {valid}/{len(pairs)}")

    jobs = []
    for k, (pi, pj) in enumerate(pairs):
        if flat_paths[k] is None: continue
        for size in args.sizes:
            for seed in args.seeds:
                jobs.append((pi, pj, size, seed, args.time_budget,
                             flat_paths[k], tuple(inputs), tuple(outputs)))
    print(f"\n{len(jobs)} jobs across {args.workers} workers")
    print(f"  estimated wall: {len(jobs) * args.time_budget / args.workers:.0f}s")

    Path(args.ledger).parent.mkdir(parents=True, exist_ok=True)
    if not Path(args.ledger).exists():
        with open(args.ledger, "w") as f:
            f.write("\t".join(["ts","loc_a","loc_b","size","seed",
                               "init","final","contest","ok"]) + "\n")

    best = base_count
    best_run = None
    n_done = 0
    t_start = time.time()
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(_job, j): j for j in jobs}
        for fut in as_completed(futures):
            r = fut.result()
            n_done += 1
            with open(args.ledger, "a") as f:
                f.write("\t".join([
                    time.strftime("%H:%M:%S"),
                    f"loc{r['pair'][0]}", f"loc{r['pair'][1]}",
                    str(r['size']), str(r['seed']),
                    str(r.get("init","?")), str(r.get("final","?")),
                    str(r.get("contest") if r.get("contest") is not None else "?"),
                    "OK" if r["ok"] else "FAIL",
                ]) + "\n")
            marker = ""
            if r["contest"] is not None and r["contest"] < best:
                best = r["contest"]; best_run = r
                marker = "  *** NEW BEST ***"
            print(f"[{n_done:3d}/{len(jobs)}] pair{r['pair']} "
                  f"s={r['size']} seed={r['seed']:>10}: "
                  f"contest={r.get('contest','?')} ({r['elapsed']:.0f}s){marker}",
                  flush=True)
            if r["err"]:
                print(f"      err: {r['err']}", flush=True)

    print()
    print("=" * 60)
    print(f"DONE. {n_done} runs in {time.time()-t_start:.0f}s.")
    print(f"Best contest: {best} (baseline {base_count})")
    if best < base_count:
        print(f"  *** SUB-{base_count} ACHIEVED ***")
        print(f"  best run: {best_run}")


if __name__ == "__main__":
    main()
