"""Take a .gate-form BLIF (post eslim_to_gates translation), parse it,
build a Python multiplier function from it, and verify against
eval_circuit.evaluate_fast using Longhorn's σ remap.

Usage:
  python3 experiments_eslim/blif_verify.py /path/to/some.blif
"""
from __future__ import annotations
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)) + "/..")

from eval_circuit import FP4_TABLE, evaluate_fast


_mag_to_code_long = {
    0.0: 0b0000, 0.5: 0b0001, 1.0: 0b0010, 1.5: 0b0011,
    2.0: 0b0110, 3.0: 0b0111, 4.0: 0b0100, 6.0: 0b0101,
}
INPUT_REMAP = []
for v in FP4_TABLE:
    s = 1 if v < 0 else 0
    INPUT_REMAP.append((s << 3) | _mag_to_code_long[abs(v)])


def parse_gate_blif(path):
    """Returns (inputs, outputs, gates).

    Handles three line types:
      - .gate KIND A=x B=y Y=z   → AND2/OR2/XOR2/NOT1 cells (each = 1 gate)
      - .names X Y               → followed by '1 1' = BUF (alias, 0 cost)
      - .names Y                 → followed by '1' or empty = const1/const0 (0 cost)
    """
    with open(path) as f:
        lines = f.read().splitlines()
    inputs, outputs, gates = [], [], []
    i = 0
    n = len(lines)
    while i < n:
        ln = lines[i].strip()
        i += 1
        if not ln or ln.startswith("#"): continue
        if ln.startswith(".inputs"):
            inputs = ln.split()[1:]
        elif ln.startswith(".outputs"):
            outputs = ln.split()[1:]
        elif ln.startswith(".gate"):
            parts = ln.split()
            kind = parts[1]
            pinmap = {}
            for p in parts[2:]:
                k, v = p.split("=", 1)
                pinmap[k] = v
            if kind == "NOT1":
                gates.append((kind, pinmap["Y"], [pinmap["A"]]))
            elif kind in ("AND2", "OR2", "XOR2"):
                gates.append((kind, pinmap["Y"], [pinmap["A"], pinmap["B"]]))
        elif ln.startswith(".names"):
            sigs = ln.split()[1:]
            tts = []
            while i < n:
                t = lines[i].strip()
                if t.startswith(".") or not t:
                    break
                if not t.startswith("#"):
                    tts.append(t)
                i += 1
            if len(sigs) == 2:
                src, dst = sigs
                if tts == ["1 1"]:
                    # BUF: dst = src
                    gates.append(("BUF", dst, [src]))
                elif tts == ["0 1"]:
                    # NOT via .names form
                    gates.append(("NOT1", dst, [src]))
            elif len(sigs) == 1:
                dst = sigs[0]
                if tts == ["1"]:
                    gates.append(("CONST1", dst, []))
                elif tts == [] or tts == ["0"]:
                    gates.append(("CONST0", dst, []))
        elif ln.startswith(".end"):
            break
    return inputs, outputs, gates


def topo_sort_gates(gates, inputs):
    """Sort gates so each gate's inputs are computed before it."""
    known = set(inputs)
    # Also recognize alternate naming
    alt = set()
    for n in inputs:
        # e.g., "a[0]" -> "a0"
        if "[" in n:
            alt.add(n.replace("[", "").replace("]", ""))
        else:
            alt.add(n)
    known |= alt

    sorted_gates = []
    pending = list(gates)
    last_pending = None
    while pending:
        progress = False
        next_pending = []
        for g in pending:
            kind, out, ins = g
            if all(i in known for i in ins):
                sorted_gates.append(g)
                known.add(out)
                progress = True
            else:
                next_pending.append(g)
        if not progress:
            raise RuntimeError(f"Cyclic / unresolvable gates: "
                              f"{[g[1] for g in next_pending]}")
        pending = next_pending
    return sorted_gates


def make_multiplier(blif_path):
    inputs, outputs, gates = parse_gate_blif(blif_path)
    gates = topo_sort_gates(gates, inputs)

    # Their convention: a[3]=sign, a[0]=LSB. Notebook: a0=sign, a3=LSB.
    # Build a function that takes (a0,a1,a2,a3,b0,b1,b2,b3) in NOTEBOOK
    # convention and translates to their convention internally.

    def multiplier(a0, a1, a2, a3, b0, b1, b2, b3,
                   NOT=None, AND=None, OR=None, XOR=None):
        if NOT is None:
            NOT = lambda x: not x
            AND = lambda x, y: x & y
            OR  = lambda x, y: x | y
            XOR = lambda x, y: x ^ y
        # Their convention: a[3]=sign, a[0]=LSB. Reverse from notebook.
        their_a = {"a[3]": a0, "a[2]": a1, "a[1]": a2, "a[0]": a3,
                   "b[3]": b0, "b[2]": b1, "b[1]": b2, "b[0]": b3}
        # Some BLIFs may use different naming; try both
        # We accept either a0,a1,..a3 or a[0]..a[3]
        wires = dict(their_a)
        # Also fill alternate names
        wires["a0"] = a3; wires["a1"] = a2; wires["a2"] = a1; wires["a3"] = a0
        wires["b0"] = b3; wires["b1"] = b2; wires["b2"] = b1; wires["b3"] = b0

        for kind, out, ins in gates:
            in_vals = [wires[i] for i in ins]
            if kind == "NOT1":
                wires[out] = NOT(in_vals[0])
            elif kind == "AND2":
                wires[out] = AND(in_vals[0], in_vals[1])
            elif kind == "OR2":
                wires[out] = OR(in_vals[0], in_vals[1])
            elif kind == "XOR2":
                wires[out] = XOR(in_vals[0], in_vals[1])
            elif kind == "BUF":
                wires[out] = in_vals[0]
            elif kind == "CONST0":
                wires[out] = 0
            elif kind == "CONST1":
                wires[out] = 1

        # Outputs are y[0]..y[8]; the assignment expects MSB first.
        out_vals = [wires[o] for o in outputs]
        # outputs are listed y[0]..y[8] (LSB first in their convention).
        # Notebook expects (res0=MSB, ..., res8=LSB), so reverse if needed.
        # In Longhorn submission, return order is y8, y7, ..., y0 (MSB first).
        if outputs == [f"y[{i}]" for i in range(9)]:
            return tuple(out_vals[::-1])  # y[8], y[7], ..., y[0]
        else:
            return tuple(out_vals)

    return multiplier, len(gates)


def main():
    if len(sys.argv) < 2:
        print("usage: python3 blif_verify.py <path_to.blif>")
        sys.exit(1)
    blif = sys.argv[1]
    mult, n_gates = make_multiplier(blif)
    # Count only billable cells (BUF / CONST are 0 cost)
    inputs, outputs, gates = parse_gate_blif(blif)
    n_billable = sum(1 for g in gates if g[0] in ("AND2","OR2","XOR2","NOT1"))
    n_buf = sum(1 for g in gates if g[0] == "BUF")
    n_const = sum(1 for g in gates if g[0] in ("CONST0","CONST1"))
    print(f"Loaded {blif}")
    print(f"  billable cells (AND2/OR2/XOR2/NOT1): {n_billable}")
    print(f"  BUF aliases (free): {n_buf}")
    print(f"  consts (free): {n_const}")
    print(f"  total parsed: {n_gates}")
    correct, gc, errs = evaluate_fast(mult, INPUT_REMAP)
    print(f"Verified gate count via eval_circuit (counts NOT/AND/OR/XOR calls): {gc}")
    print(f"Correct: {correct}, errors: {len(errs)}")
    if not correct:
        for e in errs[:5]: print("   error:", e)
        sys.exit(1)


if __name__ == "__main__":
    main()
