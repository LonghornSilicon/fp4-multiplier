#!/usr/bin/env python3
"""Convert subckt-style BLIF (using AND2/OR2/XOR2/NOT1 cells) to a flat .names BLIF."""
import re
import sys

def main(in_path, out_path):
    with open(in_path) as f:
        lines = f.readlines()

    inputs = []
    outputs = []
    # gates: list of (out, kind, inputs)
    gates = []
    # buffer lines: (out, in)
    aliases = []
    # constant gates: (out, val)
    constants = []

    i = 0
    while i < len(lines):
        line = lines[i].strip()
        i += 1
        if not line or line.startswith('#'):
            continue
        if line.startswith('.model') or line == '.end':
            continue
        if line.startswith('.inputs'):
            inputs = line.split()[1:]
            continue
        if line.startswith('.outputs'):
            outputs = line.split()[1:]
            continue
        if line.startswith('.subckt'):
            # .subckt KIND A=x B=y Y=z
            parts = line.split()
            kind = parts[1]
            pinmap = {}
            for p in parts[2:]:
                k, v = p.split('=', 1)
                pinmap[k] = v
            if kind == 'NOT1':
                gates.append((pinmap['Y'], 'NOT', [pinmap['A']]))
            elif kind == 'AND2':
                gates.append((pinmap['Y'], 'AND', [pinmap['A'], pinmap['B']]))
            elif kind == 'OR2':
                gates.append((pinmap['Y'], 'OR', [pinmap['A'], pinmap['B']]))
            elif kind == 'XOR2':
                gates.append((pinmap['Y'], 'XOR', [pinmap['A'], pinmap['B']]))
            else:
                raise ValueError(f"Unknown subckt kind: {kind}")
            continue
        if line.startswith('.names'):
            parts = line.split()[1:]
            # read truth table on subsequent lines
            tt_lines = []
            while i < len(lines) and not lines[i].strip().startswith('.') and lines[i].strip() and not lines[i].strip().startswith('#'):
                tt_lines.append(lines[i].strip())
                i += 1
            if len(parts) == 1:
                # constant gate: $false / $true / $undef
                out = parts[0]
                # if there's a "1" line -> constant 1 ; otherwise constant 0
                if any(t == '1' for t in tt_lines):
                    constants.append((out, 1))
                else:
                    constants.append((out, 0))
                continue
            if len(parts) == 2:
                # buffer: A B with line "1 1"
                src, dst = parts
                if tt_lines == ['1 1']:
                    aliases.append((dst, src))
                else:
                    raise ValueError(f"Unexpected names line: {line} / {tt_lines}")
                continue
            raise ValueError(f"Unexpected names: {line}")
            continue

    # Resolve aliases: build a map dst -> ultimate src (chasing through)
    alias_map = {}
    for dst, src in aliases:
        alias_map[dst] = src

    def resolve(name):
        seen = set()
        while name in alias_map:
            if name in seen:
                break
            seen.add(name)
            name = alias_map[name]
        return name

    const0 = set()
    const1 = set()
    for out, val in constants:
        if val == 0:
            const0.add(out)
        else:
            const1.add(out)

    # Write flat BLIF: every gate as .names with truth table
    # Resolve every gate's inputs through alias_map and convert constants
    with open(out_path, 'w') as g:
        g.write(".model fp4_mul\n")
        g.write(".inputs " + " ".join(inputs) + "\n")
        # outputs need to be the final names (likely y[0]..y[8])
        g.write(".outputs " + " ".join(outputs) + "\n")
        # For each gate, emit. But we need to handle aliases used as inputs/outputs.
        # Strategy: replace gate inputs/outputs with the alias resolution.
        # However, output variables (y[0]..y[8]) are aliased to other names — keep them as written.

        # Build a set of "real" wire names that we'll keep using.
        # For each gate (out, kind, ins):
        # - resolve inputs via alias_map, but if input resolves to const, substitute $false/$true
        # - keep gate out name as-is
        for (gout, kind, gins) in gates:
            resolved_ins = []
            const_inputs = {}
            for idx, inp in enumerate(gins):
                r = resolve(inp)
                if r in const0:
                    const_inputs[idx] = 0
                elif r in const1:
                    const_inputs[idx] = 1
                else:
                    resolved_ins.append((idx, r))
            # Build truth table based on kind and constants
            n = len(gins)
            actual_inputs = [r for _, r in resolved_ins]
            from itertools import product
            def eval_kind(vals):
                if kind == 'NOT':
                    return 1 - vals[0]
                if kind == 'AND':
                    return vals[0] & vals[1]
                if kind == 'OR':
                    return vals[0] | vals[1]
                if kind == 'XOR':
                    return vals[0] ^ vals[1]
            # Generate full truth table over actual_inputs
            num_real = len(actual_inputs)
            if num_real == 0:
                # all inputs are constants
                vals = [const_inputs[i] for i in range(n)]
                v = eval_kind(vals)
                g.write(f".names {gout}\n")
                if v == 1:
                    g.write("1\n")
                continue
            g.write(".names " + " ".join(actual_inputs) + " " + gout + "\n")
            ones = []
            for combo in product([0,1], repeat=num_real):
                full = [None]*n
                ci = iter(combo)
                for j in range(n):
                    if j in const_inputs:
                        full[j] = const_inputs[j]
                    else:
                        full[j] = next(ci)
                if eval_kind(full) == 1:
                    ones.append(combo)
            for combo in ones:
                g.write("".join(str(b) for b in combo) + " 1\n")

        # Now handle output aliases: if y[k] is aliased to some other name, emit a buffer
        for out in outputs:
            r = resolve(out)
            if r != out:
                if r in const0:
                    g.write(f".names {out}\n")
                elif r in const1:
                    g.write(f".names {out}\n1\n")
                else:
                    g.write(f".names {r} {out}\n1 1\n")

        # Handle input aliases the other direction (e.g., $abc$316$a[0] aliased from a[0])
        # If a gate uses $abc$316$a[0] it will resolve to a[0] via alias_map already handled in resolve()
        # But our alias_map is built from (dst, src) pairs from ".names src dst" lines.
        # Wait: ".names a[0] $abc$316$a[0]" means $abc$316$a[0] = a[0] (buffer of a[0]).
        # In BLIF, ".names A B" with table "1 1" means B = A. So src=A, dst=B.
        # I had aliases.append((dst, src)). resolve walks dst -> src. Good.

        g.write(".end\n")

if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
