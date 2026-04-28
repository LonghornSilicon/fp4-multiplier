"""Memory-efficient streaming CNF dump for full-circuit exact synthesis.

This implementation builds the SAT encoding directly without loading all
clauses into Python memory at once — clauses are emitted to disk as
they're generated. Then kissat (or any SAT solver) can solve the file.

Encoding (standard exact synthesis, Soeken et al. style):

For target G gates over basis {AND, OR, XOR, NOT} synthesizing a
multi-output function with N inputs and M outputs over T = 2^N rows:

Variables:
  type[i, op]   for i in [0..G), op in {AND, OR, XOR, NOT}: "gate i is op"
  input[i, p]   for i in [0..G), p in [0..i+N): "input p of gate i comes from predecessor p"
                (predecessor p in [0..N) means PI p; p in [N..N+i) means gate p-N)
  value[i, r]   for i in [0..G), r in [0..T): "gate i has value 1 in row r"
  out[k, p]     for k in [0..M), p in [0..G+N): "output k is wired to predecessor p"

Constraints:
  C1. Each gate has exactly one type.
  C2. Each gate has exactly the right number of inputs (1 for NOT, 2 for AND/OR/XOR).
  C3. Each output is wired to exactly one signal.
  C4. For each row r and gate i: value[i, r] is consistent with its type and inputs.
  C5. For each row r and output k: out wire's value matches the expected truth table value.

Memory: each variable is 1 int. Each clause is a list of ints.
We emit clauses as (lit1 lit2 ... 0) lines to a DIMACS file, never
holding the full clause set in memory.

Note: this is DRAFTED but writing/testing a full encoding is large work.
For now, we use Cirbo's CircuitFinderSat to BUILD the CNF (in-memory),
write to disk, then run kissat. The build phase is the memory bottleneck
(~16GB at G=63 we observed). Lingeling-via-pysat shares CNF data with
solver, so saves 50% over cadical+pysat.
"""
import sys
import time
import os
sys.path.insert(0, "/home/shadeform/fp4-multiplier/lib")


def build_cnf_via_cirbo(G):
    """Use Cirbo to build the CNF (cleanly), return clauses + max_var.

    Memory-intensive — keeps CNF in Python memory. Use only when memory
    allows."""
    from cirbo.core.truth_table import TruthTableModel
    from cirbo.synthesis.circuit_search import CircuitFinderSat, Operation
    from fp4_spec import per_output_bit_truth_tables
    from remap import encoding_from_magnitude_perm

    OUR_BASIS = [Operation.and_, Operation.or_, Operation.xor_, Operation.lnot_]
    perm = (0, 1, 2, 3, 6, 7, 4, 5)
    values = encoding_from_magnitude_perm(perm)
    table = [[bool((tt >> i) & 1) for i in range(256)]
             for tt in per_output_bit_truth_tables(values)]
    model = TruthTableModel(table)
    finder = CircuitFinderSat(boolean_function_model=model,
                              number_of_gates=G, basis=OUR_BASIS)
    cnf = finder.get_cnf()
    max_var = max(abs(lit) for clause in cnf for lit in clause)
    return cnf, max_var


def write_dimacs_streaming(cnf, max_var, path):
    """Write DIMACS CNF file. Streaming: process one clause at a time."""
    n_clauses = len(cnf)
    with open(path, "w") as f:
        f.write(f"p cnf {max_var} {n_clauses}\n")
        for clause in cnf:
            f.write(" ".join(str(lit) for lit in clause) + " 0\n")


def main():
    G = int(sys.argv[1]) if len(sys.argv) > 1 else 60
    out_path = sys.argv[2] if len(sys.argv) > 2 else f"/tmp/G{G}.cnf"
    print(f"Building CNF for G={G}...", flush=True)
    t0 = time.time()
    cnf, max_var = build_cnf_via_cirbo(G)
    print(f"  build time: {time.time()-t0:.1f}s, vars: {max_var}, clauses: {len(cnf)}",
          flush=True)
    print(f"Writing to {out_path}", flush=True)
    write_dimacs_streaming(cnf, max_var, out_path)
    sz = os.path.getsize(out_path) / 1e6
    print(f"  done. File size: {sz:.1f} MB", flush=True)


if __name__ == "__main__":
    main()
