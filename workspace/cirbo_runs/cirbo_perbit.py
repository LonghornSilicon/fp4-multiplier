"""Per-output-bit Cirbo SAT lower-bound search.
Each Y[k] is a single-output 8-input function — much smaller SAT instance
than the full 9-output circuit. Memory cost ~1-2GB per worker.

For Y[k], we walk G upward: G=4, 5, 6, ... until SAT or timeout.
The first SAT gives the proven minimum (since all G' < G were UNSAT).

Usage: cirbo_perbit.py <out_idx> <max_G> <time_limit> <solver> [perm_str]
       (Run multiple in parallel, one per output bit.)
"""
from __future__ import annotations
import csv
import json
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO / "lib"))
from cirbo.core.truth_table import TruthTableModel
from cirbo.synthesis.circuit_search import CircuitFinderSat, Operation
from fp4_spec import per_output_bit_truth_tables
from remap import encoding_from_magnitude_perm

OUR_BASIS = [Operation.and_, Operation.or_, Operation.xor_, Operation.lnot_]


def main():
    out_idx = int(sys.argv[1])
    max_G = int(sys.argv[2])
    time_limit = int(sys.argv[3])
    solver = sys.argv[4]
    perm_str = sys.argv[5] if len(sys.argv) > 5 else "0,1,2,3,6,7,4,5"
    ledger = sys.argv[6] if len(sys.argv) > 6 else \
        "/home/shadeform/fp4-multiplier/workspace/cirbo_runs/perbit_ledger.tsv"

    perm = tuple(int(x) for x in perm_str.split(","))
    values = encoding_from_magnitude_perm(perm)
    tts = per_output_bit_truth_tables(values)
    tt = tts[out_idx]
    bits = [bool((tt >> i) & 1) for i in range(256)]
    table = [bits]
    model = TruthTableModel(table)
    print(f"[Y[{out_idx}]] solver={solver} max_G={max_G} time_limit={time_limit}s",
          flush=True)

    last_unsat = None
    for G in range(1, max_G + 1):
        finder = CircuitFinderSat(boolean_function_model=model,
                                  number_of_gates=G, basis=OUR_BASIS)
        t0 = time.time()
        try:
            finder.find_circuit(solver_name=solver, time_limit=time_limit)
            wall = time.time() - t0
            print(f"[Y[{out_idx}]] G={G}: SAT  ({wall:.1f}s, solver={solver})", flush=True)
            write_ledger(ledger, out_idx, G, "SAT", solver, wall, last_unsat)
            print(f"[Y[{out_idx}]] *** PROVEN MINIMUM = {G} *** "
                  f"(after UNSAT at G={last_unsat})", flush=True)
            return
        except Exception as e:
            wall = time.time() - t0
            ename = type(e).__name__
            if "NoSolution" in ename:
                last_unsat = G
                print(f"[Y[{out_idx}]] G={G}: UNSAT  ({wall:.1f}s, solver={solver})",
                      flush=True)
                write_ledger(ledger, out_idx, G, "UNSAT", solver, wall, None)
            elif "TimeOut" in ename or "Timeout" in ename:
                print(f"[Y[{out_idx}]] G={G}: TIMEOUT ({wall:.1f}s, solver={solver})",
                      flush=True)
                write_ledger(ledger, out_idx, G, "TIMEOUT", solver, wall, last_unsat)
                print(f"[Y[{out_idx}]] STOP (last UNSAT = {last_unsat}, "
                      f"so lower bound >= {(last_unsat or 0) + 1})", flush=True)
                return
            else:
                print(f"[Y[{out_idx}]] G={G}: ERROR {ename}: {e}", flush=True)
                write_ledger(ledger, out_idx, G, "ERROR", solver, wall, last_unsat)
                return


def write_ledger(path, out_idx, G, verdict, solver, wall, last_unsat):
    new = not Path(path).exists()
    with open(path, "a", newline="") as f:
        w = csv.writer(f, delimiter="\t")
        if new:
            w.writerow(["ts", "out", "G", "verdict", "solver", "wall_s",
                        "last_unsat"])
        w.writerow([int(time.time()), f"Y[{out_idx}]", G, verdict, solver,
                    f"{wall:.1f}", last_unsat or ""])


if __name__ == "__main__":
    main()
