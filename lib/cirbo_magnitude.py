"""Cirbo SAT-exact synthesis on the *magnitude* function alone:
   inputs (eh_a, el_a, m_a, eh_b, el_b, m_b) → 8-bit unsigned magnitude.
   This is 6 inputs × 8 outputs = 64 minterms × 8 outputs — small enough
   that Cirbo should find the minimum in seconds-to-minutes."""
from __future__ import annotations
import sys
import time

from cirbo.core.truth_table import TruthTableModel
from cirbo.synthesis.circuit_search import CircuitFinderSat, Operation

from fp4_spec import DEFAULT_FP4_VALUES

OUR_BASIS = [Operation.and_, Operation.or_, Operation.xor_, Operation.lnot_]


def magnitude_truth_table(values: list[float]) -> list[list[bool]]:
    """For 6-input function (eh_a, el_a, m_a, eh_b, el_b, m_b), produce 8-bit
    magnitude per minterm. Indexing: minterm = (eh_a<<5)|(el_a<<4)|(m_a<<3)|
    (eh_b<<2)|(el_b<<1)|m_b. Magnitudes use the default encoding only.

    Cirbo's input ordering: bit 0 = least-significant. We'll enumerate minterm i
    as the 6-bit pattern with bit 5 = msb. Convention: input[0] = m_b (LSB).
    """
    # Default-encoding magnitude lookup: code (4-bit, no sign) -> magnitude.
    mag_for_code = []
    for code in range(8):
        # code = (eh, el, m). values[code] is the signed value at sign=0.
        mag_for_code.append(values[code])  # all positive in s=0 region

    out: list[list[bool]] = [[] for _ in range(8)]
    for minterm in range(64):
        # Decode (with my chosen mapping). I chose:
        #   bit 5 = eh_a, bit 4 = el_a, bit 3 = m_a, bit 2 = eh_b, bit 1 = el_b, bit 0 = m_b
        eh_a = (minterm >> 5) & 1
        el_a = (minterm >> 4) & 1
        m_a  = (minterm >> 3) & 1
        eh_b = (minterm >> 2) & 1
        el_b = (minterm >> 1) & 1
        m_b  = (minterm >> 0) & 1
        code_a = (eh_a << 2) | (el_a << 1) | m_a
        code_b = (eh_b << 2) | (el_b << 1) | m_b
        mag_a = abs(values[code_a])
        mag_b = abs(values[code_b])
        product = int(round(4 * mag_a * mag_b))
        for k in range(8):
            out[k].append(bool((product >> k) & 1))
    return out


def main():
    table = magnitude_truth_table(DEFAULT_FP4_VALUES)
    print("Magnitude function: 6 inputs × 8 outputs.")
    for k, row in enumerate(table):
        ones = sum(row)
        print(f"  M[{k}]: {ones:>2} ones / 64")
    model = TruthTableModel(table)

    print("\nSearching minimum gate count (basis = {AND,OR,XOR,NOT})...",
          flush=True)
    start = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    upper = int(sys.argv[2]) if len(sys.argv) > 2 else 50
    for n in range(start, upper + 1):
        finder = CircuitFinderSat(boolean_function_model=model,
                                  number_of_gates=n, basis=OUR_BASIS)
        t0 = time.time()
        try:
            finder.find_circuit(time_limit=600)
            print(f"  n={n}: SAT  ({time.time()-t0:.1f}s) — magnitude can be "
                  f"computed with {n} gates.")
            return
        except Exception as e:
            wall = time.time() - t0
            ename = type(e).__name__
            if "NoSolution" in ename:
                print(f"  n={n}: UNSAT  ({wall:.1f}s)", flush=True)
                continue
            elif "TimeOut" in ename or "Timeout" in ename:
                print(f"  n={n}: TIMEOUT  ({wall:.1f}s) — inconclusive", flush=True)
                return
            else:
                print(f"  n={n}: ERROR {ename}  ({wall:.1f}s)")
                return


if __name__ == "__main__":
    main()
