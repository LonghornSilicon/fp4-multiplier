"""Single-G Cirbo full-circuit SAT.
Just one G level, longer budget. Used for parallel LB walk-down.
"""
import sys, time
sys.path.insert(0, "/home/shadeform/fp4-multiplier/lib")
from cirbo.core.truth_table import TruthTableModel
from cirbo.synthesis.circuit_search import CircuitFinderSat, Operation
from fp4_spec import per_output_bit_truth_tables
from remap import encoding_from_magnitude_perm

OUR_BASIS = [Operation.and_, Operation.or_, Operation.xor_, Operation.lnot_]


def main():
    G = int(sys.argv[1])
    time_limit = int(sys.argv[2]) if len(sys.argv) > 2 else 14400
    solver = sys.argv[3] if len(sys.argv) > 3 else "cadical195"
    perm = (0, 1, 2, 3, 6, 7, 4, 5)
    values = encoding_from_magnitude_perm(perm)
    table = [[bool((tt >> i) & 1) for i in range(256)]
             for tt in per_output_bit_truth_tables(values)]
    model = TruthTableModel(table)
    print(f"[G={G}] full-circuit SAT, solver={solver}, budget={time_limit}s",
          flush=True)
    t0 = time.time()
    finder = CircuitFinderSat(boolean_function_model=model,
                              number_of_gates=G, basis=OUR_BASIS)
    try:
        circuit = finder.find_circuit(solver_name=solver, time_limit=time_limit)
        wall = time.time() - t0
        print(f"[G={G}]: SAT  ({wall:.1f}s)  ** FOUND CIRCUIT AT G={G} **",
              flush=True)
        print("--- Circuit ---", flush=True)
        try:
            print(circuit.format_circuit(), flush=True)
        except Exception:
            print("(format_circuit failed)", flush=True)
    except Exception as e:
        wall = time.time() - t0
        ename = type(e).__name__
        if "NoSolution" in ename:
            print(f"[G={G}]: UNSAT ({wall:.1f}s)  -> minimum >= {G+1}",
                  flush=True)
        elif "TimeOut" in ename or "Timeout" in ename:
            print(f"[G={G}]: TIMEOUT ({wall:.1f}s)  -> indeterminate",
                  flush=True)
        else:
            print(f"[G={G}]: ERROR {ename}: {e}", flush=True)


if __name__ == "__main__":
    main()
