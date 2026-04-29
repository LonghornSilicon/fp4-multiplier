"""
Experiment F: Large-window eSLIM directly on the original Longhorn canonical
6-NOT 64-gate BLIF (fp4_mul.blif), using sizes 10 and 12.

Rationale: G6 preemptive test used size=6 on the canonical and returned 64
contest cells. Longhorn's own campaign used sizes up to 6 (per their README
"size 6 gives best results on this circuit"). Sizes 10 and 12 have never been
applied to the canonical. A larger window may find non-local replacements that
the size=6 window misses.

Usage:
  python3 experiments_eslim/exp_f_canon_large.py [--workers 3]
"""
from __future__ import annotations
import argparse, time
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor, as_completed
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from exp_a_xor_reassoc import (
    parse_gate_blif, flatten_blif, run_eslim, translate_to_gates,
)

REPO = Path(__file__).resolve().parent.parent
WORK = Path("/tmp/eslim_work2")
WORK.mkdir(exist_ok=True)
LONGHORN_BLIF = Path("/tmp/longhorn/fp4-multiplier/src/fp4_mul.blif")
LEDGER = REPO / "experiments_eslim/exp_f_ledger.tsv"
FLAT_BLIF = WORK / "expf_canon_flat.blif"


def _job(args):
    size, seed, flat_blif, in_names, out_names, time_budget = args
    out_eslim = WORK / f"expf_s{size}_seed{seed}_out.blif"
    t0 = time.time()
    res = run_eslim(Path(flat_blif), out_eslim, time_budget, size, seed)
    dt = time.time() - t0
    contest = None
    err = None
    if res["ok"]:
        try:
            out_gate = WORK / f"expf_s{size}_seed{seed}_gates.blif"
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
    ap.add_argument("--time-budget", type=int, default=240)
    args = ap.parse_args()

    print(f"Exp F: large-window eSLIM on canonical Longhorn BLIF")
    print(f"  {LONGHORN_BLIF}")
    inputs, outputs, gates = parse_gate_blif(LONGHORN_BLIF)
    base_count = len(gates)
    n_not = sum(1 for g in gates if g["kind"] == "NOT")
    print(f"  baseline: {base_count} gates, {n_not} NOTs")

    print(f"  Flattening to {FLAT_BLIF}...")
    flatten_blif(LONGHORN_BLIF, FLAT_BLIF)
    print(f"  Done.")

    jobs = [(s, seed, str(FLAT_BLIF), tuple(inputs), tuple(outputs), args.time_budget)
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

    print(f"\nDONE. Best: {best} (baseline {base_count})")
    if best < base_count:
        print(f"*** SUB-{base_count} ACHIEVED ***")


if __name__ == "__main__":
    main()
