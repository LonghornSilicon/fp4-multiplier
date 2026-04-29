"""
Experiment D: Large-window direct eSLIM on the verified 5-NOT 64-gate BLIF.

No perturbation. Sizes 10 and 12 with 8 seeds, 180s budget each.
Hypothesis: eSLIM with size=6/8 has already saturated the 5-NOT basin at 64;
larger windows may find cross-basin paths not reachable at smaller sizes.

Usage:
  python3 experiments_eslim/exp_d_large_window.py [--workers 3]
"""
from __future__ import annotations
import argparse, time
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor, as_completed
import sys, os

sys.path.insert(0, str(Path(__file__).resolve().parent))
from exp_a_xor_reassoc import (
    parse_gate_blif, flatten_blif, run_eslim, translate_to_gates,
)

REPO = Path(__file__).resolve().parent.parent
WORK = Path("/tmp/eslim_work2")
WORK.mkdir(exist_ok=True)
SEED_BLIF = REPO / "experiments_eslim/fp4_64gate_5NOT_clean.blif"
LEDGER = REPO / "experiments_eslim/exp_d_ledger.tsv"
FLAT_BLIF = WORK / "expd_5NOT_flat.blif"


def _job(args):
    size, seed, flat_blif, in_names, out_names, time_budget = args
    out_eslim = WORK / f"expd_s{size}_seed{seed}_out.blif"
    t0 = time.time()
    res = run_eslim(Path(flat_blif), out_eslim, time_budget, size, seed)
    dt = time.time() - t0
    contest = None
    err = None
    if res["ok"]:
        try:
            out_gate = WORK / f"expd_s{size}_seed{seed}_gates.blif"
            contest = translate_to_gates(out_eslim, out_gate,
                                         list(in_names), list(out_names))
        except Exception as e:
            err = str(e)
    return {
        "size": size, "seed": seed,
        "init_internal": res.get("init_gates_internal"),
        "final_internal": res.get("final_gates_internal"),
        "contest_cells": contest, "ok": res["ok"], "elapsed": dt, "err": err,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=3)
    ap.add_argument("--sizes", type=int, nargs="+", default=[10, 12])
    ap.add_argument("--seeds", type=int, nargs="+",
                    default=[1, 42, 7777, 13371337, 99, 1024, 31415, 2718])
    ap.add_argument("--time-budget", type=int, default=180)
    ap.add_argument("--canonical", default=str(SEED_BLIF))
    ap.add_argument("--ledger-out", default=None)
    args = ap.parse_args()

    seed_blif = Path(args.canonical)
    if args.ledger_out:
        global LEDGER
        LEDGER = Path(args.ledger_out)

    print(f"Exp D: large-window eSLIM on {seed_blif.name}")
    inputs, outputs, gates = parse_gate_blif(seed_blif)
    base_count = len(gates)
    print(f"  baseline: {base_count} gates")

    flat_name = f"expd_{seed_blif.stem}_flat.blif"
    flat_blif_path = WORK / flat_name
    print(f"  Flattening to {flat_blif_path}...")
    flatten_blif(seed_blif, flat_blif_path)
    FLAT_BLIF_USED = flat_blif_path
    print(f"  Done.")

    jobs = [(s, seed, str(FLAT_BLIF_USED), tuple(inputs), tuple(outputs), args.time_budget)
            for s in args.sizes for seed in args.seeds]
    print(f"  {len(jobs)} jobs × {args.workers} workers, budget={args.time_budget}s")
    print(f"  est. wall: {len(jobs) * args.time_budget / args.workers:.0f}s")

    if not LEDGER.exists():
        with open(LEDGER, "w") as f:
            f.write("ts\tsize\tseed\tinit_internal\tfinal_internal\tcontest_cells\tok\n")

    best = base_count
    n_done = 0
    t_start = time.time()

    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(_job, j): j for j in jobs}
        for fut in as_completed(futures):
            res = fut.result()
            n_done += 1
            row = [
                time.strftime("%H:%M:%S"), str(res["size"]), str(res["seed"]),
                str(res.get("init_internal", "?")),
                str(res.get("final_internal", "?")),
                str(res["contest_cells"] if res["contest_cells"] is not None else "?"),
                "OK" if res["ok"] else "FAIL",
            ]
            with open(LEDGER, "a") as f:
                f.write("\t".join(row) + "\n")
            marker = ""
            if res["contest_cells"] is not None and res["contest_cells"] < best:
                best = res["contest_cells"]
                marker = "  *** NEW BEST ***"
            elapsed = time.time() - t_start
            print(f"[{n_done:2d}/{len(jobs)}] size={res['size']} seed={res['seed']:>10}: "
                  f"internal={res.get('final_internal','?')} "
                  f"contest={res.get('contest_cells','?')} "
                  f"({res['elapsed']:.1f}s total={elapsed:.0f}s){marker}", flush=True)
            if res.get("err"):
                print(f"      err: {res['err']}", flush=True)

    print(f"\nDONE. Best contest cells: {best} (baseline {base_count})")
    if best < base_count:
        print(f"*** SUB-{base_count} ACHIEVED ***")


if __name__ == "__main__":
    main()
