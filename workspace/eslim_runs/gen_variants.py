"""Generate gate-neutral variants of a 65-gate canonical netlist by applying
inverter-pushing rewrites. Each variant has the same gate count but a
different structural topology, giving eSLIM different starting basins.

Rewrites:
  V1. NOT(XOR(a, b)) -> XOR(NOT(a), b) when NOT(a) exists
  V2. NOT(XOR(a, b)) -> XOR(a, NOT(b)) when NOT(b) exists
  V3. AND(NOT(a), b) -> b AND NOT(a) (cosmetic permute, pad with dummy gate?)
       — no-op for our purposes since AND is commutative.
  V4. (mag XOR sy) bit-pair re-pairing — XOR is associative

For each variant we verify functional correctness against the frozen harness.
"""
from __future__ import annotations
import re
import sys
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO / "lib"))
from verify import parse_blif, verify_blif
from remap import encoding_from_magnitude_perm

VALUES = encoding_from_magnitude_perm((0, 1, 2, 3, 6, 7, 4, 5))


def write_blif(path, inputs, outputs, gates):
    """Write a .gate-form BLIF."""
    with open(path, "w") as f:
        f.write(".model fp4_mul\n")
        f.write(".inputs " + " ".join(inputs) + "\n")
        f.write(".outputs " + " ".join(outputs) + "\n")
        for out, kind, ins in gates:
            if kind == 'NOT':
                f.write(f".gate NOT1 A={ins[0]} Y={out}\n")
            elif kind == 'AND':
                f.write(f".gate AND2 A={ins[0]} B={ins[1]} Y={out}\n")
            elif kind == 'OR':
                f.write(f".gate OR2 A={ins[0]} B={ins[1]} Y={out}\n")
            elif kind == 'XOR':
                f.write(f".gate XOR2 A={ins[0]} B={ins[1]} Y={out}\n")
        f.write(".end\n")


def gate_count(gates):
    return sum(1 for g in gates if g[1] in ('NOT', 'AND', 'OR', 'XOR'))


def variant_v1_xor_negate_push(inputs, outputs, gates):
    """For each NOT gate not_x = NOT(w_x) where w_x = XOR(a, b) and NOT(a)
    exists in the netlist (or NOT(b) exists), rewrite not_x = XOR(NOT(a), b).
    Returns list of variants (one per applicable rewrite).
    """
    variants = []
    not_targets = [(i, g) for i, g in enumerate(gates) if g[1] == 'NOT']
    drv = {g[0]: (i, g[1], g[2]) for i, g in enumerate(gates)}
    not_of = {g[2][0]: g[0] for g in gates if g[1] == 'NOT'}  # source -> NOT_output

    for not_idx, (not_out, _, not_ins) in not_targets:
        src = not_ins[0]
        if src not in drv:
            continue
        di, dk, dins = drv[src]
        if dk != 'XOR':
            continue
        a, b = dins
        # If NOT(a) exists or a is a PI we can't NOT, but we want to use existing NOTs
        if a in not_of:
            new_gate = (not_out, 'XOR', [not_of[a], b])
            new_gates = gates.copy()
            new_gates[not_idx] = new_gate
            variants.append((f"v1_pushA_{not_out}", new_gates))
        if b in not_of:
            new_gate = (not_out, 'XOR', [a, not_of[b]])
            new_gates = gates.copy()
            new_gates[not_idx] = new_gate
            variants.append((f"v1_pushB_{not_out}", new_gates))
    return variants


def variant_v2_xor_associative(inputs, outputs, gates):
    """Re-associate XOR chains: XOR(XOR(a,b),c) <-> XOR(a,XOR(b,c)).
    Only safe when the intermediate XOR has fanout 1.
    """
    variants = []
    drv = {g[0]: (i, g[1], g[2]) for i, g in enumerate(gates)}
    fo = Counter()
    for g in gates:
        for s in g[2]:
            fo[s] += 1
    for o in outputs:
        fo[o] += 1
    for i, (out, kind, ins) in enumerate(gates):
        if kind != 'XOR':
            continue
        a, b = ins
        # If a is driven by XOR with fanout 1, re-associate
        if a in drv and drv[a][1] == 'XOR' and fo[a] == 1:
            ai, _, ains = drv[a]
            x, y = ains
            # out = (x ^ y) ^ b  ==  x ^ (y ^ b)
            new_inner = f"_assoc_inner_{out}"
            new_gates = [g for j, g in enumerate(gates) if j not in (ai, i)]
            new_gates.append((new_inner, 'XOR', [y, b]))
            new_gates.append((out, 'XOR', [x, new_inner]))
            variants.append((f"v2_assocA_{out}", new_gates))
        if b in drv and drv[b][1] == 'XOR' and fo[b] == 1:
            bi, _, bins = drv[b]
            x, y = bins
            new_inner = f"_assoc_inner_{out}"
            new_gates = [g for j, g in enumerate(gates) if j not in (bi, i)]
            new_gates.append((new_inner, 'XOR', [a, x]))
            new_gates.append((out, 'XOR', [new_inner, y]))
            variants.append((f"v2_assocB_{out}", new_gates))
    return variants


def main():
    if len(sys.argv) != 3:
        print("usage: gen_variants.py <input.blif> <output_dir>")
        sys.exit(1)
    in_path = Path(sys.argv[1])
    out_dir = Path(sys.argv[2])
    out_dir.mkdir(parents=True, exist_ok=True)

    p = parse_blif(in_path)
    inputs = p["inputs"]
    outputs = p["outputs"]
    gates = list(p["gates"])
    print(f"Input: {gate_count(gates)} gates")

    base_path = out_dir / f"{in_path.stem}_base.blif"
    write_blif(base_path, inputs, outputs, gates)
    ok, _ = verify_blif(str(base_path), values=VALUES)
    if not ok:
        print("FAIL: input doesn't verify")
        sys.exit(1)

    all_variants = []
    all_variants += variant_v1_xor_negate_push(inputs, outputs, gates)
    all_variants += variant_v2_xor_associative(inputs, outputs, gates)
    print(f"Generated {len(all_variants)} candidate variants. Verifying...")

    kept = 0
    for name, vgates in all_variants:
        path = out_dir / f"{in_path.stem}_{name}.blif"
        try:
            write_blif(path, inputs, outputs, vgates)
            ok, _ = verify_blif(str(path), values=VALUES)
            if ok:
                cnt = gate_count(vgates)
                kept += 1
                print(f"  KEEP {name}: {cnt} gates verified OK")
            else:
                path.unlink()
                print(f"  DROP {name}: verify FAIL")
        except Exception as e:
            path.unlink(missing_ok=True)
            print(f"  DROP {name}: {e}")
    print(f"\n{kept} variants kept in {out_dir}")


if __name__ == "__main__":
    main()
