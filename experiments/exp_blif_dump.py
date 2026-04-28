"""
Convert the 84-gate Python multiplier to a BLIF netlist by gate-tracing.

Strategy:
  - Monkey-patch NOT/AND/OR/XOR to record (out_label, op, *operands).
  - Each call returns a fresh symbolic Node whose label is g0, g1, g2, ...
  - Run write_your_multiplier_here once with symbolic inputs a0..b3.
  - Emit BLIF: .inputs, .outputs (res0..r8), one .names cube per gate.

Save: experiments/data/v4d_84gates.blif
"""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "autoresearch"))

from autoresearch.multiplier import write_your_multiplier_here


class Node:
    __slots__ = ("name",)
    def __init__(self, name):
        self.name = name
    def __repr__(self):
        return f"Node({self.name})"


def trace():
    gates = []  # list of (out_name, op, *operand_names)
    counter = [0]

    def fresh():
        n = f"g{counter[0]}"
        counter[0] += 1
        return n

    def _name(x):
        if isinstance(x, Node):
            return x.name
        # boolean constant fallback
        if x is True or x is False or x == 0 or x == 1:
            return "ONE" if x else "ZERO"
        raise TypeError(f"unexpected operand: {x!r}")

    def NOT(x):
        out = fresh()
        gates.append((out, "NOT", _name(x)))
        return Node(out)

    def AND(x, y):
        out = fresh()
        gates.append((out, "AND", _name(x), _name(y)))
        return Node(out)

    def OR(x, y):
        out = fresh()
        gates.append((out, "OR", _name(x), _name(y)))
        return Node(out)

    def XOR(x, y):
        out = fresh()
        gates.append((out, "XOR", _name(x), _name(y)))
        return Node(out)

    inputs = [Node(n) for n in ("a0", "a1", "a2", "a3", "b0", "b1", "b2", "b3")]
    outputs = write_your_multiplier_here(*inputs, NOT=NOT, AND=AND, OR=OR, XOR=XOR)
    out_names = [_name(o) for o in outputs]
    return gates, out_names


def to_blif(gates, out_names, model="v4d_84gates"):
    lines = []
    lines.append(f".model {model}")
    lines.append(".inputs a0 a1 a2 a3 b0 b1 b2 b3")
    out_labels = ["res0", "r1", "r2", "r3", "r4", "r5", "r6", "r7", "r8"]
    lines.append(".outputs " + " ".join(out_labels))

    # Map from internal gate name -> output port (for outputs that are simple wire passthroughs).
    # We will rename the final gate names to the output labels so they appear directly.
    # But m0 (r8) is *not* a gate, it's an OR result already named e.g. g??.
    # Easiest: emit each gate by its internal name, then for outputs add aliasing .names lines.
    aliases = []  # list of (out_label, internal_name)
    for label, internal in zip(out_labels, out_names):
        aliases.append((label, internal))

    for g in gates:
        out, op = g[0], g[1]
        if op == "NOT":
            (a,) = g[2:]
            lines.append(f".names {a} {out}")
            lines.append("0 1")
        elif op == "AND":
            a, b = g[2:]
            lines.append(f".names {a} {b} {out}")
            lines.append("11 1")
        elif op == "OR":
            a, b = g[2:]
            lines.append(f".names {a} {b} {out}")
            lines.append("1- 1")
            lines.append("-1 1")
        elif op == "XOR":
            a, b = g[2:]
            lines.append(f".names {a} {b} {out}")
            lines.append("01 1")
            lines.append("10 1")
        else:
            raise ValueError(op)

    # Output aliases: e.g., r8 = m0 (which is some g? wire). Buffer cube.
    for label, internal in aliases:
        if label == internal:
            continue
        lines.append(f".names {internal} {label}")
        lines.append("1 1")

    lines.append(".end")
    return "\n".join(lines) + "\n"


def main():
    gates, out_names = trace()
    print(f"Traced {len(gates)} gates")
    op_counts = {}
    for g in gates:
        op_counts[g[1]] = op_counts.get(g[1], 0) + 1
    print(f"Op counts: {op_counts}")
    print(f"Outputs (internal names): {out_names}")

    blif = to_blif(gates, out_names)
    out_path = os.path.join(ROOT, "experiments", "data", "v4d_84gates.blif")
    with open(out_path, "w") as f:
        f.write(blif)
    print(f"Wrote {out_path}")
    print(f"BLIF lines: {len(blif.splitlines())}")


if __name__ == "__main__":
    main()
