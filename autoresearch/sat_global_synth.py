"""
XOR-aware multi-output SAT synthesis (CEGIS) for FP4×FP4 → QI9.

This is an experimental tool aimed at finding *new topologies* (potentially <75 gates)
by searching directly in the {NOT, AND, OR, XOR} gate basis (all cost 1).

Key design choice: CEGIS (counterexample-guided). We synthesize a circuit that matches
the truth table on a small set of input patterns, then validate on all 256 patterns,
adding counterexamples until either:
  - we find a correct circuit, or
  - we time out / run out of iterations.

The SAT encoding uses one-hot selection for each gate's inputs among all previous wires.
This is not meant to be “fast enough for guaranteed optimality”; it is meant to be
a practical global search tool that respects XOR cost properly.
"""

from __future__ import annotations

import argparse
import os
import random
import sys
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence, Tuple

# Make repo root importable
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from eval_circuit import FP4_TABLE, build_expected_table


try:
    from pysat.solvers import Glucose3
except Exception as e:  # pragma: no cover
    raise RuntimeError(
        "PySAT not available. In WSL, install with:\n"
        "  python3 -m pip install --break-system-packages python-sat[pblib,aiger]\n"
    ) from e


# ----------------------------- SAT variable manager -----------------------------

class VarPool:
    def __init__(self) -> None:
        self.n = 0

    def new(self) -> int:
        self.n += 1
        return self.n

    def new_n(self, k: int) -> List[int]:
        return [self.new() for _ in range(k)]


def exactly_one(s: Glucose3, xs: List[int]) -> None:
    # at least one
    s.add_clause(xs)
    # at most one (pairwise)
    for i in range(len(xs)):
        xi = xs[i]
        for j in range(i + 1, len(xs)):
            s.add_clause([-xi, -xs[j]])


def add_and(s: Glucose3, out: int, a: int, b: int) -> None:
    # out <-> (a & b)
    s.add_clause([-a, -b, out])
    s.add_clause([a, -out])
    s.add_clause([b, -out])


def add_or(s: Glucose3, out: int, a: int, b: int) -> None:
    # out <-> (a | b)
    s.add_clause([a, b, -out])
    s.add_clause([-a, out])
    s.add_clause([-b, out])


def add_xor(s: Glucose3, out: int, a: int, b: int) -> None:
    # out <-> a xor b (CNF)
    s.add_clause([-a, -b, -out])
    s.add_clause([a, b, -out])
    s.add_clause([-a, b, out])
    s.add_clause([a, -b, out])


def add_not(s: Glucose3, out: int, a: int) -> None:
    # out <-> ~a
    s.add_clause([-a, -out])
    s.add_clause([a, out])


# ----------------------------- Circuit model -----------------------------

OPS = ("NOT", "AND", "OR", "XOR")


@dataclass
class SatCircuitModel:
    n_in: int
    n_gates: int
    n_out: int

    # For each gate g:
    op_sel: List[List[int]]            # [g][op] one-hot
    a_sel: List[List[int]]             # [g][wire] one-hot
    b_sel: List[List[int]]             # [g][wire] one-hot (unused for NOT but still present)

    # For each output bit:
    out_sel: List[List[int]]           # [o][wire] one-hot


def build_model(
    s: Glucose3,
    vp: VarPool,
    n_in: int,
    n_gates: int,
    n_out: int,
    *,
    window: Optional[int] = None,
) -> SatCircuitModel:
    op_sel: List[List[int]] = []
    a_sel: List[List[int]] = []
    b_sel: List[List[int]] = []
    out_sel: List[List[int]] = []

    # Gate structural vars
    for g in range(n_gates):
        op = vp.new_n(len(OPS))
        op_sel.append(op)
        exactly_one(s, op)

        # inputs can connect to previous wires:
        # - all primary inputs [0..n_in-1]
        # - plus a rolling window of the most recent gate outputs to reduce SAT size
        if window is None:
            gate_sources = list(range(n_in + g))  # all previous wires
        else:
            start_gate = max(0, g - window)
            gate_sources = list(range(n_in)) + [n_in + j for j in range(start_gate, g)]
        n_prev = len(gate_sources)
        a = vp.new_n(n_prev)
        b = vp.new_n(n_prev)
        a_sel.append(a)
        b_sel.append(b)
        exactly_one(s, a)
        exactly_one(s, b)

        # For NOT, enforce b selects a fixed dummy (wire0) to reduce symmetry a bit.
        # (NOT ignores b anyway, but this reduces branching in SAT.)
        not_idx = OPS.index("NOT")
        s.add_clause([-op[not_idx], b[0]])  # if NOT then b_sel[0]=1
        for i in range(1, n_prev):
            s.add_clause([-op[not_idx], -b[i]])

    # Output structural vars: each output taps either an input or a gate
    n_wires_total = n_in + n_gates
    for _ in range(n_out):
        sel = vp.new_n(n_wires_total)
        out_sel.append(sel)
        exactly_one(s, sel)

    return SatCircuitModel(
        n_in=n_in, n_gates=n_gates, n_out=n_out,
        op_sel=op_sel, a_sel=a_sel, b_sel=b_sel, out_sel=out_sel
    )


def add_semantics_for_patterns(
    s: Glucose3,
    vp: VarPool,
    model: SatCircuitModel,
    patterns: Sequence[int],
    expected_bits: Sequence[Sequence[int]],
) -> Tuple[List[List[List[int]]], List[List[List[int]]]]:
    """
    Add functional constraints for each input pattern.

    patterns: list of 8-bit integers (0..255)
    expected_bits[p][o] in {0,1} is expected output bit for pattern p

    Returns (wire_vals, out_vals):
      wire_vals[p][w] is SAT var for wire value of w under pattern p, for w in [0..n_in+n_gates-1]
      out_vals[p][o] is SAT var for output bit o under pattern p
    """
    n_wires_total = model.n_in + model.n_gates
    wire_vals: List[List[List[int]]] = []
    out_vals: List[List[List[int]]] = []

    # For each pattern, create wire value vars
    for pi, pat in enumerate(patterns):
        # inputs are fixed constants under this pattern; represent them as SAT vars with unit clauses
        wv = [[vp.new() for _ in range(1)] for _ in range(n_wires_total)]
        # Flatten representation to ints
        wv_ints = [x[0] for x in wv]

        # Set input bits by unit clauses (bit 7 is input0 ... bit0 is input7)
        for k in range(model.n_in):
            bit = (pat >> (7 - k)) & 1
            s.add_clause([wv_ints[k]] if bit else [-wv_ints[k]])

        # Gate outputs
        for g in range(model.n_gates):
            out_var = wv_ints[model.n_in + g]

            # Build selected input signals for this gate under this pattern using helper vars
            n_prev = len(model.a_sel[g])
            a_choices = model.a_sel[g]
            b_choices = model.b_sel[g]

            # a_val = OR_i (a_sel[i] & wv[i])
            # encode via implications with an auxiliary a_val var
            a_val = vp.new()
            b_val = vp.new()

            # a_sel[i] -> (a_val == wv[i])  using two implications:
            # a_sel -> (wv -> a_val) and a_sel -> (~wv -> ~a_val)
            for i in range(n_prev):
                sel = a_choices[i]
                # a_sel indexes directly into wv_ints (0..n_in+g-1) only when window=None.
                # With windowing, we need a deterministic mapping. We encode it via the
                # construction in build_model: sources are inputs + a suffix of gate outputs.
                # Reconstruct the same source list here.
                if n_prev == model.n_in + g:
                    src = i
                else:
                    # windowed: inputs then recent gates
                    # recent gates correspond to the last (n_prev - n_in) gates
                    if i < model.n_in:
                        src = i
                    else:
                        start_gate = g - (n_prev - model.n_in)
                        src = model.n_in + (start_gate + (i - model.n_in))
                wi = wv_ints[src]
                s.add_clause([-sel, -wi, a_val])
                s.add_clause([-sel, wi, -a_val])
            for i in range(n_prev):
                sel = b_choices[i]
                if n_prev == model.n_in + g:
                    src = i
                else:
                    if i < model.n_in:
                        src = i
                    else:
                        start_gate = g - (n_prev - model.n_in)
                        src = model.n_in + (start_gate + (i - model.n_in))
                wi = wv_ints[src]
                s.add_clause([-sel, -wi, b_val])
                s.add_clause([-sel, wi, -b_val])

            # Now op semantics: out_var equals op(a_val,b_val) depending on op selection.
            op = model.op_sel[g]
            v_not = vp.new()
            v_and = vp.new()
            v_or = vp.new()
            v_xor = vp.new()
            add_not(s, v_not, a_val)
            add_and(s, v_and, a_val, b_val)
            add_or(s, v_or, a_val, b_val)
            add_xor(s, v_xor, a_val, b_val)

            # out_var equals chosen op-result
            # For each op: op_sel -> (out == v_op)
            for sel, v in zip(op, (v_not, v_and, v_or, v_xor)):
                s.add_clause([-sel, -v, out_var])
                s.add_clause([-sel, v, -out_var])

        # Outputs
        ov = [[vp.new() for _ in range(1)] for _ in range(model.n_out)]
        ov_ints = [x[0] for x in ov]
        for o in range(model.n_out):
            sel = model.out_sel[o]
            # sel[w] -> (ov == wv[w])
            for w in range(n_wires_total):
                sw = sel[w]
                ww = wv_ints[w]
                s.add_clause([-sw, -ww, ov_ints[o]])
                s.add_clause([-sw, ww, -ov_ints[o]])

            # Constrain to expected value on this pattern
            exp = expected_bits[pi][o]
            s.add_clause([ov_ints[o]] if exp else [-ov_ints[o]])

        wire_vals.append(wv)
        out_vals.append(ov)

    return wire_vals, out_vals


def decode_model(s: Glucose3, model: SatCircuitModel) -> Dict[str, List]:
    """Extract a human-readable structural description from a SAT model."""
    m = s.get_model()
    mset = set(l for l in m if l > 0)

    def pick_one(xs: List[int]) -> int:
        for i, v in enumerate(xs):
            if v in mset:
                return i
        return 0

    gates = []
    for g in range(model.n_gates):
        op_i = pick_one(model.op_sel[g])
        op = OPS[op_i]
        a_i = pick_one(model.a_sel[g])
        b_i = pick_one(model.b_sel[g])
        gates.append((op, a_i, b_i))

    outs = []
    for o in range(model.n_out):
        w = pick_one(model.out_sel[o])
        outs.append(w)

    return {"gates": gates, "outs": outs}


# ----------------------------- Truth table generation -----------------------------

def expected_bits_for_encoding(remap: List[int]) -> List[List[int]]:
    """Return expected output bits per 8-bit remapped input index (0..255)."""
    expected = build_expected_table(remap)  # (a_code,b_code)->qi9mask
    bits = [[0] * 9 for _ in range(256)]
    for a in range(16):
        for b in range(16):
            qi9 = expected[(a, b)]
            idx = (a << 4) | b
            bits[idx] = [(qi9 >> (8 - i)) & 1 for i in range(9)]
    return bits


def random_encoding(seed: int = 0) -> List[int]:
    rng = random.Random(seed)
    arr = list(range(16))
    rng.shuffle(arr)
    return arr


def check_circuit_on_all(
    circ: Dict[str, List],
    expected_bits: List[List[int]],
    n_in: int = 8,
) -> Optional[int]:
    """
    Simulate the decoded SAT circuit on all 256 patterns.
    Returns first failing pattern index, or None if correct.
    """
    gates: List[Tuple[str, int, int]] = circ["gates"]
    outs: List[int] = circ["outs"]
    n_g = len(gates)

    for pat in range(256):
        wires = [(pat >> (7 - k)) & 1 for k in range(n_in)]
        # gate outputs appended
        for g in range(n_g):
            op, a_i, b_i = gates[g]
            a = wires[a_i]
            b = wires[b_i] if b_i < len(wires) else 0
            if op == "NOT":
                wires.append(1 - a)
            elif op == "AND":
                wires.append(a & b)
            elif op == "OR":
                wires.append(a | b)
            elif op == "XOR":
                wires.append(a ^ b)
            else:
                wires.append(0)

        out_bits = [wires[w] for w in outs]
        if out_bits != expected_bits[pat]:
            return pat
    return None


# ----------------------------- Main CEGIS loop -----------------------------

def cegis_synthesize(
    expected_bits: List[List[int]],
    n_gates: int,
    seed: int,
    max_cegis_iters: int,
    init_patterns: int,
    window: Optional[int],
    verbose: bool,
) -> Optional[Dict[str, List]]:
    rng = random.Random(seed)

    # Start with some random patterns plus a few “structured” ones.
    patterns: List[int] = []
    # Include extremes / simple rows
    patterns.extend([0x00, 0xFF, 0x0F, 0xF0, 0x33, 0xCC, 0x55, 0xAA])
    while len(patterns) < init_patterns:
        patterns.append(rng.randrange(256))
    patterns = list(dict.fromkeys(patterns))  # unique

    for it in range(max_cegis_iters):
        vp = VarPool()
        solver = Glucose3()

        model = build_model(solver, vp, n_in=8, n_gates=n_gates, n_out=9, window=window)

        exp_for_patterns = [expected_bits[p] for p in patterns]
        add_semantics_for_patterns(solver, vp, model, patterns, exp_for_patterns)

        if verbose:
            print(f"[CEGIS] iter={it} solving... patterns={len(patterns)} vars~{vp.n}", flush=True)
        sat = solver.solve()
        if not sat:
            if verbose:
                print(f"[CEGIS] UNSAT with {n_gates} gates at iter={it}, patterns={len(patterns)}")
            return None

        circ = decode_model(solver, model)
        bad = check_circuit_on_all(circ, expected_bits)
        if bad is None:
            if verbose:
                print(f"[CEGIS] FOUND correct circuit with {n_gates} gates, iters={it}, patterns={len(patterns)}")
            return circ

        patterns.append(bad)
        if verbose:
            print(f"[CEGIS] iter={it} SAT but counterexample={bad}, patterns={len(patterns)}")

    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--gates", type=int, default=78, help="gate budget to try")
    ap.add_argument("--cegis-iters", type=int, default=40)
    ap.add_argument("--init-patterns", type=int, default=24)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--encoding", choices=["random"], default="random")
    ap.add_argument("--window", type=int, default=24, help="limit each gate to depend on last W gates (+all inputs). Use 0 for inputs-only, -1 for unlimited.")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    if args.encoding == "random":
        remap = random_encoding(args.seed)
    else:
        remap = list(range(16))

    print(f"Using encoding remap(orig->new): {remap}")
    expected = expected_bits_for_encoding(remap)

    window = None if args.window < 0 else args.window

    circ = cegis_synthesize(
        expected_bits=expected,
        n_gates=args.gates,
        seed=args.seed,
        max_cegis_iters=args.cegis_iters,
        init_patterns=args.init_patterns,
        window=window,
        verbose=args.verbose,
    )

    if circ is None:
        print("No circuit found at this gate budget.")
        return

    print("Found circuit.")
    print(f"outs: {circ['outs']}")
    print("gates (op, a, b):")
    for i, g in enumerate(circ["gates"]):
        print(f"  g{i:02d}: {g}")


if __name__ == "__main__":
    main()

