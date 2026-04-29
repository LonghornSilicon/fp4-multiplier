"""
Parallelized version of exp_a_xor_reassoc.py.

Runs eSLIM jobs across N worker processes (default 8 to leave 4 cores idle).
Same XOR-of-XOR enumeration + flatten + eSLIM + translate pipeline, but
the (variant × size × seed) Cartesian product is dispatched to a process
pool. Each eSLIM invocation is single-threaded so this scales linearly.

Usage:
  python3 experiments_eslim/exp_a_parallel.py \
      --time-budget 60 --sizes 6 8 \
      --seeds 1 42 7777 13371337 --max-variants 12 --workers 8
"""
from __future__ import annotations
import argparse, subprocess, sys, os, time, json
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor, as_completed
from itertools import product

# Reuse single-process driver helpers
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from exp_a_xor_reassoc import (
    parse_gate_blif, write_gate_blif, find_xor_xor_locations,
    reassoc_at, flatten_blif, run_eslim, translate_to_gates,
    LONGHORN, ESLIM, WORK,
)

REPO = Path(__file__).resolve().parent.parent


def _job(args_tuple):
    """One eSLIM run. args_tuple = (loc_idx, size, seed, time_budget,
    flat_blif_path, in_names, out_names)."""
    (loc_idx, size, seed, tb, flat_blif, in_names, out_names) = args_tuple
    out_eslim = WORK / f"par_{loc_idx:03d}_s{size}_seed{seed}_out.blif"
    t0 = time.time()
    res = run_eslim(Path(flat_blif), out_eslim, tb, size, seed)
    dt = time.time() - t0
    contest = None
    err = None
    if res["ok"]:
        try:
            out_gate = WORK / f"par_{loc_idx:03d}_s{size}_seed{seed}_gates.blif"
            contest = translate_to_gates(out_eslim, out_gate,
                                          list(in_names), list(out_names))
        except Exception as e:
            err = f"translate: {e}"
    return {
        "loc_idx": loc_idx, "size": size, "seed": seed,
        "init_internal": res.get("init_gates_internal"),
        "final_internal": res.get("final_gates_internal"),
        "contest_cells": contest, "ok": res["ok"], "elapsed": dt, "err": err,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--time-budget", type=int, default=60)
    ap.add_argument("--sizes", type=int, nargs="+", default=[6, 8])
    ap.add_argument("--seeds", type=int, nargs="+",
                    default=[1, 42, 7777, 13371337])
    ap.add_argument("--max-variants", type=int, default=12)
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--canonical",
                    default=str(LONGHORN / "src/fp4_mul.blif"))
    ap.add_argument("--ledger",
                    default=str(REPO / "experiments_eslim/exp_a_ledger.tsv"))
    args = ap.parse_args()

    print(f"Reading: {args.canonical}")
    inputs, outputs, gates = parse_gate_blif(Path(args.canonical))
    base_count = len(gates)
    print(f"  baseline: {base_count} gates, "
          f"inputs={len(inputs)}, outputs={len(outputs)}")

    locs = find_xor_xor_locations(gates)[:args.max_variants]
    print(f"  XOR-XOR variants: {len(locs)}")

    # Pre-build all variant flat BLIFs (cheap, sequential)
    print("Generating perturbed BLIFs...")
    flat_paths = []
    for li, (t, p, par) in enumerate(locs):
        try:
            perturbed = reassoc_at(gates, t, p, par)
        except Exception as e:
            print(f"  loc#{li} reassoc failed: {e}")
            flat_paths.append(None); continue
        var_blif = WORK / f"par_var_{li:03d}.blif"
        flat_blif = WORK / f"par_var_{li:03d}_flat.blif"
        write_gate_blif(var_blif, inputs, outputs, perturbed)
        try:
            flatten_blif(var_blif, flat_blif)
            flat_paths.append(str(flat_blif))
            print(f"  loc#{li}: flat at {flat_blif.name}")
        except Exception as e:
            print(f"  loc#{li} flatten failed: {e}")
            flat_paths.append(None)

    # Build job list
    jobs = []
    for li, fp in enumerate(flat_paths):
        if fp is None: continue
        for size in args.sizes:
            for seed in args.seeds:
                jobs.append((li, size, seed, args.time_budget, fp,
                             tuple(inputs), tuple(outputs)))
    print(f"\nDispatching {len(jobs)} jobs across {args.workers} workers...")
    print(f"  estimated wall time: {len(jobs) * args.time_budget / args.workers:.0f}s")

    # Open ledger
    Path(args.ledger).parent.mkdir(parents=True, exist_ok=True)
    if not Path(args.ledger).exists():
        with open(args.ledger, "w") as f:
            f.write("\t".join(["ts","variant","size","seed","init_internal",
                               "final_internal","contest_cells","ok"]) + "\n")

    # Run pool
    best = base_count
    best_run = None
    n_done = 0
    t_start = time.time()
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(_job, j): j for j in jobs}
        for fut in as_completed(futures):
            res = fut.result()
            n_done += 1
            row = [
                time.strftime("%H:%M:%S"),
                f"loc{res['loc_idx']}",
                str(res['size']), str(res['seed']),
                str(res.get("init_internal","?")),
                str(res.get("final_internal","?")),
                str(res.get("contest_cells") if res.get("contest_cells") is not None else "?"),
                "OK" if res["ok"] else "FAIL"
            ]
            with open(args.ledger, "a") as f:
                f.write("\t".join(row) + "\n")
            marker = ""
            if res["contest_cells"] is not None and res["contest_cells"] < best:
                best = res["contest_cells"]
                best_run = res
                marker = "  *** NEW BEST ***"
            elapsed = time.time() - t_start
            print(f"[{n_done:3d}/{len(jobs)}] loc{res['loc_idx']:2d} "
                  f"size={res['size']} seed={res['seed']:>10}: "
                  f"final_internal={res.get('final_internal','?')} "
                  f"contest={res.get('contest_cells','?')} "
                  f"({res['elapsed']:.1f}s, total {elapsed:.0f}s){marker}",
                  flush=True)
            if res["err"]:
                print(f"      err: {res['err']}", flush=True)

    print()
    print("=" * 60)
    print(f"DONE. {n_done} runs in {time.time()-t_start:.0f}s.")
    print(f"Best contest cells: {best} (baseline {base_count})")
    if best < base_count:
        print(f"  *** SUB-{base_count} ACHIEVED ***")
        print(f"  best run: {best_run}")


if __name__ == "__main__":
    main()
