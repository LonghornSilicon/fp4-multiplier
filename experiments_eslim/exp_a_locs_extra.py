"""
Supplemental: XOR re-association sweep for locs 12-15 of the 5-NOT BLIF.

Round 2 (exp_a_parallel.py --max-variants 12) covered locs 0-11.
The 5-NOT BLIF has 16 XOR-XOR locations total; locs 12-15 are unexplored.
This script covers exactly those 4 remaining locations.

Usage:
  python3 experiments_eslim/exp_a_locs_extra.py [--workers 2]
"""
from __future__ import annotations
import argparse, time
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor, as_completed
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from exp_a_xor_reassoc import (
    parse_gate_blif, write_gate_blif, find_xor_xor_locations,
    reassoc_at, flatten_blif, run_eslim, translate_to_gates,
)

REPO = Path(__file__).resolve().parent.parent
WORK = Path("/tmp/eslim_work2")
WORK.mkdir(exist_ok=True)
SEED_BLIF = REPO / "experiments_eslim/fp4_64gate_5NOT_clean.blif"
LEDGER = REPO / "experiments_eslim/exp_a_locs_extra_ledger.tsv"
LOC_START = 12   # skip locs already covered by Round 2


def _job(args):
    loc_idx, size, seed, flat_blif, in_names, out_names, time_budget = args
    out_eslim = WORK / f"extra_{loc_idx:03d}_s{size}_seed{seed}_out.blif"
    t0 = time.time()
    res = run_eslim(Path(flat_blif), out_eslim, time_budget, size, seed)
    dt = time.time() - t0
    contest = None
    err = None
    if res["ok"]:
        try:
            out_gate = WORK / f"extra_{loc_idx:03d}_s{size}_seed{seed}_gates.blif"
            contest = translate_to_gates(out_eslim, out_gate,
                                         list(in_names), list(out_names))
        except Exception as e:
            err = str(e)
    return {
        "loc_idx": loc_idx, "size": size, "seed": seed,
        "init_internal": res.get("init_gates_internal"),
        "final_internal": res.get("final_gates_internal"),
        "contest_cells": contest, "ok": res["ok"], "elapsed": dt, "err": err,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=2)
    ap.add_argument("--sizes", type=int, nargs="+", default=[6, 8])
    ap.add_argument("--seeds", type=int, nargs="+",
                    default=[1, 42, 7777, 13371337, 99, 1024, 31415, 2718])
    ap.add_argument("--time-budget", type=int, default=90)
    args = ap.parse_args()

    print(f"Exp A extra locs ({LOC_START}+): XOR re-association on {SEED_BLIF.name}")
    inputs, outputs, gates = parse_gate_blif(SEED_BLIF)
    base_count = len(gates)
    print(f"  baseline: {base_count} gates")

    all_locs = find_xor_xor_locations(gates)
    locs = all_locs[LOC_START:]
    print(f"  Total XOR-XOR locs: {len(all_locs)}, using locs {LOC_START}-{LOC_START+len(locs)-1} ({len(locs)} locs)")

    flat_paths = {}
    for offset, (t_idx, xpos, par_idx) in enumerate(locs):
        li = LOC_START + offset
        try:
            perturbed = reassoc_at(gates, t_idx, xpos, par_idx)
        except Exception as e:
            print(f"  loc#{li} reassoc failed: {e}"); continue
        var_blif = WORK / f"extra_var_{li:03d}.blif"
        flat_blif = WORK / f"extra_var_{li:03d}_flat.blif"
        write_gate_blif(var_blif, inputs, outputs, perturbed)
        try:
            flatten_blif(var_blif, flat_blif)
            flat_paths[li] = str(flat_blif)
            print(f"  loc#{li}: flat OK")
        except Exception as e:
            print(f"  loc#{li} flatten failed: {e}")

    jobs = [(li, size, seed, fp, tuple(inputs), tuple(outputs), args.time_budget)
            for li, fp in flat_paths.items()
            for size in args.sizes
            for seed in args.seeds]
    print(f"\nDispatching {len(jobs)} jobs × {args.workers} workers, budget={args.time_budget}s")
    print(f"  est. wall: {len(jobs) * args.time_budget / args.workers:.0f}s")

    if not LEDGER.exists():
        with open(LEDGER, "w") as f:
            f.write("ts\tvariant\tsize\tseed\tinit_internal\t"
                    "final_internal\tcontest_cells\tok\n")

    best = base_count
    n_done = 0
    t_start = time.time()

    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(_job, j): j for j in jobs}
        for fut in as_completed(futures):
            res = fut.result()
            n_done += 1
            row = [
                time.strftime("%H:%M:%S"), f"loc{res['loc_idx']}",
                str(res["size"]), str(res["seed"]),
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
            print(f"[{n_done:2d}/{len(jobs)}] loc{res['loc_idx']} "
                  f"size={res['size']} seed={res['seed']:>10}: "
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
