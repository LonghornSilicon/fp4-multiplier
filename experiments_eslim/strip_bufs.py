"""Take a BLIF that mixes .gate and .names BUF aliases. Eliminate the BUFs
by inlining their source wherever the alias is referenced. Output a pure
.gate-form BLIF.

Usage:
  python3 strip_bufs.py IN.blif OUT.blif
"""
from __future__ import annotations
import sys


def main(in_path, out_path):
    with open(in_path) as f:
        lines = f.read().splitlines()

    inputs = []
    outputs = []
    gates = []
    aliases = {}   # dst -> src

    i = 0
    while i < len(lines):
        ln = lines[i].strip()
        i += 1
        if not ln or ln.startswith("#"): continue
        if ln.startswith(".model"):
            model = ln.split(None, 1)[1] if len(ln.split(None,1)) > 1 else "fp4_mul"
        elif ln.startswith(".inputs"):
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
            gates.append((kind, pinmap))
        elif ln.startswith(".names"):
            sigs = ln.split()[1:]
            tts = []
            while i < len(lines):
                t = lines[i].strip()
                if t.startswith(".") or not t: break
                if not t.startswith("#"): tts.append(t)
                i += 1
            if len(sigs) == 2 and tts == ["1 1"]:
                src, dst = sigs
                aliases[dst] = src
            elif len(sigs) == 2 and tts == ["0 1"]:
                # NOT alias — convert to NOT1 gate
                src, dst = sigs
                gates.append(("NOT1", {"A": src, "Y": dst}))
            elif len(sigs) == 1:
                # constant — emit as nothing (trim) but flag
                pass
        elif ln.startswith(".end"):
            break

    # Resolve aliases transitively
    def resolve(name):
        seen = set()
        while name in aliases:
            if name in seen: return name
            seen.add(name)
            name = aliases[name]
        return name

    # Apply alias resolution to all gate inputs and primary outputs
    new_outputs = [resolve(o) for o in outputs]
    new_gates = []
    for kind, pinmap in gates:
        new_pin = {}
        for k, v in pinmap.items():
            if k == "Y":
                new_pin[k] = v  # output stays as-is unless aliased
            else:
                new_pin[k] = resolve(v)
        new_gates.append((kind, new_pin))

    # Write out
    with open(out_path, "w") as f:
        f.write(".model fp4_mul\n")
        f.write(".inputs " + " ".join(inputs) + "\n")
        f.write(".outputs " + " ".join(new_outputs) + "\n")
        for kind, pinmap in new_gates:
            if kind == "NOT1":
                f.write(f".gate NOT1 A={pinmap['A']} Y={pinmap['Y']}\n")
            else:
                f.write(f".gate {kind} A={pinmap['A']} B={pinmap['B']} Y={pinmap['Y']}\n")
        f.write(".end\n")

    n_billable = len(new_gates)
    print(f"  inputs: {len(inputs)}, outputs: {len(new_outputs)}, gates: {n_billable}")
    print(f"  aliases inlined: {len(aliases)}")
    print(f"  written: {out_path}")


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("usage: python3 strip_bufs.py IN.blif OUT.blif")
        sys.exit(1)
    main(sys.argv[1], sys.argv[2])
