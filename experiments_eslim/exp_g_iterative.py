"""
Experiment G: Iterative eSLIM on the 5-NOT 64-gate BLIF.

Strategy: run eSLIM once → get output BLIF → run eSLIM again on that output
(same or different seed) → repeat N times. Each iteration re-exposes the
resulting topology to eSLIM's window-walking, potentially crossing basin
boundaries that a single run can't reach.

eSLIM is deterministic per (input, size, seed). After one run with seed A,
the output is in a local minimum for that configuration. Running with seed B
from that output starts a new search from a different walk order, potentially
escaping the previous basin.

Parameters:
  --iters 5    (number of eSLIM passes per chain)
  --chains 6   (number of independent chains, each with a different seed sequence)
  --size 6     (window size — start small; 8 for a deeper run)

Usage:
  python3 experiments_eslim/exp_g_iterative.py [--workers 4] [--chains 8]
"""
from __future__ import annotations
import argparse, time
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor, as_completed
import sys, shutil

sys.path.insert(0, str(Path(__file__).resolve().parent))
from exp_a_xor_reassoc import (
    parse_gate_blif, flatten_blif, run_eslim, translate_to_gates,
)

REPO = Path(__file__).resolve().parent.parent
WORK = Path("/tmp/eslim_work2")
WORK.mkdir(exist_ok=True)
SEED_BLIF = REPO / "experiments_eslim/fp4_64gate_5NOT_clean.blif"
LEDGER = REPO / "experiments_eslim/exp_g_ledger.tsv"

# Chains: list of (chain_id, seed_sequence_list)
# Each chain starts from the flattened 5-NOT BLIF, applies seeds in sequence.
CHAIN_SEEDS = [
    [1, 42, 7777, 99, 13371337],
    [42, 7777, 1, 2718, 31415],
    [7777, 13371337, 42, 1024, 1],
    [13371337, 99, 1024, 7777, 42],
    [99, 1024, 31415, 1, 2718],
    [1024, 31415, 2718, 42, 99],
    [31415, 2718, 99, 13371337, 1024],
    [2718, 1, 13371337, 31415, 7777],
]


def _chain(args):
    chain_id, seed_seq, flat_blif_str, in_names, out_names, size, time_budget = args
    results = []
    cur_blif = Path(flat_blif_str)
    for step, seed in enumerate(seed_seq):
        out_eslim = WORK / f"expg_c{chain_id}_step{step}_s{size}_seed{seed}_out.blif"
        t0 = time.time()
        res = run_eslim(cur_blif, out_eslim, time_budget, size, seed)
        dt = time.time() - t0
        contest = None
        err = None
        if res["ok"]:
            try:
                out_gate = WORK / f"expg_c{chain_id}_step{step}_s{size}_seed{seed}_gates.blif"
                contest = translate_to_gates(out_eslim, out_gate,
                                             list(in_names), list(out_names))
                cur_blif = out_eslim  # advance to next step's input
            except Exception as e:
                err = str(e)
        results.append({
            "chain": chain_id, "step": step, "seed": seed, "size": size,
            "init_internal": res.get("init_gates_internal"),
            "final_internal": res.get("final_gates_internal"),
            "contest_cells": contest, "ok": res["ok"], "elapsed": dt, "err": err,
        })
        if not res["ok"]:
            break  # chain broken
    return results


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--size", type=int, default=6)
    ap.add_argument("--time-budget", type=int, default=90)
    ap.add_argument("--chains", type=int, default=8,
                    help="Number of independent chains to run (max 8)")
    ap.add_argument("--canonical", default=str(SEED_BLIF))
    ap.add_argument("--ledger-out", default=None)
    args = ap.parse_args()

    seed_blif = Path(args.canonical)
    if args.ledger_out:
        global LEDGER
        LEDGER = Path(args.ledger_out)

    print(f"Exp G: iterative eSLIM on {seed_blif.name}")
    inputs, outputs, gates = parse_gate_blif(seed_blif)
    base_count = len(gates)
    print(f"  baseline: {base_count} gates, size={args.size}, budget={args.time_budget}s")

    flat_stem = seed_blif.stem
    flat_blif = WORK / f"expg_{flat_stem}_flat.blif"
    flatten_blif(seed_blif, flat_blif)
    print(f"  flattened to {flat_blif}")

    chain_specs = CHAIN_SEEDS[:args.chains]
    jobs = [(i, seeds, str(flat_blif), tuple(inputs), tuple(outputs),
             args.size, args.time_budget)
            for i, seeds in enumerate(chain_specs)]
    n_iters = len(chain_specs[0]) if chain_specs else 0
    print(f"  {len(jobs)} chains × {n_iters} iters × {args.time_budget}s budget")
    print(f"  est. wall: {len(jobs) * n_iters * args.time_budget / args.workers:.0f}s "
          f"({args.workers} workers)")

    if not LEDGER.exists():
        with open(LEDGER, "w") as f:
            f.write("ts\tchain\tstep\tsize\tseed\tinit_internal\t"
                    "final_internal\tcontest_cells\tok\n")

    best = base_count
    n_chains_done = 0
    t_start = time.time()

    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(_chain, j): j for j in jobs}
        for fut in as_completed(futures):
            chain_results = fut.result()
            n_chains_done += 1
            for r in chain_results:
                row = [
                    time.strftime("%H:%M:%S"),
                    str(r["chain"]), str(r["step"]), str(r["size"]), str(r["seed"]),
                    str(r.get("init_internal", "?")),
                    str(r.get("final_internal", "?")),
                    str(r["contest_cells"] if r["contest_cells"] is not None else "?"),
                    "OK" if r["ok"] else "FAIL",
                ]
                with open(LEDGER, "a") as f:
                    f.write("\t".join(row) + "\n")
                marker = ""
                if r["contest_cells"] is not None and r["contest_cells"] < best:
                    best = r["contest_cells"]
                    marker = "  *** NEW BEST ***"
                print(f"  chain={r['chain']} step={r['step']} seed={r['seed']:>10}: "
                      f"internal={r.get('final_internal','?')} "
                      f"contest={r.get('contest_cells','?')}{marker}", flush=True)
            elapsed = time.time() - t_start
            print(f"[{n_chains_done}/{len(jobs)}] chains done, {elapsed:.0f}s elapsed",
                  flush=True)

    print(f"\nDONE. Best: {best} (baseline {base_count})")
    if best < base_count:
        print(f"*** SUB-{base_count} ACHIEVED ***")


if __name__ == "__main__":
    main()
