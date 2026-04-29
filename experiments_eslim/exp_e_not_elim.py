"""
Experiment E: NOT-elimination rewrites on the 5-NOT 64-gate BLIF.

Rewrite rule (gate-neutral, NOT-reducing):
  AND(NOT(x), y)  →  XOR(AND(x, y), y)   [net: -1 NOT, +1 XOR, total gates unchanged]

Each of the 5 NOT outputs in fp4_64gate_5NOT_clean.blif feeds exactly one AND
gate, so each of the 5 rewrites is valid. Each produces a 4-NOT 64-gate netlist.
We also try the all-5-at-once rewrite (0-NOT) as a structural extreme.

These 4-NOT topologies are different basins from where Round 2 explores, and may
let eSLIM find sub-64 or 3-NOT results that are inaccessible from the 5-NOT start.

Usage:
  python3 experiments_eslim/exp_e_not_elim.py [--workers 3]
"""
from __future__ import annotations
import argparse, time
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor, as_completed
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from exp_a_xor_reassoc import (
    parse_gate_blif, write_gate_blif, flatten_blif,
    run_eslim, translate_to_gates,
)

REPO = Path(__file__).resolve().parent.parent
WORK = Path("/tmp/eslim_work2")
WORK.mkdir(exist_ok=True)
SEED_BLIF = REPO / "experiments_eslim/fp4_64gate_5NOT_clean.blif"
LEDGER = REPO / "experiments_eslim/exp_e_ledger.tsv"


def find_and_not_patterns(gates):
    """Return list of (nx_wire, x_wire, y_wire, and_out_wire) for each
    AND(NOT(x), y) pattern where NOT fanout == 1."""
    not_map = {g["out"]: g["ins"][0] for g in gates if g["kind"] == "NOT"}
    # Count fanout for each wire
    fanout = {}
    for g in gates:
        for inp in g["ins"]:
            fanout[inp] = fanout.get(inp, 0) + 1

    patterns = []
    for g in gates:
        if g["kind"] != "AND":
            continue
        for pos, inp in enumerate(g["ins"]):
            if inp in not_map and fanout.get(inp, 0) == 1:
                x_wire = not_map[inp]
                y_wire = g["ins"][1 - pos]
                patterns.append((inp, x_wire, y_wire, g["out"]))
                break  # each AND has at most one NOT input we handle
    return patterns


def apply_not_elim(gates, patterns_to_apply):
    """Apply a set of NOT-elimination rewrites simultaneously.
    patterns_to_apply: list of (nx_wire, x_wire, y_wire, and_out_wire).
    For each pattern:
      - Remove the NOT gate (nx_wire)
      - Replace AND(nx_wire, y_wire)->and_out with:
          AND(x_wire, y_wire)->new_wire
          XOR(new_wire, y_wire)->and_out_wire
    """
    skip_outs = set()   # NOT gate outputs to remove
    replace_and = {}    # and_out_wire -> (x_wire, y_wire, new_wire)
    for nx_wire, x_wire, y_wire, and_out_wire in patterns_to_apply:
        skip_outs.add(nx_wire)
        new_wire = f"nelim_{x_wire}_{y_wire}"
        replace_and[and_out_wire] = (x_wire, y_wire, new_wire)

    new_gates = []
    for g in gates:
        if g["out"] in skip_outs:
            continue  # drop NOT gate
        if g["out"] in replace_and:
            x_wire, y_wire, new_wire = replace_and[g["out"]]
            new_gates.append({"kind": "AND", "ins": [x_wire, y_wire], "out": new_wire})
            new_gates.append({"kind": "XOR", "ins": [new_wire, y_wire], "out": g["out"]})
        else:
            new_gates.append(dict(g))
    return new_gates


def _job(args):
    variant_name, size, seed, flat_blif, in_names, out_names, time_budget = args
    safe = variant_name.replace("/", "_")
    out_eslim = WORK / f"expe_{safe}_s{size}_seed{seed}_out.blif"
    t0 = time.time()
    res = run_eslim(Path(flat_blif), out_eslim, time_budget, size, seed)
    dt = time.time() - t0
    contest = None
    err = None
    if res["ok"]:
        try:
            out_gate = WORK / f"expe_{safe}_s{size}_seed{seed}_gates.blif"
            contest = translate_to_gates(out_eslim, out_gate,
                                         list(in_names), list(out_names))
        except Exception as e:
            err = str(e)
    return {
        "variant": variant_name, "size": size, "seed": seed,
        "init_internal": res.get("init_gates_internal"),
        "final_internal": res.get("final_gates_internal"),
        "contest_cells": contest, "ok": res["ok"], "elapsed": dt, "err": err,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=3)
    ap.add_argument("--sizes", type=int, nargs="+", default=[6, 8])
    ap.add_argument("--seeds", type=int, nargs="+",
                    default=[1, 42, 7777, 13371337, 99, 1024, 31415, 2718])
    ap.add_argument("--time-budget", type=int, default=90)
    ap.add_argument("--canonical", default=str(SEED_BLIF))
    ap.add_argument("--ledger-out", default=None)
    args = ap.parse_args()

    seed_blif = Path(args.canonical)
    if args.ledger_out:
        global LEDGER
        LEDGER = Path(args.ledger_out)

    print(f"Exp E: NOT-elimination rewrites on {seed_blif.name}")
    inputs, outputs, gates = parse_gate_blif(seed_blif)
    base_count = len(gates)
    print(f"  baseline: {base_count} gates")

    patterns = find_and_not_patterns(gates)
    print(f"  AND-NOT patterns: {len(patterns)}")
    for nx, x, y, aout in patterns:
        print(f"    AND(NOT({x}), {y}) -> {aout}  [NOT wire: {nx}]")

    # Build variants: each single elimination + all-at-once
    variants = []
    for i, pat in enumerate(patterns):
        name = f"nelim{i}_{pat[1]}"  # e.g. nelim0_w69
        variant_gates = apply_not_elim(gates, [pat])
        variants.append((name, variant_gates))
    # All 5 at once
    all_gates = apply_not_elim(gates, patterns)
    variants.append(("nelim_all5", all_gates))

    print(f"  Generating {len(variants)} variant BLIFs...")
    flat_paths = {}
    for vname, vgates in variants:
        n_not = sum(1 for g in vgates if g["kind"] == "NOT")
        var_blif = WORK / f"expe_{vname}.blif"
        flat_blif = WORK / f"expe_{vname}_flat.blif"
        write_gate_blif(var_blif, inputs, outputs, vgates)
        try:
            flatten_blif(var_blif, flat_blif)
            flat_paths[vname] = str(flat_blif)
            print(f"  {vname}: {len(vgates)} gates, {n_not} NOTs, flat OK")
        except Exception as e:
            print(f"  {vname}: flatten FAILED: {e}")

    jobs = []
    for vname, fp in flat_paths.items():
        for size in args.sizes:
            for seed in args.seeds:
                jobs.append((vname, size, seed, fp,
                             tuple(inputs), tuple(outputs), args.time_budget))
    print(f"\nDispatching {len(jobs)} jobs × {args.workers} workers, "
          f"budget={args.time_budget}s")
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
