"""Extract the 7-gate optimal circuit for 2x2 unsigned multiplication.
Cirbo proved 7 is exact (G=6 UNSAT, G=7 SAT). Print the circuit so we can
embed it in our Verilog."""
from cirbo.core.truth_table import TruthTableModel
from cirbo.synthesis.circuit_search import CircuitFinderSat, Operation

OUR_BASIS = [Operation.and_, Operation.or_, Operation.xor_, Operation.lnot_]

# 2x2 unsigned mul: inputs M_a[1:0], M_b[1:0]; outputs P[3:0]
# Minterm idx = ma1*8 + ma0*4 + mb1*2 + mb0
def build_table():
    out = [[False] * 16 for _ in range(4)]
    for ma1 in range(2):
        for ma0 in range(2):
            for mb1 in range(2):
                for mb0 in range(2):
                    Ma = ma1*2 + ma0
                    Mb = mb1*2 + mb0
                    P = Ma * Mb
                    idx = ma1*8 + ma0*4 + mb1*2 + mb0
                    for k in range(4):
                        out[k][idx] = bool((P >> k) & 1)
    return out


table = build_table()
model = TruthTableModel(table)
finder = CircuitFinderSat(boolean_function_model=model, number_of_gates=7,
                          basis=OUR_BASIS)
print("Searching G=7 SAT for 2x2 mul ...", flush=True)
import time
t0 = time.time()
circuit = finder.find_circuit(time_limit=60)
print(f"  found in {time.time()-t0:.1f}s")
print(f"\nCircuit type: {type(circuit).__name__}")
print(f"Inputs: {circuit.inputs}")
print(f"Outputs: {circuit.outputs}")
print()
# Walk the circuit gates
gates = list(circuit.gates_iter()) if hasattr(circuit, 'gates_iter') else []
if not gates:
    # try other access
    print("dir(circuit):", [x for x in dir(circuit) if not x.startswith('_')])
else:
    for g in gates:
        print(g)
