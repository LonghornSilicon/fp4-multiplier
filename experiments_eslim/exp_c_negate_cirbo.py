"""
Experiment C: Cirbo SAT on conditional-negate sub-block.

Function spec:
  Inputs: mag[7..0] (8 bits) + sy (1 bit) = 9 inputs
  Outputs: y[7..0] (8 bits) where:
    if sy == 0:  y[i] = mag[i]                    (passthrough)
    else:        y[7..0] = -mag (two's complement) (negation)

Two's complement negation for the 8-bit magnitude (with sy as control):
  y[i] = mag[i] XOR (sy AND ~below_i)
  where below_i = ~(mag[0] | mag[1] | ... | mag[i-1])
  (i.e., "all bits below position i are zero")

Longhorn proved ≥11 gates for this function. Their G=11 attempt timed out at
30 min. We push G=11 with longer budget, and also try G=12, G=13.

Note: Cirbo TruthTableModel is a fully-specified function (no don't-cares),
so we feed the EXACT 2^9 = 512 minterm truth table.
"""
from __future__ import annotations
import sys, os, time

try:
    from cirbo.core.truth_table import TruthTableModel
    from cirbo.synthesis.circuit_search import CircuitFinderSat, Operation
    HAS_CIRBO = True
    OUR_BASIS = [Operation.and_, Operation.or_, Operation.xor_, Operation.lnot_]
except ImportError as e:
    print(f"cirbo not available: {e}")
    sys.exit(1)


def build_negate_table():
    """Returns 8 rows, each 512 columns. Row i = output bit i.
    Minterm index m: bits 0..7 of m = mag[7..0] (mag[7] is MSB at bit 0 of m).
    Wait — let me be careful. By convention, the MSB of m corresponds to
    the FIRST input. We have inputs ordered [sy, mag[7], mag[6], ..., mag[0]],
    so bit (n-1-k) of m is input k.
    For 9 inputs, bit 8 of m = sy, bit 7 = mag[7], ..., bit 0 = mag[0].
    """
    out = [[False] * 512 for _ in range(8)]
    for m in range(512):
        sy = (m >> 8) & 1
        mag = m & 0xFF
        if sy == 0:
            y = mag
        else:
            y = (-mag) & 0xFF  # two's complement, 8-bit
        for i in range(8):
            # Row i = output bit i (0=LSB, 7=MSB).
            # By cirbo convention, our 8 outputs map to rows in the same order
            # we'll feed them. Let's say row 0 = y[0] = LSB.
            out[i][m] = bool((y >> i) & 1)
    return out


def find_min(table, max_n=20, time_budget=600, label=""):
    print(f"\n=== {label} ===", flush=True)
    n_in = len(table[0]).bit_length() - 1
    print(f"Inputs: {n_in}, outputs: {len(table)}", flush=True)
    print(f"{'G':>4}  {'result':>10}  {'wall':>6}", flush=True)
    model = TruthTableModel(table)
    last_unsat = None
    for n in range(8, max_n + 1):
        finder = CircuitFinderSat(boolean_function_model=model,
                                  number_of_gates=n, basis=OUR_BASIS)
        t0 = time.time()
        try:
            finder.find_circuit(time_limit=time_budget)
            wall = time.time() - t0
            print(f"  {n:>4}  {'SAT':>10}  {wall:>6.1f}s", flush=True)
            return n
        except Exception as e:
            wall = time.time() - t0
            ename = type(e).__name__
            if "NoSolution" in ename:
                print(f"  {n:>4}  {'UNSAT':>10}  {wall:>6.1f}s", flush=True)
                last_unsat = n
            elif "TimeOut" in ename or "Timeout" in ename:
                print(f"  {n:>4}  {'TIMEOUT':>10}  {wall:>6.1f}s "
                      f"(last UNSAT: {last_unsat})", flush=True)
                return None
            else:
                print(f"  {n:>4}  ERROR {ename}: {e}", flush=True)
                return None


def main():
    print("Building 9-input conditional-negate truth table (sy + mag[7..0])...")
    tbl = build_negate_table()
    n_in = len(tbl[0]).bit_length() - 1
    n_out = len(tbl)
    print(f"  {n_in} inputs, {n_out} outputs, {len(tbl[0])} minterms.")
    # Walk G from 8 upward. Longhorn proved UNSAT through G=10.
    # We push G=11 with a long budget (30min was their cutoff).
    find_min(tbl, max_n=14, time_budget=1800,
             label="Conditional negate (sy + mag[8] -> y[8])")


if __name__ == "__main__":
    main()
