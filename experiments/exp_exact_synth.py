"""
PySAT exact circuit synthesis — Kojevnikov et al. encoding.

Finds the minimum {AND, OR, XOR, NOT}-gate circuit for a Boolean function.
Each gate costs 1. Iterates k from 1 upward until SAT.

Usage:
    python exp_exact_synth.py sdec       -- S-decoder 3→7 (currently 13 gates)
    python exp_exact_synth.py esumdec    -- E-sum+decoder 4→7 (currently 20 gates)
    python exp_exact_synth.py mag_bit N  -- magnitude bit N: 6→1 (N in 0..7)
"""
import sys, os, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from pysat.solvers import Glucose3
from eval_circuit import FP4_TABLE

# ── Encodings ──────────────────────────────────────────────────────────────────

class ExactSynth:
    """
    Encodes the problem: "does a circuit of k gates exist for function f?"

    Variable naming (all 1-indexed SAT variables):
      sel0[g][v]  1 iff gate g's first  input comes from node v  (v in 0..N+g-1)
      sel1[g][v]  1 iff gate g's second input comes from node v
      type[g][j]  1 iff gate g has type j  (0=AND, 1=OR, 2=XOR, 3=NOT)
      val[g][t]   value of gate g's output at truth table row t

    Primary inputs (nodes 0..N-1) have fixed values from the truth table.
    Gate g is node N+g.
    """
    def __init__(self, n_in, n_out, truth_table, k):
        self.n_in = n_in
        self.n_out = n_out
        self.tt = truth_table  # list of ((inp_bits...), (out_bits...))
        self.k = k
        self.T = len(truth_table)
        self.N = n_in
        self._var = 0
        self._clauses = []

    def _new(self, count=1):
        start = self._var + 1
        self._var += count
        if count == 1:
            return self._var  # single int for single var
        return list(range(start, start + count))

    def _newvars(self, count):
        """Always returns a list of 'count' new variables."""
        start = self._var + 1
        self._var += count
        return list(range(start, start + count))

    def _clause(self, *lits):
        self._clauses.append(list(lits))

    def _exactly_one(self, lits):
        """At least one + at most one (pairwise)."""
        self._clause(*lits)  # at least one
        for i in range(len(lits)):
            for j in range(i + 1, len(lits)):
                self._clause(-lits[i], -lits[j])  # not both

    def build(self):
        n_in, n_out, k, T, N = self.n_in, self.n_out, self.k, self.T, self.N

        # sel0[g][v]: 1 iff gate g's input 0 = node v
        # sel1[g][v]: same for input 1
        # type[g][j]: j in {0=AND,1=OR,2=XOR,3=NOT}
        # val[g][t]:  value of gate g at row t

        # Allocate variables in blocks
        # sel0[g] has N+g entries  →  irregular; store as list of lists
        self.sel0 = []
        self.sel1 = []
        for g in range(k):
            n_prev = N + g  # valid input nodes for gate g
            self.sel0.append(self._new(n_prev))
            self.sel1.append(self._new(n_prev))

        self.gtype = [self._new(4) for _ in range(k)]  # 4 types each

        # val[g][t]: k × T boolean variables
        self.val = [[self._new() for _ in range(T)] for _ in range(k)]

        # ── Constraints ────────────────────────────────────────────────────────

        # 1. Exactly one input selection per gate
        for g in range(k):
            self._exactly_one(self.sel0[g])
            self._exactly_one(self.sel1[g])

        # 2. Exactly one type per gate
        for g in range(k):
            self._exactly_one(self.gtype[g])

        # 3. Gate semantics: for each gate g, row t, enforce:
        #    val[g][t] = f(type[g], val_of_in0[g][t], val_of_in1[g][t])
        #
        # We use the conditional encoding:
        #   (sel0[g][v] AND type[g][j]) => specific relation between val[g][t], node_v_t, node_w_t
        #
        # For each gate g, row t, we first compute:
        #   in0_t = value of gate g's first input at row t
        #   in1_t = same for second input
        # via the MUX encoding:
        #   (sel0[g][v]) => (in0_t == node_t[v])
        # but since in0_t is implicit, we directly encode:
        #   (sel0[g][v]) AND (val_node[v][t]) => ...
        #   (sel0[g][v]) AND (NOT val_node[v][t]) => ...

        for g in range(k):
            for t in range(T):
                vgt = self.val[g][t]
                # For each combination of (input sel, gate type), enforce output
                for v0 in range(N + g):  # first input node
                    s0v = self.sel0[g][v0]
                    val0_t = self._node_val(g, v0, t)  # ±var

                    for v1 in range(N + g):  # second input node
                        s1v = self.sel1[g][v1]
                        val1_t = self._node_val(g, v1, t)

                        # Premise: sel0==v0 AND sel1==v1
                        pre = [s0v, s1v]  # both must be positive

                        # For each gate type:
                        for jtype in range(4):
                            tj = self.gtype[g][jtype]
                            full_pre = [-s0v, -s1v, -tj]  # negate premises for implication

                            # AND: vgt <=> (v0_val AND v1_val)
                            if jtype == 0:
                                # vgt=1 => v0_val=1 AND v1_val=1
                                self._clause(*full_pre, val0_t,  -vgt)
                                self._clause(*full_pre, val1_t,  -vgt)
                                # vgt=0 => v0_val=0 OR v1_val=0
                                self._clause(*full_pre, -val0_t, -val1_t, vgt)
                            # OR: vgt <=> (v0_val OR v1_val)
                            elif jtype == 1:
                                self._clause(*full_pre, -val0_t, vgt)
                                self._clause(*full_pre, -val1_t, vgt)
                                self._clause(*full_pre, val0_t, val1_t, -vgt)
                            # XOR: vgt <=> (v0_val XOR v1_val)
                            elif jtype == 2:
                                # vgt=1 => v0≠v1
                                self._clause(*full_pre, val0_t,  val1_t,  -vgt)
                                self._clause(*full_pre, -val0_t, -val1_t, -vgt)
                                # vgt=0 => v0=v1
                                self._clause(*full_pre, val0_t,  -val1_t, vgt)
                                self._clause(*full_pre, -val0_t, val1_t,  vgt)
                            # NOT: vgt <=> NOT(v0_val)  [v1 ignored]
                            elif jtype == 3:
                                self._clause(*full_pre, val0_t,  vgt)
                                self._clause(*full_pre, -val0_t, -vgt)

        # 4. Output constraints: last n_out gates are the outputs
        for t, (_, out_bits) in enumerate(self.tt):
            for o in range(n_out):
                g_out = k - n_out + o  # gate index for output o
                v = self.val[g_out][t]
                if out_bits[o]:
                    self._clause(v)
                else:
                    self._clause(-v)

        return self._clauses

    def _node_val(self, gate_idx, node_v, row_t):
        """
        Return the SAT literal for: "node v has value 1 at row t".
        node v < N: primary input → fixed ±1 (constant literal encoding via unit clause)
        node v >= N: gate → val[v-N][t]
        """
        if node_v < self.N:
            inp_bit = self.tt[row_t][0][node_v]
            return (self._primary_lit(node_v, row_t) if inp_bit
                    else -self._primary_lit(node_v, row_t))
        else:
            return self.val[node_v - self.N][row_t]

    def _primary_lit(self, node_v, row_t):
        """
        For primary inputs we don't store variables - we use the truth table directly.
        Return +1 if inp_bit=1 (meaning "true"), return a special constant.
        Actually: we encode directly as +/- val literals.

        Since we can't use 0 as a SAT variable, we handle primary inputs specially.
        For a primary input i at row t with value 1: we return a "constant true" proxy.
        For value 0: "constant false" proxy.

        Trick: allocate a "TRUE" variable t_var and add unit clause [t_var].
        Then a primary input with value 1 = t_var, value 0 = -t_var.
        """
        return self._TRUE

    def _alloc_true(self):
        self._TRUE = self._new()
        self._clause(self._TRUE)

    def build_clean(self):
        """Cleaner build that handles primary inputs properly."""
        n_in, n_out, k, T, N = self.n_in, self.n_out, self.k, self.T, self.N

        self._alloc_true()

        # Allocate primary input value variables (per row, per input)
        # inp_var[i][t] = SAT variable for primary input i at row t
        # Fixed by unit clauses based on truth table
        self.inp_var = [[self._new() for _ in range(T)] for _ in range(N)]
        for i in range(N):
            for t, (inp_bits, _) in enumerate(self.tt):
                if inp_bits[i]:
                    self._clause(self.inp_var[i][t])
                else:
                    self._clause(-self.inp_var[i][t])

        # sel0[g], sel1[g]: one variable per possible input node
        self.sel0 = []
        self.sel1 = []
        for g in range(k):
            n_prev = N + g
            self.sel0.append(self._newvars(n_prev))
            self.sel1.append(self._newvars(n_prev))

        # gate types: [AND, OR, XOR, NOT] per gate
        self.gtype = [self._newvars(4) for _ in range(k)]

        # gate values: val[g][t]
        self.val = [[self._new() for _ in range(T)] for _ in range(k)]

        # Exactly-one constraints
        for g in range(k):
            self._exactly_one(self.sel0[g])
            self._exactly_one(self.sel1[g])
            self._exactly_one(self.gtype[g])

        # Gate semantics
        def node_var(node, t):
            """SAT variable for node 'node' at row t."""
            if node < N:
                return self.inp_var[node][t]
            else:
                return self.val[node - N][t]

        for g in range(k):
            for t in range(T):
                vgt = self.val[g][t]
                for v0 in range(N + g):
                    s0 = self.sel0[g][v0]
                    x0 = node_var(v0, t)
                    for v1 in range(N + g):
                        s1 = self.sel1[g][v1]
                        x1 = node_var(v1, t)
                        neg = [-s0, -s1]  # negate premises

                        # AND (type 0)
                        tj = self.gtype[g][0]
                        self._clause(*neg, -tj, x0,  -vgt)
                        self._clause(*neg, -tj, x1,  -vgt)
                        self._clause(*neg, -tj, -x0, -x1, vgt)
                        # OR (type 1)
                        tj = self.gtype[g][1]
                        self._clause(*neg, -tj, -x0, vgt)
                        self._clause(*neg, -tj, -x1, vgt)
                        self._clause(*neg, -tj, x0, x1, -vgt)
                        # XOR (type 2)
                        tj = self.gtype[g][2]
                        self._clause(*neg, -tj, x0,  x1,  -vgt)
                        self._clause(*neg, -tj, -x0, -x1, -vgt)
                        self._clause(*neg, -tj, x0,  -x1, vgt)
                        self._clause(*neg, -tj, -x0, x1,  vgt)
                        # NOT (type 3): ignores v1
                        tj = self.gtype[g][3]
                        self._clause(*neg, -tj, x0,  vgt)
                        self._clause(*neg, -tj, -x0, -vgt)

        # Output node selection: each output o comes from some gate (flexible)
        # out_sel[o][g]: 1 iff output o comes from gate g
        self.out_sel = []
        for o in range(n_out):
            sel = self._newvars(k)
            self.out_sel.append(sel)
            self._exactly_one(sel)

        # Output value constraints: out_sel[o][g] => (expected[o][t] == val[g][t])
        for t, (_, out_bits) in enumerate(self.tt):
            for o in range(n_out):
                for g in range(k):
                    osg = self.out_sel[o][g]
                    vg = self.val[g][t]
                    if out_bits[o]:
                        # osg=1 => val[g][t]=1
                        self._clause(-osg, vg)
                    else:
                        # osg=1 => val[g][t]=0
                        self._clause(-osg, -vg)

        return self._clauses


def try_k_gates(n_in, n_out, tt, k, timeout_s=30):
    t0 = time.time()
    es = ExactSynth(n_in, n_out, tt, k)
    clauses = es.build_clean()
    solver = Glucose3(bootstrap_with=clauses)
    status = solver.solve_limited(expect_interrupt=False)
    elapsed = time.time() - t0
    if status is True:
        model = solver.get_model()
        solver.delete()
        return True, elapsed, es, model
    else:
        solver.delete()
        return False, elapsed, None, None


def decode_solution(es, model):
    model_set = set(model)
    def is_true(v): return v in model_set

    N, k, n_out = es.n_in, es.k, es.n_out
    node_names = [f"x{i}" for i in range(N)] + [f"g{i}" for i in range(k)]
    type_names = ['AND','OR','XOR','NOT']

    gates = []
    for g in range(k):
        gtype = next(j for j in range(4) if is_true(es.gtype[g][j]))
        n_prev = N + g
        in0 = next(v for v in range(n_prev) if is_true(es.sel0[g][v]))
        in1 = next(v for v in range(n_prev) if is_true(es.sel1[g][v]))
        gates.append((type_names[gtype], in0, in1))

    # Decode output mapping
    output_nodes = []
    for o in range(n_out):
        g_out = next(g for g in range(k) if is_true(es.out_sel[o][g]))
        output_nodes.append(N + g_out)

    return gates, node_names, output_nodes


def print_gates(gates, node_names, output_nodes):
    N_base = len(node_names) - len(gates)
    for i, (tp, in0, in1) in enumerate(gates):
        n = node_names[N_base + i]
        i0 = node_names[in0]
        if tp == 'NOT':
            print(f"  {n} = NOT({i0})")
        else:
            i1 = node_names[in1]
            print(f"  {n} = {tp}({i0}, {i1})")
    outs = [node_names[o] for o in output_nodes]
    print(f"  outputs: {outs}")


def search_minimum(n_in, n_out, tt, label, start=1, stop=25):
    print(f"\n{'='*60}")
    print(f"Target: {label}  ({n_in}->{n_out}, {len(tt)} rows)")
    print(f"{'='*60}")
    for k in range(start, stop+1):
        t0 = time.time()
        print(f"  k={k:2d} ...", end="", flush=True)
        sat, elapsed, es, model = try_k_gates(n_in, n_out, tt, k)
        if sat:
            print(f" SAT! ({elapsed:.1f}s)  MINIMUM = {k} gates")
            gates, node_names, output_nodes = decode_solution(es, model)
            print_gates(gates, node_names, output_nodes)
            return k
        else:
            print(f" UNSAT ({elapsed:.1f}s)")
    print(f"  No solution found up to k={stop}")
    return None


# ── Truth table builders ───────────────────────────────────────────────────────

def make_sdec_tt():
    rows = []
    for s in range(7):  # S=7 is don't-care (impossible), skip
        inp = tuple((s >> (2-i)) & 1 for i in range(3))
        out = tuple(int(s == j) for j in range(7))
        rows.append((inp, out))
    return rows

def make_esumdec_tt():
    rows = []
    for a2 in range(2):
        for a3 in range(2):
            for b2 in range(2):
                for b3 in range(2):
                    s = 2*a2 + a3 + 2*b2 + b3
                    rows.append(((a2,a3,b2,b3), tuple(int(s==j) for j in range(7))))
    return rows

def make_mag_bit_tt(bit):
    _mag_to_code = {0.0:0,1.5:1,3.0:2,6.0:3,0.5:4,1.0:5,2.0:6,4.0:7}
    REMAP = []
    for v in FP4_TABLE:
        s = 1 if v < 0 else 0
        REMAP.append((s << 3) | _mag_to_code[abs(v)])
    seen = {}
    for a in range(16):
        for b in range(16):
            a_mag = REMAP[a] & 7; b_mag = REMAP[b] & 7
            inp = (a_mag << 3) | b_mag
            mag = int(round(abs(FP4_TABLE[a]) * abs(FP4_TABLE[b]) * 4))
            seen[inp] = mag
    rows = []
    for inp_int in range(64):
        mag = seen.get(inp_int, 0)
        inp_bits = tuple((inp_int >> (5-i)) & 1 for i in range(6))
        rows.append((inp_bits, ((mag >> bit) & 1,)))
    return rows


# ── Main ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else "sdec"

    if target == "sdec":
        tt = make_sdec_tt()
        search_minimum(3, 7, tt, "S-decoder (currently 13 gates)", start=1, stop=14)

    elif target == "esumdec":
        tt = make_esumdec_tt()
        search_minimum(4, 7, tt, "E-sum+decoder (currently 20 gates)", start=1, stop=21)

    elif target == "mag_bit":
        bit = int(sys.argv[2]) if len(sys.argv) > 2 else 0
        tt = make_mag_bit_tt(bit)
        ones = sum(1 for _, o in tt if o[0])
        search_minimum(6, 1, tt, f"Magnitude bit {bit} (6→1, {ones} ones)", start=1, stop=12)

    else:
        print(f"Unknown target '{target}'. Use: sdec | esumdec | mag_bit [N]")
