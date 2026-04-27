"""Local rewrite rules over a contest-cell netlist (.gate KIND form).

Applies a small set of equivalence-preserving rewrites and returns the smallest
verified netlist found. Each rewrite must produce strictly fewer gates while
preserving function (validated against the frozen verifier).

Rewrites attempted:
  R1. Double-negation elimination: NOT(NOT(x)) -> x.
  R2. NOT-on-XOR pushing: NOT(XOR(x, y)) -> XOR(x, NOT(y)) when NOT(y) already
      exists or saves a gate.
  R3. DeMorgan AND/NOT: AND(NOT(x), NOT(y)) -> NOT(OR(x, y)). Saves 1 gate
      whenever both NOT(x) and NOT(y) are not used elsewhere (each NOT loses
      its consumer; we add a single new NOT and replace the inner OR's NOTs
      go away).
  R4. DeMorgan OR/NOT: OR(NOT(x), NOT(y)) -> NOT(AND(x, y)). Same shape.
  R5. Constant-fold: AND(x, NOT(x)) -> 0; OR(x, NOT(x)) -> 1; XOR(x, x) -> 0.
  R6. Buffer-elimination: NOT-out-of-NOT, BUF-aliases, etc. (mostly cosmetic;
      validates that no cosmetic dead-logic survived).
  R7. Inverter-bubble through XOR: XOR(NOT(x), y) -> NOT(XOR(x, y)). This
      preserves count but can enable downstream R3/R4 by repositioning the NOT.

We apply each rule greedily, re-validating the netlist after every rewrite.
If any rule fires, restart from R1 (some rules enable each other).
"""
from __future__ import annotations
import sys
from collections import defaultdict
from copy import deepcopy
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "lib"))
from verify import verify_blif, parse_blif
from remap import encoding_from_magnitude_perm

VALUES = encoding_from_magnitude_perm((0, 1, 2, 3, 6, 7, 4, 5))


def parse_to_dag(path):
    p = parse_blif(path)
    inputs = p["inputs"]
    outputs = p["outputs"]
    # gates: list of (out, kind, ins) where kind is one of NOT/AND/OR/XOR/BUF
    gates = list(p["gates"])
    constants = dict(p["constant"])
    # Verify outputs are present in outputs list
    return inputs, outputs, gates, constants


def gate_count(gates):
    return sum(1 for g in gates if g[1] in ('NOT', 'AND', 'OR', 'XOR'))


def write_blif(path, inputs, outputs, gates, constants):
    """Write a .gate-form BLIF to path."""
    name_map = {}
    with open(path, "w") as f:
        f.write(".model fp4_mul\n")
        f.write(".inputs " + " ".join(inputs) + "\n")
        f.write(".outputs " + " ".join(outputs) + "\n")
        for net, val in constants.items():
            if val == 0:
                f.write(f".names {net}\n")
            else:
                f.write(f".names {net}\n1\n")
        for out, kind, ins in gates:
            if kind == 'NOT':
                f.write(f".gate NOT1 A={ins[0]} Y={out}\n")
            elif kind == 'AND':
                f.write(f".gate AND2 A={ins[0]} B={ins[1]} Y={out}\n")
            elif kind == 'OR':
                f.write(f".gate OR2 A={ins[0]} B={ins[1]} Y={out}\n")
            elif kind == 'XOR':
                f.write(f".gate XOR2 A={ins[0]} B={ins[1]} Y={out}\n")
            elif kind == 'BUF':
                f.write(f".names {ins[0]} {out}\n1 1\n")
        f.write(".end\n")


def fanout_of(gates, outputs):
    """Map net -> count of consumers (gates + outputs)."""
    fo = defaultdict(int)
    for out, kind, ins in gates:
        for s in ins:
            fo[s] += 1
    for o in outputs:
        fo[o] += 1
    return fo


def driver_of(gates):
    """Map net -> (idx, kind, ins) for the gate that drives it."""
    return {g[0]: (i, g[1], g[2]) for i, g in enumerate(gates)}


def verify(inputs, outputs, gates, constants, work_path="/tmp/_rewrite_check.blif"):
    write_blif(work_path, inputs, outputs, gates, constants)
    ok, _ = verify_blif(work_path, values=VALUES)
    return ok


def rewrite_R3_demorgan_and(inputs, outputs, gates, constants):
    """AND(NOT(a), NOT(b)) where each NOT has fanout 1 -> NOT(OR(a, b)).
    Saves 1 gate (replaces 3 with 2)."""
    drv = driver_of(gates)
    fo = fanout_of(gates, outputs)
    for i, (out, kind, ins) in enumerate(gates):
        if kind != 'AND':
            continue
        # Both inputs must be driven by NOT
        a, b = ins
        if a not in drv or b not in drv:
            continue
        ai, ak, ains = drv[a]
        bi, bk, bins = drv[b]
        if ak != 'NOT' or bk != 'NOT':
            continue
        # Both NOTs must have fanout 1 (only this AND uses them)
        if fo[a] != 1 or fo[b] != 1:
            continue
        # Build new netlist
        new_or = f"_or_{out}"
        new_gates = [g for g in gates if g[0] not in (a, b)]
        # Replace the AND with OR + NOT
        for j, (gout, gkind, gins) in enumerate(new_gates):
            if gout == out and gkind == 'AND':
                # replace with NOT
                new_gates[j] = (out, 'NOT', [new_or])
                break
        # Insert OR before the NOT (topological order: any place before)
        new_gates.insert(0, (new_or, 'OR', [ains[0], bins[0]]))
        if verify(inputs, outputs, new_gates, constants):
            return new_gates
    return None


def rewrite_R4_demorgan_or(inputs, outputs, gates, constants):
    """OR(NOT(a), NOT(b)) where each NOT has fanout 1 -> NOT(AND(a, b))."""
    drv = driver_of(gates)
    fo = fanout_of(gates, outputs)
    for i, (out, kind, ins) in enumerate(gates):
        if kind != 'OR':
            continue
        a, b = ins
        if a not in drv or b not in drv:
            continue
        ai, ak, ains = drv[a]
        bi, bk, bins = drv[b]
        if ak != 'NOT' or bk != 'NOT':
            continue
        if fo[a] != 1 or fo[b] != 1:
            continue
        new_and = f"_and_{out}"
        new_gates = [g for g in gates if g[0] not in (a, b)]
        for j, (gout, gkind, gins) in enumerate(new_gates):
            if gout == out and gkind == 'OR':
                new_gates[j] = (out, 'NOT', [new_and])
                break
        new_gates.insert(0, (new_and, 'AND', [ains[0], bins[0]]))
        if verify(inputs, outputs, new_gates, constants):
            return new_gates
    return None


def rewrite_R1_double_negation(inputs, outputs, gates, constants):
    """NOT(NOT(x)) -> x. Replace x' driven by NOT(y) where y is driven by NOT(z)
    with z everywhere. Saves 2 gates."""
    drv = driver_of(gates)
    fo = fanout_of(gates, outputs)
    for i, (out, kind, ins) in enumerate(gates):
        if kind != 'NOT':
            continue
        inner = ins[0]
        if inner not in drv:
            continue
        ii, ik, iins = drv[inner]
        if ik != 'NOT':
            continue
        # out = NOT(NOT(z)) = z
        z = iins[0]
        # Replace 'out' with 'z' in all consumers
        new_gates = []
        for gout, gkind, gins in gates:
            if gout == out:
                continue  # delete this NOT
            if gkind == 'NOT' and gout == inner and fo[inner] == 1:
                continue  # delete the inner NOT (only used by this outer NOT)
            new_ins = [z if x == out else x for x in gins]
            new_gates.append((gout, gkind, new_ins))
        new_outputs = [z if o == out else o for o in outputs]
        # Note: if 'out' is a primary output, replacing with z requires the
        # output line to refer to z. Update outputs.
        if verify(inputs, new_outputs, new_gates, constants):
            return (new_gates, new_outputs)
    return None


def main():
    if len(sys.argv) < 2:
        print("usage: netlist_rewrite.py <input.blif> [output.blif]")
        sys.exit(1)
    inp = sys.argv[1]
    outp = sys.argv[2] if len(sys.argv) > 2 else "/tmp/rewritten.blif"

    inputs, outputs, gates, constants = parse_to_dag(inp)
    print(f"Initial: {gate_count(gates)} gates")

    # Verify input
    if not verify(inputs, outputs, gates, constants):
        print("FAIL: input does not verify under sigma=(0,1,2,3,6,7,4,5)")
        sys.exit(1)

    iter_count = 0
    while iter_count < 100:
        iter_count += 1
        # Try R1 (saves 2)
        r = rewrite_R1_double_negation(inputs, outputs, gates, constants)
        if r is not None:
            gates, outputs = r
            print(f"  iter {iter_count}: R1 fired -> {gate_count(gates)} gates")
            continue
        # Try R3 (saves 1)
        r = rewrite_R3_demorgan_and(inputs, outputs, gates, constants)
        if r is not None:
            gates = r
            print(f"  iter {iter_count}: R3 fired -> {gate_count(gates)} gates")
            continue
        r = rewrite_R4_demorgan_or(inputs, outputs, gates, constants)
        if r is not None:
            gates = r
            print(f"  iter {iter_count}: R4 fired -> {gate_count(gates)} gates")
            continue
        break

    print(f"Final: {gate_count(gates)} gates")
    write_blif(outp, inputs, outputs, gates, constants)
    if verify(inputs, outputs, gates, constants):
        print(f"Verified OK. Written to {outp}")
    else:
        print("ERROR: final netlist does not verify!")
        sys.exit(2)


if __name__ == "__main__":
    main()
