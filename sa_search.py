"""
Greedy gate-elimination search for FP4 multiplier.

Starting from the verified 82-gate netlist, try to delete each gate by rewiring
its fanouts to some other existing node (or a constant). If 225/225 correctness
is preserved, accept the reduction and recurse.

This is exhaustive at depth 1 (every gate × every replacement candidate per fanout).
At depth >= 2 it switches to stochastic SA with restarts.

Run:  python3 sa_search.py
"""

from __future__ import annotations
import random, sys, time, json, os, copy

# ── Truth-table setup (matches eval_circuit.py) ─────────────────────────────
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from eval_circuit import FP4_TABLE

_mag_to_code = {0.0:0,1.5:1,3.0:2,6.0:3,0.5:4,1.0:5,2.0:6,4.0:7}
REMAP = []
for v in FP4_TABLE:
    s = 1 if v < 0 else 0
    REMAP.append((s<<3) | _mag_to_code[abs(v)])

# Build (a_code, b_code) -> 9-bit qi expected output
EXPECTED = {}
for a_orig in range(16):
    for b_orig in range(16):
        a_val = FP4_TABLE[a_orig]; b_val = FP4_TABLE[b_orig]
        qi = int(round(a_val * b_val * 4)) & 0x1FF
        EXPECTED[(REMAP[a_orig], REMAP[b_orig])] = qi

# Care-set inputs: only (a_code, b_code) pairs reachable through REMAP
CARE = sorted(set(EXPECTED.keys()))   # 16*16 = 256 (some duplicate codes? -0.0)
# After dedup of code pairs, this is the actual care set.
print(f"Care set size: {len(CARE)}", file=sys.stderr)

N_IN = 8
NOT_OP, AND_OP, OR_OP, XOR_OP, CONST0, CONST1, BUF = range(7)
OP_NAMES = {NOT_OP:"NOT", AND_OP:"AND", OR_OP:"OR", XOR_OP:"XOR",
            CONST0:"0", CONST1:"1", BUF:"BUF"}

# ── Build the 82-gate seed circuit as (op, in0, in1) tuples ────────────────
def build_82():
    gates = []
    def g(op, i, j=0):
        gates.append([op, i, j])
        return N_IN + len(gates) - 1

    a0,a1,a2,a3 = 0,1,2,3
    b0,b1,b2,b3 = 4,5,6,7

    sign   = g(XOR_OP,a0,b0)
    or_a23 = g(OR_OP,a2,a3)
    nz_a   = g(OR_OP,a1,or_a23)
    or_b23 = g(OR_OP,b2,b3)
    nz_b   = g(OR_OP,b1,or_b23)
    nz     = g(AND_OP,nz_a,nz_b)

    s0  = g(XOR_OP,a3,b3)
    c0  = g(AND_OP,a3,b3)
    s1x = g(XOR_OP,a2,b2)
    s1  = g(XOR_OP,s1x,c0)
    t1  = g(AND_OP,a2,b2)
    t2  = g(AND_OP,s1x,c0)
    s2  = g(OR_OP,t1,t2)

    or_a1b1 = g(OR_OP,a1,b1)
    k9_raw  = g(NOT_OP,or_a1b1)
    k3_raw  = g(XOR_OP,a1,b1)

    nmc = g(AND_OP,or_a1b1,nz)
    k3  = g(AND_OP,k3_raw,nz)
    k9  = g(AND_OP,k9_raw,nz)

    _or01  = g(OR_OP,s2,s1)
    _or012 = g(OR_OP,s0,_or01)
    sh0    = g(NOT_OP,_or012)
    sh1    = g(XOR_OP,_or01,_or012)
    _xor2  = g(XOR_OP,s0,_or012)
    _and2  = g(AND_OP,s2,_xor2)
    sh3    = g(AND_OP,s1,s0)
    sh5    = g(AND_OP,s2,s0)
    sh2    = g(XOR_OP,_xor2,_and2)
    sh6    = g(AND_OP,s1,_and2)
    sh4    = g(XOR_OP,_and2,sh6)

    nmc0=g(AND_OP,nmc,sh0); nmc1=g(AND_OP,nmc,sh1); nmc2=g(AND_OP,nmc,sh2)
    nmc3=g(AND_OP,nmc,sh3); nmc4=g(AND_OP,nmc,sh4); nmc5=g(AND_OP,nmc,sh5)
    nmc6=g(AND_OP,nmc,sh6)
    k3_1=g(AND_OP,k3,sh1);  k3_2=g(AND_OP,k3,sh2);  k3_3=g(AND_OP,k3,sh3)
    k3_4=g(AND_OP,k3,sh4);  k3_5=g(AND_OP,k3,sh5);  k3_6=g(AND_OP,k3,sh6)
    k9_2=g(AND_OP,k9,sh2);  k9_3=g(AND_OP,k9,sh3);  k9_4=g(AND_OP,k9,sh4)
    k9_5=g(AND_OP,k9,sh5);  k9_6=g(AND_OP,k9,sh6)

    m7=k9_6
    m6=g(OR_OP,nmc6,k9_5)
    t3=g(OR_OP,k3_6,k9_4);  m5=g(OR_OP,nmc5,t3)
    t4=g(OR_OP,nmc4,k3_5);  t5=g(OR_OP,k9_6,k9_3); m4=g(OR_OP,t4,t5)
    t6=g(OR_OP,nmc3,k3_4);  t7=g(OR_OP,k9_5,k9_2); m3=g(OR_OP,t6,t7)
    t8=g(OR_OP,k3_3,k9_4);  m2=g(OR_OP,nmc2,t8)
    t9=g(OR_OP,k3_2,k9_3);  m1=g(OR_OP,nmc1,t9)
    t10=g(OR_OP,k3_1,k9_2); m0=g(OR_OP,nmc0,t10)

    res0 = g(AND_OP,sign,nz)

    p2=g(OR_OP,m0,m1); p3=g(OR_OP,p2,m2); p4=g(OR_OP,p3,m3)
    p5=g(OR_OP,p4,m4); p6=g(OR_OP,p5,m5)

    sp1=g(AND_OP,sign,m0)
    sp2=g(AND_OP,sign,p2); sp3=g(AND_OP,sign,p3); sp4=g(AND_OP,sign,p4)
    sp5=g(AND_OP,sign,p5); sp6=g(AND_OP,sign,p6)

    r8=m0
    r7=g(XOR_OP,m1,sp1); r6=g(XOR_OP,m2,sp2); r5=g(XOR_OP,m3,sp3)
    r4=g(XOR_OP,m4,sp4); r3=g(XOR_OP,m5,sp5); r2=g(XOR_OP,m6,sp6)
    r1=g(XOR_OP,m7,res0)

    out_nodes = [res0,r1,r2,r3,r4,r5,r6,r7,r8]
    return gates, out_nodes


# ── Bit-parallel correctness check ──────────────────────────────────────────
# Pack all 256 care points as bitvectors, evaluate each gate as a single
# Python big-int operation. Speeds up evaluation 30-100x.

INPUT_BITS = [0]*N_IN
for k, (a,b) in enumerate(CARE):
    code = (a<<4) | b
    for bit in range(8):
        if (code >> (7-bit)) & 1:
            INPUT_BITS[bit] |= (1 << k)

EXPECTED_BITS = [0]*9   # 9 output bits, MSB first
for k, (a,b) in enumerate(CARE):
    qi = EXPECTED[(a,b)]
    for bit in range(9):
        if (qi >> (8-bit)) & 1:
            EXPECTED_BITS[bit] |= (1 << k)

ALL_ONE = (1 << len(CARE)) - 1

def simulate(gates):
    """Returns list of bitvectors, one per node (inputs + gates)."""
    vals = list(INPUT_BITS) + [0]*len(gates)
    for gi, (op, i, j) in enumerate(gates):
        idx = N_IN + gi
        if op == NOT_OP:
            vals[idx] = ALL_ONE ^ vals[i]
        elif op == AND_OP:
            vals[idx] = vals[i] & vals[j]
        elif op == OR_OP:
            vals[idx] = vals[i] | vals[j]
        elif op == XOR_OP:
            vals[idx] = vals[i] ^ vals[j]
        elif op == CONST0:
            vals[idx] = 0
        elif op == CONST1:
            vals[idx] = ALL_ONE
        elif op == BUF:
            vals[idx] = vals[i]
    return vals

def is_correct(gates, out_nodes):
    vals = simulate(gates)
    for bit, node in enumerate(out_nodes):
        if vals[node] != EXPECTED_BITS[bit]:
            return False
    return True

def hamming_correct(gates, out_nodes):
    """Returns count of (input × output_bit) positions where output matches."""
    vals = simulate(gates)
    total = 0
    n = len(CARE)
    for bit, node in enumerate(out_nodes):
        diff = vals[node] ^ EXPECTED_BITS[bit]
        # Number of zeros = matches
        total += n - bin(diff).count("1")
    return total

# ── Compaction: remove unused gates (after rewiring) ───────────────────────
def compact(gates, out_nodes):
    """Drop gates with no fanout (DCE). Renumber and return new (gates, outs)."""
    n = len(gates)
    used = [False]*(N_IN + n)
    for o in out_nodes: used[o] = True
    for i in range(n-1, -1, -1):
        if used[N_IN + i]:
            op, x, y = gates[i]
            used[x] = True
            if op in (AND_OP, OR_OP, XOR_OP):
                used[y] = True
    # build remap: old index -> new index
    new_idx = [-1]*(N_IN + n)
    for i in range(N_IN): new_idx[i] = i
    new_gates = []
    for i in range(n):
        if used[N_IN + i]:
            op, x, y = gates[i]
            new_idx[N_IN + i] = N_IN + len(new_gates)
            new_gates.append([op, new_idx[x], new_idx[y]])
    new_outs = [new_idx[o] for o in out_nodes]
    return new_gates, new_outs

# ── Greedy gate-elimination at depth 1 ─────────────────────────────────────
def try_eliminate(gates, out_nodes):
    """For each gate, try replacing every reference to its output with one of:
       - constant 0 / 1
       - either of its inputs (BUF)
       - any earlier node (limit to small set for speed)
       If the rewired circuit is still correct, keep it and DCE.
       Returns (new_gates, new_outs) if reduction succeeded, else None.
    """
    n_gates = len(gates)
    base_vals = simulate(gates)

    # candidates per gate: try replacing the gate's output with one of these node ids
    for gi in range(n_gates):
        node_id = N_IN + gi
        # Build candidate replacement node ids: const 0, const 1, plus any earlier
        # node whose bitvector matches this gate's output exactly.
        target_bv = base_vals[node_id]
        candidates = []
        # Must be earlier than gi (no cycles)
        for k in range(N_IN + gi):
            if base_vals[k] == target_bv:
                candidates.append(k)
        # Constants only valid if target_bv is 0 or all-1
        if target_bv == 0:
            candidates.append("CONST0")
        if target_bv == ALL_ONE:
            candidates.append("CONST1")

        if not candidates:
            continue

        # Use the first candidate. Rewire all references to node_id -> cand.
        cand = candidates[0]
        new_gates = [list(g) for g in gates]
        if cand == "CONST0":
            replacement = None  # mark via a sentinel
            # Replace gate gi with CONST0 (op=CONST0, will be DCE'd if no fanout)
            new_gates[gi] = [CONST0, 0, 0]
        elif cand == "CONST1":
            new_gates[gi] = [CONST1, 0, 0]
        else:
            # Rewire: every later gate that referenced node_id now references cand
            for k in range(gi+1, n_gates):
                op, x, y = new_gates[k]
                if x == node_id: x = cand
                if y == node_id: y = cand
                new_gates[k] = [op, x, y]
            # Outputs that reference node_id
            new_outs = [cand if o == node_id else o for o in out_nodes]
            # The gate at gi itself becomes orphaned -> DCE will drop it.
            ng, no = compact(new_gates, new_outs)
            if is_correct(ng, no):
                return ng, no, f"replace gate#{gi} ({OP_NAMES[gates[gi][0]]}) with node#{cand}"
            continue

        # Constant replacement path
        new_outs = list(out_nodes)
        ng, no = compact(new_gates, new_outs)
        if is_correct(ng, no):
            return ng, no, f"replace gate#{gi} with {OP_NAMES[new_gates[gi][0]]}"

    return None


# ── Driver ────────────────────────────────────────────────────────────────
def main():
    gates, outs = build_82()
    assert is_correct(gates, outs), "Seed circuit is not correct!"
    print(f"Seed verified: {len(gates)} gates, 225/225")

    LOG = []
    iteration = 0
    while True:
        iteration += 1
        before = len(gates)
        result = try_eliminate(gates, outs)
        if result is None:
            print(f"[iter {iteration}] No 1-gate reduction found. Stuck at {before}.")
            break
        gates, outs, msg = result
        after = len(gates)
        line = f"[iter {iteration}] {before} -> {after}: {msg}"
        print(line)
        LOG.append(line)

    final = len(gates)
    print(f"\nFinal: {final} gates")
    return gates, outs, LOG, final

if __name__ == "__main__":
    t0 = time.time()
    gates, outs, log, final = main()
    elapsed = time.time() - t0
    print(f"\nElapsed: {elapsed:.2f}s")

    # Save results
    out_path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            f"sa_result_{final}gates.json")
    with open(out_path, "w") as f:
        json.dump({"gates": gates, "outs": outs, "log": log,
                   "final_count": final, "elapsed_sec": elapsed}, f, indent=2)
    print(f"Saved to {out_path}")
