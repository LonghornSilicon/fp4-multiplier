"""Build Cirbo SAT instance for full-circuit G, dump to DIMACS file.
Then we can run kissat directly without Python overhead."""
import sys
import time
sys.path.insert(0, "/home/shadeform/fp4-multiplier/lib")
from cirbo.core.truth_table import TruthTableModel
from cirbo.synthesis.circuit_search import CircuitFinderSat, Operation
from fp4_spec import per_output_bit_truth_tables
from remap import encoding_from_magnitude_perm

OUR_BASIS = [Operation.and_, Operation.or_, Operation.xor_, Operation.lnot_]


def main():
    G = int(sys.argv[1]) if len(sys.argv) > 1 else 64
    out_path = sys.argv[2] if len(sys.argv) > 2 else f"/tmp/cirbo_G{G}.cnf"
    perm_str = sys.argv[3] if len(sys.argv) > 3 else "0,1,2,3,6,7,4,5"
    perm = tuple(int(x) for x in perm_str.split(","))
    values = encoding_from_magnitude_perm(perm)
    table = [[bool((tt >> i) & 1) for i in range(256)]
             for tt in per_output_bit_truth_tables(values)]
    model = TruthTableModel(table)
    print(f"Building CNF for G={G}, 9 outputs, 8 inputs", flush=True)
    t0 = time.time()
    finder = CircuitFinderSat(boolean_function_model=model,
                              number_of_gates=G, basis=OUR_BASIS)
    cnf = finder.get_cnf()
    print(f"  build time: {time.time()-t0:.1f}s, #clauses: {len(cnf)}", flush=True)

    # Find max variable
    max_var = 0
    for c in cnf:
        for lit in c:
            v = abs(lit)
            if v > max_var:
                max_var = v
    print(f"  max var: {max_var}", flush=True)

    # Write DIMACS
    print(f"Writing to {out_path}", flush=True)
    with open(out_path, "w") as f:
        f.write(f"p cnf {max_var} {len(cnf)}\n")
        for c in cnf:
            f.write(" ".join(str(lit) for lit in c) + " 0\n")
    print(f"  done. File size: ", end="", flush=True)
    import os
    print(f"{os.path.getsize(out_path)/1e6:.1f} MB", flush=True)


if __name__ == "__main__":
    main()
