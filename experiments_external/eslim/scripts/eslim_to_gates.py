#!/usr/bin/env python3
"""Convert eSLIM non-AIG .names BLIF to .gate-form BLIF using AND2/OR2/XOR2/NOT1.

Each .names line in the eSLIM output is a 2-input or 1-input function.
We classify it and emit the corresponding gates. For AND-with-negated-input
we share NOT gates across uses of the same negated input.

Outputs use the original net names (1..N integers from eSLIM).
"""
import sys
from collections import defaultdict

def main(in_path, out_path, in_names, out_names):
    """
    in_names: 8 strings — the 8 PI names (a[0]..a[3], b[0]..b[3]) in the
              order they appear in the eSLIM .inputs line (1..8).
    out_names: 9 strings — the 9 PO names (y[0]..y[8]) in the order they
               appear in the eSLIM .outputs line.
    """
    with open(in_path) as f:
        lines = [ln.rstrip('\n') for ln in f]

    eslim_inputs = []
    eslim_outputs = []
    gates = []  # list of (out_net, kind, inputs)
    i = 0
    n = len(lines)
    while i < n:
        ln = lines[i].strip()
        if ln.startswith('.inputs'):
            eslim_inputs = ln.split()[1:]
        elif ln.startswith('.outputs'):
            eslim_outputs = ln.split()[1:]
        elif ln.startswith('.names'):
            toks = ln.split()[1:]
            cubes = []
            j = i + 1
            while j < n and not lines[j].strip().startswith('.'):
                if lines[j].strip() and not lines[j].strip().startswith('#'):
                    cubes.append(lines[j].strip())
                j += 1
            i = j
            n_in = len(toks) - 1
            out = toks[-1]
            ins = toks[:-1]
            # Classify
            if n_in == 0:
                if cubes == []:
                    gates.append((out, 'CONST0', []))
                elif cubes == ['1']:
                    gates.append((out, 'CONST1', []))
                else:
                    raise ValueError(f"weird const: {ln} {cubes}")
            elif n_in == 1:
                if cubes == ['1 1']:
                    gates.append((out, 'BUF', ins))
                elif cubes == ['0 1']:
                    gates.append((out, 'NOT', ins))
                else:
                    raise ValueError(f"weird 1-in: {ln} {cubes}")
            elif n_in == 2:
                cset = frozenset(c.split()[0] for c in cubes)
                if cset == frozenset({'11'}):
                    gates.append((out, 'AND', ins))
                elif cset == frozenset({'01','10','11'}):
                    gates.append((out, 'OR', ins))
                elif cset == frozenset({'01','10'}):
                    gates.append((out, 'XOR', ins))
                elif cset == frozenset({'00','11'}):
                    gates.append((out, 'XNOR', ins))
                elif cset == frozenset({'00','01','10'}):
                    gates.append((out, 'NAND', ins))
                elif cset == frozenset({'00'}):
                    gates.append((out, 'NOR', ins))
                elif cset == frozenset({'01'}):  # ~A & B
                    gates.append((out, 'ANDN_A', ins))
                elif cset == frozenset({'10'}):  # A & ~B
                    gates.append((out, 'ANDN_B', ins))
                elif cset == frozenset({'00','11'}):
                    gates.append((out, 'XNOR', ins))
                elif cset == frozenset({'11','01'}):  # B (with extra constraint)
                    gates.append((out, 'BUF', [ins[1]]))
                elif cset == frozenset({'11','10'}):  # A
                    gates.append((out, 'BUF', [ins[0]]))
                elif cset == frozenset({'00','01'}):  # ~A
                    gates.append((out, 'NOT', [ins[0]]))
                elif cset == frozenset({'00','10'}):  # ~B
                    gates.append((out, 'NOT', [ins[1]]))
                else:
                    raise ValueError(f"unknown 2-in: {ln} {cset}")
            elif n_in == 3:
                cset = frozenset(c.split()[0] for c in cubes)
                # Detect XOR3 (odd parity)
                if cset == frozenset({'001','010','100','111'}):
                    gates.append((out, 'XOR3', ins))
                elif cset == frozenset({'111'}):
                    gates.append((out, 'AND3', ins))
                elif cset == frozenset({'001','010','011','100','101','110','111'}):
                    gates.append((out, 'OR3', ins))
                else:
                    raise ValueError(f"unknown 3-in: {ln} {cset}")
            else:
                raise ValueError(f"too many inputs: {n_in}")
            continue
        i += 1

    # Now build the output BLIF.
    # Map eslim wire names -> our verifier-friendly net names.
    # For PIs: use in_names mapping.
    # For internal/output nets: prefix with 'n_' (just keep eslim name if integer ok).
    assert len(eslim_inputs) == len(in_names), f"input count mismatch: {len(eslim_inputs)} vs {len(in_names)}"
    assert len(eslim_outputs) == len(out_names), f"output count mismatch: {len(eslim_outputs)} vs {len(out_names)}"

    rename = {}
    for src, dst in zip(eslim_inputs, in_names):
        rename[src] = dst
    # eslim_outputs map to out_names — but we want the gate that defines the eslim output
    # to drive the named output. Easiest: alias them.
    for src, dst in zip(eslim_outputs, out_names):
        rename[src] = dst  # we'll rewrite gate output names

    def n(name):
        # rename PIs and primary outputs; for internal nets, prefix with "w_"
        if name in rename:
            return rename[name]
        # Internal net: keep but prefix to avoid conflicts
        return f"w_{name}"

    # Allocate NOT-buffers for ANDN_A / ANDN_B sharing
    # A NOT for input wire X gets named "not_<X>"
    nots_needed = set()
    for (out, kind, ins) in gates:
        if kind == 'ANDN_A':
            nots_needed.add(ins[0])
        elif kind == 'ANDN_B':
            nots_needed.add(ins[1])

    # Write BLIF
    with open(out_path, 'w') as g:
        g.write(".model fp4_mul\n")
        g.write(".inputs " + " ".join(in_names) + "\n")
        g.write(".outputs " + " ".join(out_names) + "\n")
        # const0 / const1 if needed (use $false / $true)
        # Emit shared NOTs first
        not_names = {}
        for src in sorted(nots_needed):
            nname = f"not_{src}"
            not_names[src] = nname
            g.write(f".gate NOT1 A={n(src)} Y={nname}\n")
        # Emit gates
        for (out, kind, ins) in gates:
            nout = n(out)
            if kind == 'AND':
                g.write(f".gate AND2 A={n(ins[0])} B={n(ins[1])} Y={nout}\n")
            elif kind == 'OR':
                g.write(f".gate OR2 A={n(ins[0])} B={n(ins[1])} Y={nout}\n")
            elif kind == 'XOR':
                g.write(f".gate XOR2 A={n(ins[0])} B={n(ins[1])} Y={nout}\n")
            elif kind == 'NOT':
                g.write(f".gate NOT1 A={n(ins[0])} Y={nout}\n")
            elif kind == 'BUF':
                # implement as identity via .names
                g.write(f".names {n(ins[0])} {nout}\n1 1\n")
            elif kind == 'CONST0':
                g.write(f".names {nout}\n")
            elif kind == 'CONST1':
                g.write(f".names {nout}\n1\n")
            elif kind == 'NAND':
                # NAND = NOT(AND); add an internal AND
                aux = f"aux_{out}"
                g.write(f".gate AND2 A={n(ins[0])} B={n(ins[1])} Y={aux}\n")
                g.write(f".gate NOT1 A={aux} Y={nout}\n")
            elif kind == 'NOR':
                aux = f"aux_{out}"
                g.write(f".gate OR2 A={n(ins[0])} B={n(ins[1])} Y={aux}\n")
                g.write(f".gate NOT1 A={aux} Y={nout}\n")
            elif kind == 'XNOR':
                aux = f"aux_{out}"
                g.write(f".gate XOR2 A={n(ins[0])} B={n(ins[1])} Y={aux}\n")
                g.write(f".gate NOT1 A={aux} Y={nout}\n")
            elif kind == 'ANDN_A':  # ~A & B
                # use shared NOT
                g.write(f".gate AND2 A={not_names[ins[0]]} B={n(ins[1])} Y={nout}\n")
            elif kind == 'ANDN_B':  # A & ~B
                g.write(f".gate AND2 A={n(ins[0])} B={not_names[ins[1]]} Y={nout}\n")
            elif kind == 'XOR3':
                # XOR3(a,b,c) = XOR2(XOR2(a,b),c)
                aux = f"aux_{out}"
                g.write(f".gate XOR2 A={n(ins[0])} B={n(ins[1])} Y={aux}\n")
                g.write(f".gate XOR2 A={aux} B={n(ins[2])} Y={nout}\n")
            elif kind == 'AND3':
                aux = f"aux_{out}"
                g.write(f".gate AND2 A={n(ins[0])} B={n(ins[1])} Y={aux}\n")
                g.write(f".gate AND2 A={aux} B={n(ins[2])} Y={nout}\n")
            elif kind == 'OR3':
                aux = f"aux_{out}"
                g.write(f".gate OR2 A={n(ins[0])} B={n(ins[1])} Y={aux}\n")
                g.write(f".gate OR2 A={aux} B={n(ins[2])} Y={nout}\n")
            else:
                raise ValueError(f"Unhandled kind {kind}")
        g.write(".end\n")

    # Count gates (approx)
    # NOT shared: len(nots_needed)
    # Each gate 1 except NAND/NOR/XNOR=2, ANDN=1, AND3/OR3/XOR3=2
    count = 0
    count += len(nots_needed)
    for (out, kind, ins) in gates:
        if kind in ('AND','OR','XOR','NOT'):
            count += 1
        elif kind in ('NAND','NOR','XNOR','XOR3','AND3','OR3'):
            count += 2
        elif kind == 'ANDN_A' or kind == 'ANDN_B':
            count += 1
        elif kind in ('BUF','CONST0','CONST1'):
            count += 0
    print(f"Estimated gate count: {count}")

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("usage: eslim_to_gates.py <in.blif> <out.blif>")
        sys.exit(1)
    in_names = ['a[0]','a[1]','a[2]','a[3]','b[0]','b[1]','b[2]','b[3]']
    out_names = ['y[0]','y[1]','y[2]','y[3]','y[4]','y[5]','y[6]','y[7]','y[8]']
    main(sys.argv[1], sys.argv[2], in_names, out_names)
