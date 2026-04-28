"""Custom streaming SAT encoder for exact circuit synthesis.

Implements the standard Soeken-style exact synthesis encoding directly,
streaming clauses to disk WITHOUT loading them into Python memory at
once. This bypasses pysat/Cirbo's in-memory CNF representation which is
the bottleneck (saw 36GB OOM at G=60 with lingeling+pysat).

Encoding (Soeken et al., DATE 2018; see also Cirbo paper IWLS 2024):

For target G gates over basis B = {AND, OR, XOR, NOT} synthesizing a
multi-output Boolean function with N inputs and M outputs, T = 2^N rows:

Variables (1-indexed for DIMACS):
  S(i, op)   for i in [0..G), op in B:
              "gate i is type op"
  X(i, p, q) for i in [0..G), p < q in [0..N+i):
              "gate i has inputs (p, q) where p < q"
  V(i, r)    for i in [0..G), r in [0..T):
              "gate i has value 1 in row r"
  P(k, p)    for k in [0..M), p in [0..N+G):
              "output k is wired to predecessor p"

Constraints (clauses, written as DIMACS lines):
  C1 (one type per gate):
       For each i: AT_LEAST_ONE { S(i,op) : op in B }
       For each i, op1 != op2: NOT S(i,op1) OR NOT S(i,op2) (mutex)
  C2 (one input combination per non-NOT gate; one input per NOT gate):
       For each i: AT_LEAST_ONE { X(i,p,q) : p<q in [0..N+i) }
       Mutex pairs of X variables (within gate i)
       For NOT gates, only allow X(i,p,p) form (degenerate)
  C3 (one wire per output):
       For each k: AT_LEAST_ONE { P(k,p) : p in [0..N+G) }
       Mutex pairs.
  C4 (gate value consistent with type and inputs):
       For each i, r, op, (p,q):
         If S(i,op) AND X(i,p,q):
            V(i,r) = op_func(val(p,r), val(q,r))
         where val(p,r) = (PI value at row r if p < N) or V(p-N, r) otherwise.
         Encoded as 4 clauses per (i, r, op, p, q) for op in {AND, OR, XOR}.
  C5 (output value matches truth table):
       For each k, r:
         If P(k,p): val(p,r) = T[k][r]
         (i.e., output wire's value at row r matches expected T[k][r])

This is a LOT of clauses. We stream them to disk.

For G=64, N=8, M=9, T=256, B size=4:
  S vars: 64 * 4 = 256
  X vars: sum_i C(N+i, 2) = sum_i (N+i)(N+i-1)/2 for i in 0..63
                          ~ (1/2) sum_i (i+8)^2 ~ 1/6 * 72^3 ~ 62K
  V vars: 64 * 256 = 16K
  P vars: 9 * (8 + 64) = 648
  Total vars: ~80K
  Clauses for C4: 64 * 256 * 4 * ~36 (average X choices) * 4 = ~9M
  Total: ~10M clauses
  DIMACS file: ~100-200 MB

This fits comfortably on disk. kissat solves CNF files <1GB easily.
"""
from __future__ import annotations
import sys, time, os
sys.path.insert(0, "/home/shadeform/fp4-multiplier/lib")
from fp4_spec import per_output_bit_truth_tables
from remap import encoding_from_magnitude_perm


# Operations
AND = 0
OR = 1
XOR = 2
NOT = 3
OPS = [AND, OR, XOR, NOT]
OPS_2IN = [AND, OR, XOR]

# Op truth tables: op_func(a, b) -> c
# AND, OR, XOR are 2-input. NOT is special-cased (1 input).
def op_func(op, a, b):
    if op == AND: return a & b
    if op == OR:  return a | b
    if op == XOR: return a ^ b
    if op == NOT: return 1 - a
    raise ValueError(op)


class CNFWriter:
    """Streaming DIMACS writer. Counts clauses; emits header at end."""
    def __init__(self, path):
        self.path = path
        self.body_path = path + ".body"
        self.body = open(self.body_path, "w")
        self.n_clauses = 0
        self.max_var = 0

    def add_clause(self, lits):
        if not lits:
            return
        for lit in lits:
            if abs(lit) > self.max_var:
                self.max_var = abs(lit)
        self.body.write(" ".join(str(l) for l in lits) + " 0\n")
        self.n_clauses += 1

    def add_at_least_one(self, lits):
        self.add_clause(list(lits))

    def add_at_most_one(self, lits):
        # Pairwise mutex: O(n^2)
        lits = list(lits)
        for i in range(len(lits)):
            for j in range(i+1, len(lits)):
                self.add_clause([-lits[i], -lits[j]])

    def add_exactly_one(self, lits):
        lits = list(lits)
        self.add_at_least_one(lits)
        self.add_at_most_one(lits)

    def finalize(self):
        self.body.close()
        with open(self.path, "w") as f:
            f.write(f"p cnf {self.max_var} {self.n_clauses}\n")
            with open(self.body_path) as g:
                for line in g:
                    f.write(line)
        os.unlink(self.body_path)


def encode(G, N, T_rows, output_truth):
    """G = num gates, N = num PIs, T_rows = 2^N (truth-table rows),
    output_truth = list of M lists of T_rows bools.

    Returns CNFWriter (file written)."""
    M = len(output_truth)
    n_basis = 4

    # Variable allocation (1-indexed)
    var_id = [1]  # mutable counter
    def next_var():
        v = var_id[0]
        var_id[0] += 1
        return v

    # S[i][op] = "gate i is type op"
    S = [[next_var() for _ in range(n_basis)] for _ in range(G)]

    # X[i] = list of (p, q, var) for all p < q in [0..N+i)
    # For NOT gates, we use X(i, p, p) which we encode as a "self-loop"
    # but easier: NOT has its own input variable Y(i, p) for one input.
    # Cleaner encoding: each gate has one "input pattern" variable per
    # possible (p, q) pair (including p=q for NOT).
    X = []
    for i in range(G):
        n_pred = N + i
        x_i = []
        for p in range(n_pred):
            for q in range(p, n_pred):
                x_i.append((p, q, next_var()))
        X.append(x_i)

    # V[i][r] = "gate i value at row r"
    V = [[next_var() for _ in range(T_rows)] for _ in range(G)]

    # P[k][p] = "output k wired to predecessor p (0..N+G-1)"
    n_out_pred = N + G
    P = [[next_var() for _ in range(n_out_pred)] for _ in range(M)]

    print(f"  Encoding: G={G} N={N} M={M} T={T_rows}, vars={var_id[0]-1}",
          flush=True)
    return S, X, V, P, var_id[0] - 1


def write_cnf(out_path, G, N, T_rows, output_truth):
    """Build full CNF and write to out_path. Returns (n_vars, n_clauses)."""
    M = len(output_truth)
    cnf = CNFWriter(out_path)

    # Var allocation
    var_id = [1]
    def alloc():
        v = var_id[0]; var_id[0] += 1
        return v

    S = [[alloc() for _ in range(4)] for _ in range(G)]
    # X[i] : list of (p, q, var). For NOT, only p=q used.
    X = []
    for i in range(G):
        n_pred = N + i
        x_i = []
        for p in range(n_pred):
            for q in range(p, n_pred):
                x_i.append((p, q, alloc()))
        X.append(x_i)
    V = [[alloc() for _ in range(T_rows)] for _ in range(G)]
    n_out_pred = N + G
    P = [[alloc() for _ in range(n_out_pred)] for _ in range(M)]

    # C1: each gate has exactly one type
    for i in range(G):
        cnf.add_exactly_one(S[i])

    # C2: each gate has exactly one input pattern
    for i in range(G):
        all_x = [v for (p, q, v) in X[i]]
        cnf.add_exactly_one(all_x)
        # If gate is NOT (S[i][NOT]), then X must be of form (p, p)
        # If gate is 2-input (AND/OR/XOR), then X must be of form (p, q) with p < q
        for (p, q, v) in X[i]:
            if p == q:
                # Only allowed if NOT
                # NOT S[i][AND] OR NOT v (etc. for OR, XOR)
                cnf.add_clause([-S[i][AND], -v])
                cnf.add_clause([-S[i][OR], -v])
                cnf.add_clause([-S[i][XOR], -v])
            else:
                cnf.add_clause([-S[i][NOT], -v])

    # C3: each output wired to exactly one signal
    for k in range(M):
        cnf.add_exactly_one(P[k])

    # C4: gate value consistency
    # For each i, r, (p, q, x_var) in X[i]:
    #   For each op in {AND, OR, XOR}: if x_var AND S[i][op]: V[i][r] = op_func(val(p,r), val(q,r))
    #   For NOT (only when p==q): if x_var AND S[i][NOT]: V[i][r] = NOT val(p,r)
    # val(p, r) = PI bit at row r if p < N, else V[p-N][r]
    def val_var(p, r):
        """Return ('const', 0/1) for PI at given row, or ('var', var_id)
        for gate output. Disambiguates constant from variable id."""
        if p < N:
            return ('const', (r >> p) & 1)
        else:
            return ('var', V[p - N][r])

    def encode_gate_consistency(i, r, p, q, x_var, op):
        """If x_var AND S[i][op]: V[i][r] = op_func(val(p,r), val(q,r))."""
        a_kind, a_val_or_var = val_var(p, r)
        if op == NOT:
            if a_kind == 'const':
                if a_val_or_var == 0:
                    cnf.add_clause([-S[i][NOT], -x_var, V[i][r]])
                else:
                    cnf.add_clause([-S[i][NOT], -x_var, -V[i][r]])
            else:
                a_var = a_val_or_var
                cnf.add_clause([-S[i][NOT], -x_var, a_var, V[i][r]])
                cnf.add_clause([-S[i][NOT], -x_var, -a_var, -V[i][r]])
            return

        b_kind, b_val_or_var = val_var(q, r)
        for a_val in (0, 1):
            for b_val in (0, 1):
                c_val = op_func(op, a_val, b_val)
                lits = []
                if a_kind == 'const':
                    if a_val_or_var != a_val:
                        continue
                else:
                    a_var = a_val_or_var
                    lits.append(-a_var if a_val else a_var)
                if b_kind == 'const':
                    if b_val_or_var != b_val:
                        continue
                else:
                    b_var = b_val_or_var
                    lits.append(-b_var if b_val else b_var)
                lits.append(-S[i][op])
                lits.append(-x_var)
                if c_val:
                    lits.append(V[i][r])
                else:
                    lits.append(-V[i][r])
                cnf.add_clause(lits)

    for i in range(G):
        for (p, q, x_var) in X[i]:
            for r in range(T_rows):
                if p == q:
                    encode_gate_consistency(i, r, p, q, x_var, NOT)
                else:
                    for op in OPS_2IN:
                        encode_gate_consistency(i, r, p, q, x_var, op)

    # C5: output truth table
    for k in range(M):
        for r in range(T_rows):
            for p in range(n_out_pred):
                # If P[k][p]: val(p, r) = output_truth[k][r]
                target = output_truth[k][r]
                if p < N:
                    bit = (r >> p) & 1
                    if bit != target:
                        # P[k][p] is contradicted
                        cnf.add_clause([-P[k][p]])
                    # else: trivially satisfied
                else:
                    v = V[p - N][r]
                    if target:
                        cnf.add_clause([-P[k][p], v])
                    else:
                        cnf.add_clause([-P[k][p], -v])

    cnf.finalize()
    print(f"  CNF: vars={cnf.max_var}, clauses={cnf.n_clauses}", flush=True)
    sz = os.path.getsize(out_path) / 1e6
    print(f"  File: {sz:.1f} MB", flush=True)
    return cnf.max_var, cnf.n_clauses


def main():
    G = int(sys.argv[1]) if len(sys.argv) > 1 else 50
    out_path = sys.argv[2] if len(sys.argv) > 2 else f"/tmp/G{G}_custom.cnf"
    perm = (0, 1, 2, 3, 6, 7, 4, 5)
    values = encoding_from_magnitude_perm(perm)
    table_int = per_output_bit_truth_tables(values)
    output_truth = [[(tt >> r) & 1 for r in range(256)] for tt in table_int]
    print(f"Encoding G={G}, N=8, M={len(output_truth)}, T=256")
    t0 = time.time()
    n_vars, n_clauses = write_cnf(out_path, G, 8, 256, output_truth)
    print(f"Done in {time.time()-t0:.1f}s. Run kissat:")
    print(f"  /home/shadeform/kissat/build/kissat {out_path}")


if __name__ == "__main__":
    main()
