"""
Experiment H: Double XOR re-association on the 5-NOT 64-gate BLIF.

Round 2 applies ONE XOR re-association at a time. This experiment applies TWO
in sequence: apply loc_i → find new XOR-XOR locs in the result → apply loc_j.
The result is a 2D perturbation that creates structural topologies unreachable
by any single re-association. With 16 locs, up to C(16,2)=120 unique pairs.

Strategy: outer=first 8 locs, inner=first 4 fresh locs per result → 32 total
distinct doubly-perturbed BLIFs. Each run: size=6, 4 seeds, 90s budget.

Usage:
  python3 experiments_eslim/exp_h_double_xor.py [--workers 4]
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
LEDGER = REPO / "experiments_eslim/exp_h_ledger.tsv"


def _job(args):
    name, size, seed, flat_blif, in_names, out_names, time_budget = args
    safe = name.replace("/", "_")
    out_eslim = WORK / f"exph_{safe}_s{size}_seed{seed}_out.blif"
    t0 = time.time()
    res = run_eslim(Path(flat_blif), out_eslim, time_budget, size, seed)
    dt = time.time() - t0
    contest = None
    err = None
    if res["ok"]:
        try:
            out_gate = WORK / f"exph_{safe}_s{size}_seed{seed}_gates.blif"
            contest = translate_to_gates(out_eslim, out_gate,
                                         list(in_names), list(out_names))
        except Exception as e:
            err = str(e)
    return {
        "variant": name, "size": size, "seed": seed,
        "init_internal": res.get("init_gates_internal"),
        "final_internal": res.get("final_gates_internal"),
        "contest_cells": contest, "ok": res["ok"], "elapsed": dt, "err": err,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--sizes", type=int, nargs="+", default=[6, 8])
    ap.add_argument("--seeds", type=int, nargs="+",
                    default=[1, 42, 7777, 13371337])
    ap.add_argument("--time-budget", type=int, default=90)
    ap.add_argument("--outer-locs", type=int, default=8,
                    help="How many outer locs to iterate over")
    ap.add_argument("--inner-locs", type=int, default=4,
                    help="How many inner locs to apply per outer result")
    ap.add_argument("--canonical", default=str(SEED_BLIF))
    ap.add_argument("--ledger-out", default=None)
    args = ap.parse_args()

    seed_blif = Path(args.canonical)
    if args.ledger_out:
        global LEDGER
        LEDGER = Path(args.ledger_out)

    print(f"Exp H: double XOR re-association on {seed_blif.name}")
    inputs, outputs, gates = parse_gate_blif(seed_blif)
    base_count = len(gates)
    all_locs = find_xor_xor_locations(gates)
    print(f"  baseline: {base_count} gates, {len(all_locs)} XOR-XOR locs")

    # Build doubly-perturbed flat BLIFs
    flat_paths = {}
    outer_locs = all_locs[:args.outer_locs]
    for oi, (t_i, xp_i, par_i) in enumerate(outer_locs):
        try:
            gates1 = reassoc_at(gates, t_i, xp_i, par_i)
        except Exception as e:
            print(f"  outer loc#{oi} failed: {e}"); continue

        inner_locs = find_xor_xor_locations(gates1)[:args.inner_locs]
        for ji, (t_j, xp_j, par_j) in enumerate(inner_locs):
            name = f"dxor_o{oi}_i{ji}"
            try:
                gates2 = reassoc_at(gates1, t_j, xp_j, par_j)
            except Exception as e:
                print(f"  {name} inner failed: {e}"); continue
            var_blif = WORK / f"exph_{name}.blif"
            flat_blif = WORK / f"exph_{name}_flat.blif"
            write_gate_blif(var_blif, inputs, outputs, gates2)
            try:
                flatten_blif(var_blif, flat_blif)
                flat_paths[name] = str(flat_blif)
            except Exception as e:
                print(f"  {name} flatten failed: {e}")

    print(f"  {len(flat_paths)} doubly-perturbed BLIFs generated")

    jobs = [(name, size, seed, fp, tuple(inputs), tuple(outputs), args.time_budget)
            for name, fp in flat_paths.items()
            for size in args.sizes
            for seed in args.seeds]
    n_est = len(jobs) * args.time_budget / args.workers
    print(f"  {len(jobs)} jobs × {args.workers} workers, budget={args.time_budget}s")
    print(f"  est. wall: {n_est:.0f}s ({n_est/60:.0f}min)")

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
                time.strftime("%H:%M:%S"), res["variant"],
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
            print(f"[{n_done:3d}/{len(jobs)}] {res['variant']} "
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
