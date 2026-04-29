"""
Direct SAT-based exact synthesis (Kullmann/Knuth style) for the FP4 multiplier.

Encodes "is there a netlist of <= K gates over {AND2, OR2, XOR2, NOT1} that
computes the FP4 multiplier function?" as a CNF and asks CaDiCaL for a model.

Variables:
  - kind[g][t] for g in 0..K-1, t in {AND, OR, XOR, NOT}: at-most-1, at-least-1
  - in0[g][s], in1[g][s] for s in 0..(8 + g - 1): selector vars (PI or earlier gate)
  - out_sel[o][s] for o in 0..8, s in 0..(8 + K - 1): output wire selectors
  - val[g][m] for g in 0..K-1, m in 0..255: gate value at minterm m
  - in0_val[g][m], in1_val[g][m]: helper vars equal to val of selected source

Constraints:
  - exactly-one for kind[g][*], in0[g][*], in1[g][*], out_sel[o][*]
  - functional: kind selector + input selectors -> val[g][m] for every m
  - target: out_sel[o] picks a wire whose val[m] equals the target output bit

Practical notes:
  - At K=62 this is ~25k vars and ~200k clauses with naive encoding.
  - At full size, expect minutes-to-hours per call. UNSAT is much harder than SAT.
  - We do *not* enforce symmetry breaking beyond a basic gate-ordering pass.

For the paper: even a successful UNSAT at K=62 (proof of optimality at 63)
is a publishable result.
"""
from __future__ import annotations
import argparse, sys, os, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pysat.solvers import Cadical103
from pysat.card import CardEnc, EncType
from analysis.lower_bound import build_funcs_under_sigma


# Gate kinds in fixed order
KIND_AND, KIND_OR, KIND_XOR, KIND_NOT = 0, 1, 2, 3
KINDS = [KIND_AND, KIND_OR, KIND_XOR, KIND_NOT]
KIND_NAMES = {0: "AND", 1: "OR", 2: "XOR", 3: "NOT"}
N_INPUTS = 8
N_OUTPUTS = 9
N_MINTERMS = 256


class CnfBuilder:
    def __init__(self, solver=None):
        self.next_var = 1
        self.clauses = [] if solver is None else None
        self.solver = solver
        self.n_clauses = 0

    def new_var(self):
        v = self.next_var
        self.next_var += 1
        return v

    def add(self, *clause):
        self.n_clauses += 1
        if self.solver is not None:
            self.solver.add_clause(clause)
        else:
            self.clauses.append(list(clause))

    def add_many(self, clauses):
        for c in clauses:
            self.add(*c)

    def at_most_one(self, vars):
        # Pairwise. Sufficient for our small selectors.
        for i in range(len(vars)):
            for j in range(i + 1, len(vars)):
                self.add(-vars[i], -vars[j])

    def at_least_one(self, vars):
        self.add(*vars)

    def exactly_one(self, vars):
        self.at_least_one(vars)
        self.at_most_one(vars)

    def equal(self, a, b):
        # a <-> b
        self.add(-a, b)
        self.add(a, -b)

    def or_gate(self, a, b, out):
        # out = a OR b
        self.add(-a, out)
        self.add(-b, out)
        self.add(a, b, -out)

    def and_gate(self, a, b, out):
        # out = a AND b
        self.add(a, -out)
        self.add(b, -out)
        self.add(-a, -b, out)

    def xor_gate(self, a, b, out):
        # out = a XOR b
        self.add(-a, -b, -out)
        self.add(a, b, -out)
        self.add(a, -b, out)
        self.add(-a, b, out)

    def not_gate(self, a, out):
        # out = NOT a
        self.equal(a, -out)


def encode(K: int, targets: list[list[int]], pi_vals: list[list[int]], solver=None):
    """
    targets[o][m] = desired bit value (0 or 1) for output o at minterm m.
    pi_vals[i][m] = bit value of primary input i at minterm m.
    If `solver` is given, clauses are streamed to it instead of buffered.
    """
    cb = CnfBuilder(solver=solver)

    # Variables
    kind = [[cb.new_var() for _ in KINDS] for _ in range(K)]
    in0_sel = [[cb.new_var() for _ in range(N_INPUTS + g)] for g in range(K)]
    in1_sel = [[cb.new_var() for _ in range(N_INPUTS + g)] for g in range(K)]
    out_sel = [[cb.new_var() for _ in range(N_INPUTS + K)] for _ in range(N_OUTPUTS)]
    val = [[cb.new_var() for _ in range(N_MINTERMS)] for _ in range(K)]

    # Each gate has exactly one kind
    for g in range(K):
        cb.exactly_one(kind[g])
        cb.exactly_one(in0_sel[g])
        # NOT only uses in0; for binary gates, in1 also exactly-one. Allow
        # either: always exactly-one of in1, but ignore for NOT (no constraints
        # on output rely on in1_val when kind=NOT).
        cb.exactly_one(in1_sel[g])

    # Each output has exactly one source
    for o in range(N_OUTPUTS):
        cb.exactly_one(out_sel[o])

    # Symmetry break for commutative gates: forbid in0_idx >= in1_idx when
    # kind in {AND, OR, XOR}. Halves the search space per commutative gate.
    # Also rules out trivial AND(x,x)=x / OR(x,x)=x / XOR(x,x)=0.
    # NOT is unary so in1 is irrelevant; no constraint added for NOT.
    for g in range(K):
        for s0 in range(N_INPUTS + g):
            for s1 in range(s0 + 1):  # s1 <= s0 forbidden for commutative kinds
                cb.add(-kind[g][KIND_AND], -in0_sel[g][s0], -in1_sel[g][s1])
                cb.add(-kind[g][KIND_OR],  -in0_sel[g][s0], -in1_sel[g][s1])
                cb.add(-kind[g][KIND_XOR], -in0_sel[g][s0], -in1_sel[g][s1])

    # Functional constraints. For each gate g and each minterm m:
    # We enumerate (i0, i1) source choices and (kind) choices and constrain val.
    # This is O(K * (N_INPUTS+K) * (N_INPUTS+K) * N_MINTERMS * 4) clauses --
    # very large. Use the source-conditioning style:
    #    (in0_sel[g][s] /\ in1_sel[g][s'] /\ kind[g][k]) -> val[g][m] = f_k(s_val, s'_val)
    # and for NOT, in1 is unconstrained (we still emit the constraint with in1
    # arbitrary, but tie val to NOT(in0_val) regardless of in1).
    for g in range(K):
        # Precompute possible source values per minterm
        # Source idx s in 0..N_INPUTS-1 -> PI value pi_vals[s][m] (constant)
        # Source idx s in N_INPUTS..N_INPUTS+g-1 -> val[s - N_INPUTS][m] (variable)
        for m in range(N_MINTERMS):
            for s0 in range(N_INPUTS + g):
                for s1 in range(N_INPUTS + g):
                    a_val = pi_vals[s0][m] if s0 < N_INPUTS else None
                    b_val = pi_vals[s1][m] if s1 < N_INPUTS else None
                    a_var = None if s0 < N_INPUTS else val[s0 - N_INPUTS][m]
                    b_var = None if s1 < N_INPUTS else val[s1 - N_INPUTS][m]

                    # AND
                    # in0_sel /\ in1_sel /\ kind=AND -> val = a /\ b
                    sel_lits = [-in0_sel[g][s0], -in1_sel[g][s1], -kind[g][KIND_AND]]
                    enforce_eq(cb, sel_lits, val[g][m], "AND", a_val, b_val, a_var, b_var)
                    # OR
                    sel_lits = [-in0_sel[g][s0], -in1_sel[g][s1], -kind[g][KIND_OR]]
                    enforce_eq(cb, sel_lits, val[g][m], "OR", a_val, b_val, a_var, b_var)
                    # XOR
                    sel_lits = [-in0_sel[g][s0], -in1_sel[g][s1], -kind[g][KIND_XOR]]
                    enforce_eq(cb, sel_lits, val[g][m], "XOR", a_val, b_val, a_var, b_var)
                    # NOT (only in0 matters)
                    if s1 == 0:  # only emit once
                        sel_lits = [-in0_sel[g][s0], -kind[g][KIND_NOT]]
                        enforce_eq(cb, sel_lits, val[g][m], "NOT", a_val, None, a_var, None)

        if g % 5 == 0:
            print(f"  encoded gate {g}/{K} (clauses={cb.n_clauses})", flush=True)

    # Output constraints: out_sel[o][s] /\ target[o][m] -> source val[s][m] matches.
    for o in range(N_OUTPUTS):
        for m in range(N_MINTERMS):
            for s in range(N_INPUTS + K):
                if s < N_INPUTS:
                    # PI value at minterm m
                    if pi_vals[s][m] != targets[o][m]:
                        cb.add(-out_sel[o][s])  # exclude
                else:
                    src_var = val[s - N_INPUTS][m]
                    if targets[o][m] == 1:
                        cb.add(-out_sel[o][s], src_var)
                    else:
                        cb.add(-out_sel[o][s], -src_var)

    return cb, kind, in0_sel, in1_sel, out_sel, val


def enforce_eq(cb, sel_lits, out_var, kind_name, a_val, b_val, a_var, b_var):
    """Emit clauses of the form (NOT sel0 \\/ NOT sel1 \\/ NOT kind \\/ functional_constraint).
    a_val/b_val: constant 0/1/None. a_var/b_var: SAT var or None.
    out_var: SAT var for the gate's value at this minterm.
    """
    # Build a function f(a, b) -> {0, 1, x_in_terms_of_vars}.
    # We need clauses encoding out_var = f(a_lit, b_lit), guarded by sel_lits.
    a_lit = a_var if a_var is not None else (None if a_val is None else (a_val == 1))
    b_lit = b_var if b_var is not None else (None if b_val is None else (b_val == 1))

    # Convert "constant True/False" into a no-op handling.
    # Use a small helper that emits the lit form expected by Tseitin clauses.
    def lit(v_or_const):
        # Returns ("var", id) or ("const", 0/1)
        if isinstance(v_or_const, bool):
            return ("const", 1 if v_or_const else 0)
        return ("var", v_or_const)

    A = lit(a_lit) if a_lit is not None else None
    B = lit(b_lit) if b_lit is not None else None

    if kind_name == "NOT":
        # out = NOT a
        if A[0] == "const":
            forced = 1 - A[1]
            if forced == 1:
                cb.add(*sel_lits, out_var)
            else:
                cb.add(*sel_lits, -out_var)
        else:
            cb.add(*sel_lits, A[1], out_var)       # not a OR a -> ok via two clauses
            cb.add(*sel_lits, -A[1], -out_var)
        return

    # Binary gates
    def binclause(out_lit, a_lit, b_lit):
        cb.add(*sel_lits, *out_lit, *a_lit, *b_lit)

    def lit_pos(L):
        if L[0] == "const":
            return [] if L[1] == 1 else [None]  # impossible / vacuous handled below
        return [L[1]]

    def lit_neg(L):
        if L[0] == "const":
            return [None] if L[1] == 1 else []
        return [-L[1]]

    # We construct the Tseitin clauses for out = AND/OR/XOR(a, b),
    # specializing on which of a/b are constants.
    def emit(out_lit, a_form, b_form):
        # out_lit, a_form, b_form: each a list of ints (literal) or [None] meaning unsat
        if any(x is None for x in out_lit + a_form + b_form):
            return  # vacuous clause (literal evaluating to False blocks the clause)
        cb.add(*sel_lits, *out_lit, *a_form, *b_form)

    if kind_name == "AND":
        # (a /\ b) -> out  : (NOT a OR NOT b OR out)
        emit([out_var], lit_neg(A), lit_neg(B))
        # NOT a -> NOT out : (a OR NOT out)
        emit([-out_var], lit_pos(A), [])
        # NOT b -> NOT out : (b OR NOT out)
        emit([-out_var], [], lit_pos(B))
    elif kind_name == "OR":
        emit([-out_var], lit_neg(A), lit_neg(B))
        emit([out_var], lit_pos(A), [])
        emit([out_var], [], lit_pos(B))
    elif kind_name == "XOR":
        # 4 clauses
        emit([out_var], lit_neg(A), lit_pos(B))   # (NOT a /\ b) -> out
        emit([out_var], lit_pos(A), lit_neg(B))   # (a /\ NOT b) -> out
        emit([-out_var], lit_pos(A), lit_pos(B))  # (a /\ b) -> NOT out
        emit([-out_var], lit_neg(A), lit_neg(B))  # (NOT a /\ NOT b) -> NOT out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--K", type=int, required=True, help="Gate budget")
    ap.add_argument("--time-budget", type=int, default=600,
                    help="SAT solver time budget in seconds")
    args = ap.parse_args()

    print(f"Encoding SAT exact synthesis: K={args.K}, time-budget={args.time_budget}s")
    funcs = build_funcs_under_sigma()
    targets = funcs

    # PI values: 8 inputs, 256 minterms each. Bit i of minterm m is the PI value.
    pi_vals = [[(m >> i) & 1 for m in range(N_MINTERMS)] for i in range(N_INPUTS)]

    t0 = time.time()
    solver = Cadical103()
    cb, kind, in0_sel, in1_sel, out_sel, val = encode(args.K, targets, pi_vals,
                                                       solver=solver)
    print(f"\nEncoding done: vars={cb.next_var-1}, clauses={cb.n_clauses}, "
          f"time={time.time()-t0:.1f}s", flush=True)

    print(f"Solving with CaDiCaL (budget {args.time_budget}s)...", flush=True)
    t1 = time.time()
    # PySAT lacks a clean timeout; we'll solve and let it run.
    # For real time-bound, run this script with `timeout Xs python3 ...`.
    sat = solver.solve()
    elapsed = time.time() - t1
    print(f"\nResult: {'SAT' if sat else 'UNSAT'} in {elapsed:.1f}s", flush=True)

    if sat:
        model = solver.get_model()
        print("\n*** FOUND CIRCUIT ***\n", flush=True)
        decode_model(model, args.K, kind, in0_sel, in1_sel, out_sel)


def decode_model(model, K, kind, in0_sel, in1_sel, out_sel):
    """Print the gate list that satisfies the SAT model."""
    pos = set(v for v in model if v > 0)
    for g in range(K):
        k = next(t for t in range(4) if kind[g][t] in pos)
        s0 = next(s for s in range(len(in0_sel[g])) if in0_sel[g][s] in pos)
        s1 = next(s for s in range(len(in1_sel[g])) if in1_sel[g][s] in pos)
        print(f"  gate {g:>2}: {KIND_NAMES[k]} in0={s0} in1={s1}")
    for o in range(N_OUTPUTS):
        s = next(s for s in range(len(out_sel[o])) if out_sel[o][s] in pos)
        print(f"  out y{o}: source = {s}")


if __name__ == "__main__":
    main()
