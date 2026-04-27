"""Multi-output Cirbo SAT to find sharing-aware lower bound.

Synthesize a SUBSET of output bits together. The SAT minimum tells us
the smallest gate count to compute that subset jointly (allowing
sharing within the subset).

If min(Y[i] + Y[j]) < min(Y[i]) + min(Y[j]), there's intrinsic
sharing between those outputs. Repeating for many pairs/triples gives
us shape of the sharing structure.
"""
import sys, time
sys.path.insert(0, "/home/shadeform/fp4-multiplier/lib")
from cirbo.core.truth_table import TruthTableModel
from cirbo.synthesis.circuit_search import CircuitFinderSat, Operation
from fp4_spec import per_output_bit_truth_tables
from remap import encoding_from_magnitude_perm

OUR_BASIS = [Operation.and_, Operation.or_, Operation.xor_, Operation.lnot_]


def main():
    # Output indices to synthesize jointly (e.g., "0,8" or "0,1,8")
    out_indices = [int(x) for x in sys.argv[1].split(",")]
    G_start = int(sys.argv[2]) if len(sys.argv) > 2 else 4
    G_max = int(sys.argv[3]) if len(sys.argv) > 3 else 30
    time_limit = int(sys.argv[4]) if len(sys.argv) > 4 else 1800
    solver = sys.argv[5] if len(sys.argv) > 5 else "cadical195"
    perm_str = "0,1,2,3,6,7,4,5"

    perm = tuple(int(x) for x in perm_str.split(","))
    values = encoding_from_magnitude_perm(perm)
    tts = per_output_bit_truth_tables(values)
    table = []
    for k in out_indices:
        bits = [bool((tts[k] >> i) & 1) for i in range(256)]
        table.append(bits)
    model = TruthTableModel(table)
    out_label = ",".join(f"Y[{k}]" for k in out_indices)
    print(f"Multi-output: {out_label} ({len(out_indices)} outputs, 8 inputs)",
          flush=True)
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
            print(f"  G={G}: SAT  ({wall:.1f}s)  -> joint min({out_label}) = {G}",
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
                print(f"  G={G}: TIMEOUT ({wall:.1f}s)  -> joint min({out_label}) >= {(last_unsat or G_start - 1) + 1}",
                      flush=True)
                return
            else:
                print(f"  G={G}: ERROR {ename}: {e}", flush=True)
                return


if __name__ == "__main__":
    main()
