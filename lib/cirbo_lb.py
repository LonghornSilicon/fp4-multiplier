"""Probe lower bound on full circuit via Cirbo SAT.
For each G in [start, stop, step], try to find a circuit with G gates.
SAT -> upper bound on optimum is G; UNSAT -> lower bound is G+1.
Each call has a tight time budget; we print results live.
"""
from __future__ import annotations
import sys
import time

from cirbo.core.truth_table import TruthTableModel
from cirbo.synthesis.circuit_search import CircuitFinderSat, Operation

from fp4_spec import per_output_bit_truth_tables
from remap import encoding_from_magnitude_perm

OUR_BASIS = [Operation.and_, Operation.or_, Operation.xor_, Operation.lnot_]


def main():
    perm_str = sys.argv[1] if len(sys.argv) > 1 else "0,1,2,3,6,7,4,5"
    start = int(sys.argv[2]) if len(sys.argv) > 2 else 10
    stop = int(sys.argv[3]) if len(sys.argv) > 3 else 80
    step = int(sys.argv[4]) if len(sys.argv) > 4 else 10
    budget = int(sys.argv[5]) if len(sys.argv) > 5 else 60

    perm = tuple(int(x) for x in perm_str.split(","))
    values = encoding_from_magnitude_perm(perm)
    table = [[bool((tt >> i) & 1) for i in range(256)]
             for tt in per_output_bit_truth_tables(values)]
    model = TruthTableModel(table)
    print(f"Probing full-circuit minimum at G ∈ [{start}, {stop}], step={step}, "
          f"per-G budget={budget}s. Perm: {perm}", flush=True)
    print(f"\n{'G':>4}  {'result':>12}  {'wall':>6}", flush=True)
    last_unsat = None
    last_sat = None
    for G in range(start, stop + 1, step):
        finder = CircuitFinderSat(boolean_function_model=model,
                                  number_of_gates=G, basis=OUR_BASIS)
        t0 = time.time()
        try:
            finder.find_circuit(time_limit=budget)
            wall = time.time() - t0
            print(f"{G:>4}  {'SAT':>12}  {wall:>6.1f}s", flush=True)
            last_sat = G
        except Exception as e:
            ename = type(e).__name__
            wall = time.time() - t0
            if "NoSolution" in ename:
                print(f"{G:>4}  {'UNSAT':>12}  {wall:>6.1f}s", flush=True)
                last_unsat = G
            elif "TimeOut" in ename or "Timeout" in ename:
                print(f"{G:>4}  {'TIMEOUT':>12}  {wall:>6.1f}s", flush=True)
            else:
                print(f"{G:>4}  ERROR {ename}: {e}", flush=True)

    print(f"\nSummary: best UNSAT={last_unsat} (lower bound ≥ {last_unsat+1 if last_unsat else '?'}); "
          f"best SAT={last_sat} (upper bound ≤ {last_sat if last_sat else '?'}).")


if __name__ == "__main__":
    main()
