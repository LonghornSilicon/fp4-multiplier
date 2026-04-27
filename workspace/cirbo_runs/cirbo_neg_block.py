"""Cirbo SAT on the conditional-negate sub-block.

Inputs: mag[7:0] (8 bits) + sy (1 bit) = 9 inputs.
Outputs: y[7:1] = 7 outputs (y[0] = mag[0] is trivial in mut11 form).

For sy=0: y[i] = mag[i].
For sy=1: y[i] = -mag, computed in mut11 form as
   y[i] = mag[i] XOR (sy & ~below_i) for i in [1,7]
   below_i = ~mag[0] & ~mag[1] & ... & ~mag[i-1]

Equivalent: y[7:0] = (sy=1) ? (-mag mod 256) : mag
Bit 0: y[0] = mag[0] always (in 2's-comp, bit 0 of -x = bit 0 of x for x != 0).

This walks G upward to find the true minimum of the conditional-negate
sub-block ALONE, providing a lower-bound additive component for the
full multiplier.
"""
import sys, time
sys.path.insert(0, "/home/shadeform/fp4-multiplier/lib")
from cirbo.core.truth_table import TruthTableModel
from cirbo.synthesis.circuit_search import CircuitFinderSat, Operation

OUR_BASIS = [Operation.and_, Operation.or_, Operation.xor_, Operation.lnot_]


def build_neg_table():
    """Conditional negate on (mag[7:0], sy) -> y[7:1].
    Index: bit 0 = sy, bits 1..8 = mag[0..7] (sy first to keep small bits leftmost).
    """
    out = [[False] * 512 for _ in range(7)]
    for idx in range(512):
        sy = idx & 1
        mag = (idx >> 1) & 0xFF
        if sy == 0:
            y = mag
        else:
            y = (-mag) & 0xFF
        for k in range(1, 8):
            out[k - 1][idx] = bool((y >> k) & 1)
    return out


def main():
    G_start = int(sys.argv[1]) if len(sys.argv) > 1 else 8
    G_max = int(sys.argv[2]) if len(sys.argv) > 2 else 25
    time_limit = int(sys.argv[3]) if len(sys.argv) > 3 else 1800
    solver = sys.argv[4] if len(sys.argv) > 4 else "cadical195"

    table = build_neg_table()
    model = TruthTableModel(table)
    print(f"Conditional negate: 9 inputs, 7 outputs", flush=True)
    print(f"Walking G {G_start}..{G_max} with {time_limit}s budget per step (solver={solver})",
          flush=True)
    last_unsat = None
    for G in range(G_start, G_max + 1):
        finder = CircuitFinderSat(boolean_function_model=model,
                                  number_of_gates=G, basis=OUR_BASIS)
        t0 = time.time()
        try:
            circuit = finder.find_circuit(solver_name=solver, time_limit=time_limit)
            wall = time.time() - t0
            print(f"  G={G}: SAT  ({wall:.1f}s)  -> conditional-negate >= {(last_unsat or G_start - 1) + 1}, found {G}",
                  flush=True)
            print(f"--- Circuit ---", flush=True)
            print(circuit.format_circuit(), flush=True)
            return
        except Exception as e:
            wall = time.time() - t0
            ename = type(e).__name__
            if "NoSolution" in ename:
                last_unsat = G
                print(f"  G={G}: UNSAT ({wall:.1f}s)", flush=True)
            elif "TimeOut" in ename or "Timeout" in ename:
                print(f"  G={G}: TIMEOUT ({wall:.1f}s)  -> conditional-negate >= {(last_unsat or G_start - 1) + 1}, indeterminate at {G}",
                      flush=True)
                return
            else:
                print(f"  G={G}: ERROR {ename}: {e}", flush=True)
                return


if __name__ == "__main__":
    main()
