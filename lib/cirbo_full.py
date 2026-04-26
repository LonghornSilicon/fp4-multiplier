"""SAT-based search for the FULL FP4 multiplier circuit at a target gate count.

Use Cirbo's CircuitFinderSat. We start at the current best (85) and walk down.
Each call asks: "is there a circuit with G gates that realizes the function?"
- SAT  -> we have a smaller circuit; record + try G-1
- UNSAT -> proven lower bound; we are done
- Timeout -> inconclusive at this G
"""
from __future__ import annotations
import argparse
import sys
import time
from pathlib import Path

from cirbo.core.truth_table import TruthTableModel
from cirbo.synthesis.circuit_search import CircuitFinderSat, Operation

from fp4_spec import per_output_bit_truth_tables, DEFAULT_FP4_VALUES
from remap import encoding_from_magnitude_perm

OUR_BASIS = [Operation.and_, Operation.or_, Operation.xor_, Operation.lnot_]


def build_truth_table(values):
    tts_int = per_output_bit_truth_tables(values)
    return [[bool((tt >> i) & 1) for i in range(256)] for tt in tts_int]


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--start", type=int, default=84,
                   help="initial G to try (one less than known-good 85)")
    p.add_argument("--floor", type=int, default=40,
                   help="lowest G to attempt (don't search lower than this)")
    p.add_argument("--time-budget", type=int, default=600,
                   help="per-G SAT-solver time budget (seconds)")
    p.add_argument("--remap-perm", type=str, default="0,1,2,3,6,7,4,5",
                   help="comma-separated 8-perm of magnitude indices")
    args = p.parse_args()

    perm = tuple(int(x) for x in args.remap_perm.split(","))
    values = encoding_from_magnitude_perm(perm)
    table = build_truth_table(values)
    model = TruthTableModel(table)
    print(f"Truth table: 8 inputs, 9 outputs. Sum of ones across outputs:",
          sum(b for row in table for b in row), flush=True)
    print(f"Remap perm: {perm}", flush=True)
    print(f"Searching downward from G={args.start} until UNSAT/timeout. "
          f"Per-G budget: {args.time_budget}s.", flush=True)

    G = args.start
    best_sat: int | None = None
    while G >= args.floor:
        finder = CircuitFinderSat(boolean_function_model=model,
                                  number_of_gates=G, basis=OUR_BASIS)
        t0 = time.time()
        try:
            circuit = finder.find_circuit(time_limit=args.time_budget)
            wall = time.time() - t0
            print(f"  G={G}: SAT  ({wall:.1f}s)", flush=True)
            best_sat = G
            G -= 1
        except Exception as e:
            wall = time.time() - t0
            ename = type(e).__name__
            if "NoSolution" in ename:
                print(f"  G={G}: UNSAT — proven lower bound ≥ {G+1}  ({wall:.1f}s)",
                      flush=True)
                if best_sat is not None:
                    print(f"\n*** Optimal: G = {best_sat} (within timeout). ***",
                          flush=True)
                else:
                    print(f"\nNo SAT found in [{args.floor}..{args.start}].",
                          flush=True)
                return
            elif "TimeOut" in ename or "Timeout" in ename:
                print(f"  G={G}: TIMEOUT after {wall:.1f}s  (inconclusive)",
                      flush=True)
                if best_sat is not None:
                    print(f"\nBest SAT result: G = {best_sat}.", flush=True)
                return
            else:
                print(f"  G={G}: ERROR {ename}: {e}  ({wall:.1f}s)", flush=True)
                return


if __name__ == "__main__":
    main()
