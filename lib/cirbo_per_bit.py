"""Find the exact gate-minimum for each Y[k] independently using Cirbo SAT.
Sum across k = upper bound on full-circuit gate count if no sharing exists."""
from __future__ import annotations
import sys
import time

from cirbo.core.truth_table import TruthTableModel
from cirbo.synthesis.circuit_search import CircuitFinderSat, Operation

from fp4_spec import per_output_bit_truth_tables, DEFAULT_FP4_VALUES
from remap import encoding_from_magnitude_perm

OUR_BASIS = [Operation.and_, Operation.or_, Operation.xor_, Operation.lnot_]


def find_min_for_output(tt_int: int, max_n: int = 15, time_budget: int = 60) -> int | None:
    """Binary-walk up: G=1, 2, ... until SAT. Returns minimum or None on timeout."""
    bits = [bool((tt_int >> i) & 1) for i in range(256)]
    table = [bits]
    model = TruthTableModel(table)
    for n in range(0, max_n + 1):
        # G=0 means "constant function". Special-case.
        if n == 0:
            if all(b == bits[0] for b in bits):
                return 0
            continue
        finder = CircuitFinderSat(boolean_function_model=model,
                                  number_of_gates=n, basis=OUR_BASIS)
        t0 = time.time()
        try:
            finder.find_circuit(time_limit=time_budget)
            return n
        except Exception as e:
            ename = type(e).__name__
            if "NoSolution" in ename:
                continue   # try larger n
            elif "TimeOut" in ename or "Timeout" in ename:
                return None
            raise


def main():
    perm_str = sys.argv[1] if len(sys.argv) > 1 else "0,1,2,3,6,7,4,5"
    perm = tuple(int(x) for x in perm_str.split(","))
    values = encoding_from_magnitude_perm(perm)
    print(f"Encoding: perm={perm} -> values_low_8={values[:8]}", flush=True)
    tts = per_output_bit_truth_tables(values)
    print(f"\n{'Y':>3} {'ones':>5} {'min_gates':>10} {'wall':>5}", flush=True)
    total = 0
    for k, tt in enumerate(tts):
        ones = bin(tt).count("1")
        t0 = time.time()
        n = find_min_for_output(tt, max_n=15, time_budget=120)
        wall = time.time() - t0
        if n is None:
            print(f"  Y[{k}]  {ones:>4}  {'TIMEOUT':>10} {wall:>5.1f}s", flush=True)
            return
        total += n
        print(f"  Y[{k}]  {ones:>4}  {n:>10} {wall:>5.1f}s", flush=True)
    print(f"\n  Sum (no sharing) = {total} gates")
    print("  Compared to current best with sharing: 85 gates")


if __name__ == "__main__":
    main()
