"""Single-(out, G, solver) Cirbo SAT attempt with extended time budget.
Used to push Y[k] @ G=7 harder than the default walk-up campaign.
"""
import sys, time
sys.path.insert(0, "/home/shadeform/fp4-multiplier/lib")
from cirbo.core.truth_table import TruthTableModel
from cirbo.synthesis.circuit_search import CircuitFinderSat, Operation
from fp4_spec import per_output_bit_truth_tables
from remap import encoding_from_magnitude_perm

OUR_BASIS = [Operation.and_, Operation.or_, Operation.xor_, Operation.lnot_]


def main():
    out_idx = int(sys.argv[1])
    G = int(sys.argv[2])
    time_limit = int(sys.argv[3])
    solver = sys.argv[4] if len(sys.argv) > 4 else "cadical195"
    perm_str = sys.argv[5] if len(sys.argv) > 5 else "0,1,2,3,6,7,4,5"
    perm = tuple(int(x) for x in perm_str.split(","))
    values = encoding_from_magnitude_perm(perm)
    tts = per_output_bit_truth_tables(values)
    tt = tts[out_idx]
    bits = [bool((tt >> i) & 1) for i in range(256)]
    table = [bits]
    model = TruthTableModel(table)
    finder = CircuitFinderSat(boolean_function_model=model,
                              number_of_gates=G, basis=OUR_BASIS)
    print(f"[Y[{out_idx}]] @ G={G} solver={solver} budget={time_limit}s start", flush=True)
    t0 = time.time()
    try:
        circuit = finder.find_circuit(solver_name=solver, time_limit=time_limit)
        wall = time.time() - t0
        print(f"[Y[{out_idx}]] G={G}: SAT  ({wall:.1f}s)  -> minimum = {G}", flush=True)
        print(f"--- Circuit ---", flush=True)
        print(circuit.format_circuit(), flush=True)
    except Exception as e:
        wall = time.time() - t0
        ename = type(e).__name__
        if "NoSolution" in ename:
            print(f"[Y[{out_idx}]] G={G}: UNSAT  ({wall:.1f}s)  -> minimum >= {G+1}",
                  flush=True)
        elif "TimeOut" in ename or "Timeout" in ename:
            print(f"[Y[{out_idx}]] G={G}: TIMEOUT ({wall:.1f}s)  -> inconclusive",
                  flush=True)
        else:
            print(f"[Y[{out_idx}]] G={G}: ERROR {ename}: {e}", flush=True)


if __name__ == "__main__":
    main()
