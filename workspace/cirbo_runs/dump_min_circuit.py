"""Re-prove Y[k] minimum and dump the resulting Cirbo circuit so we can
inspect its structure (which gates, what operations)."""
import sys
sys.path.insert(0, "/home/shadeform/fp4-multiplier/lib")
from cirbo.core.truth_table import TruthTableModel
from cirbo.synthesis.circuit_search import CircuitFinderSat, Operation
from fp4_spec import per_output_bit_truth_tables
from remap import encoding_from_magnitude_perm

OUR_BASIS = [Operation.and_, Operation.or_, Operation.xor_, Operation.lnot_]


def main():
    out_idx = int(sys.argv[1])
    G = int(sys.argv[2])
    perm = (0, 1, 2, 3, 6, 7, 4, 5)
    values = encoding_from_magnitude_perm(perm)
    tts = per_output_bit_truth_tables(values)
    tt = tts[out_idx]
    bits = [bool((tt >> i) & 1) for i in range(256)]
    table = [bits]
    model = TruthTableModel(table)
    finder = CircuitFinderSat(boolean_function_model=model,
                              number_of_gates=G, basis=OUR_BASIS)
    print(f"Y[{out_idx}] @ G={G} basis=AND/OR/XOR/NOT", flush=True)
    circuit = finder.find_circuit(time_limit=180)
    print(f"Found! Circuit:", flush=True)
    print(circuit, flush=True)


if __name__ == "__main__":
    main()
