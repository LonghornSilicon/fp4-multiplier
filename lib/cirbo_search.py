"""SAT-based exact circuit search using Cirbo (github.com/SPbSAT/cirbo).

Given the FP4 multiplier truth table over 8 inputs × 9 outputs, search for
the minimum-gate circuit over our restricted basis {AND, OR, XOR, NOT}.

Cirbo's CircuitFinderSat takes a target gate count G and asks SAT: "is there
a circuit with G gates that realizes this function?" UNSAT proves G-1 is a
lower bound.
"""
from __future__ import annotations
import time
from pathlib import Path

from cirbo.core.truth_table import TruthTableModel
from cirbo.synthesis.circuit_search import CircuitFinderSat, Operation, Basis

from fp4_spec import per_output_bit_truth_tables, DEFAULT_FP4_VALUES
from remap import encoding_from_magnitude_perm

# Our 4-cell library: AND2, OR2, XOR2, NOT1.  Cirbo's Operation enum names:
OUR_BASIS = [Operation.and_, Operation.or_, Operation.xor_, Operation.lnot_]


def build_truth_table(values: list[float]) -> list[list[bool]]:
    """For 8-input × 9-output multiplier, produce a list[9][256] of bools.

    Y[k] is bit k of qi9_encode(4 * val[a] * val[b]). Our minterm convention:
    minterm = a * 16 + b (a = bits 7..4, b = bits 3..0). Cirbo's convention is
    that input value list [b7, b6, ..., b0] forms minterm in big-endian binary.
    Matches our `per_output_bit_truth_tables` indexing if we read input bits
    `(a3, a2, a1, a0, b3, b2, b1, b0)` in order MSB first.

    The integer mapping is consistent: per_output_bit_truth_tables(...)[k]
    has bit i = 1 iff Y[k] = 1 for input pattern i, where i = a*16 + b
    (a in [0,15], b in [0,15]) with a being the high 4 bits.
    """
    tts_int = per_output_bit_truth_tables(values)
    out: list[list[bool]] = []
    for k, tt in enumerate(tts_int):
        bits = [bool((tt >> i) & 1) for i in range(256)]
        out.append(bits)
    return out


def try_size(values: list[float], n_gates: int, time_budget_s: int = 600) -> dict:
    """Ask Cirbo: is there an `n_gates`-gate circuit (basis {AND,OR,XOR,NOT})?
    Returns {'sat': bool, 'wall': float, 'circuit': Optional[Circuit]} or
    {'sat': None, 'wall': float, 'note': 'timeout'} if SAT solver times out.
    """
    table = build_truth_table(values)
    model = TruthTableModel(table)

    finder = CircuitFinderSat(
        boolean_function_model=model,
        number_of_gates=n_gates,
        basis=OUR_BASIS,
    )
    t0 = time.time()
    try:
        # Cirbo's find_circuit returns the Circuit on SAT; raises NoSolutionError
        # on UNSAT; raises TimeoutError on timeout.
        circuit = finder.find_circuit(time_limit=time_budget_s)
        return {"sat": True, "wall": time.time() - t0, "circuit": circuit}
    except Exception as e:
        wall = time.time() - t0
        ename = type(e).__name__
        if "NoSolution" in ename:
            return {"sat": False, "wall": wall, "note": "UNSAT — proven >= n+1 gates"}
        if "TimeOut" in ename or "Timeout" in ename:
            return {"sat": None, "wall": wall, "note": "timeout"}
        raise


def main():
    """Sanity check on Y[0] alone: it has 16 ones, simple structure. We
    expect a small minimum (~3-5 gates). Then try the full multi-output."""
    print("=== Y[0] alone (8-input × 1-output, 16 ones) ===")
    tts = build_truth_table(DEFAULT_FP4_VALUES)
    table_y0 = [tts[0]]   # single output
    model_y0 = TruthTableModel(table_y0)

    for n in range(1, 8):
        finder = CircuitFinderSat(boolean_function_model=model_y0,
                                   number_of_gates=n, basis=OUR_BASIS)
        t0 = time.time()
        try:
            c = finder.find_circuit(time_limit=120)
            print(f"  n={n}: SAT  ({time.time()-t0:.1f}s)")
            print("Y[0] minimum:", n)
            break
        except Exception as e:
            ename = type(e).__name__
            print(f"  n={n}: UNSAT/{ename}  ({time.time()-t0:.1f}s)")


if __name__ == "__main__":
    main()
