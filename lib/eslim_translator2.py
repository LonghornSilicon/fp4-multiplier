"""Improved eSLIM-internal -> contest-cell translator.

The legacy translator (experiments_external/eslim/scripts/eslim_to_gates.py)
emits one shared NOT for each distinct inverted input used in ANDN_A/ANDN_B
gates. With the canonical 58-internal solution, that adds 7 NOTs -> 65 total.

This translator additionally applies:

  (1) DeMorgan: NAND(a,b) = OR(~a, ~b) when both ~a and ~b already exist
      as primitive NOTs (no new NOT introduced) -> save 1 gate (skip the
      auxiliary AND).
  (2) XNOR/XOR sharing: if XNOR(a,b) is needed and XOR(a,b) is already in
      the netlist (or trivially expressible), reuse it.
  (3) Inverter pushing: if ANDN_A(x, y) drives a XOR2(x AND ?, ...) chain,
      try to bubble the inversion through the XOR (XOR(~x, y) = ~XOR(x, y))
      to eliminate the explicit NOT. ABC won't do this rewrite because it
      changes structural cone but preserves semantics.
  (4) Dual-input ANDN sharing: ANDN_A(x, y) AND ANDN_A(x, z) share NOT(x).
      Already in legacy. Extended: ANDN_A(x,y) AND ANDN_B(z,x) also share.
  (5) Output-feeding inversion sink: if a NOT feeds *only* a single output
      Y[k], and Y[k] = NOT(z), we can express z as the "correct polarity"
      output of an upstream XOR (toggle one input). This requires upstream
      analysis.

For now we implement (1), (2), (4) which are local. (3) and (5) require
larger graph rewrites and are more invasive.

Verification: any output of this translator MUST pass the same frozen
verify_blif as the original. The translator is purely cosmetic — same
function, fewer cells.
"""
from __future__ import annotations
import sys
from collections import defaultdict, Counter
from pathlib import Path


def parse_eslim_blif(path):
    """Parse eSLIM's flat .names BLIF output. Returns (inputs, outputs, gates).
    gates: list of (out_net, kind, [in_nets]).
    Recognized kinds match eslim_to_gates: AND, OR, XOR, NOT, NAND, NOR,
    XNOR, ANDN_A (~a & b), ANDN_B (a & ~b), BUF, CONST0, CONST1, AND3, OR3,
    XOR3.
    """
    with open(path) as f:
        lines = [ln.rstrip() for ln in f]

    inputs = []
    outputs = []
    gates = []
    i = 0
    n = len(lines)
    while i < n:
        ln = lines[i].strip()
        if ln.startswith('.inputs'):
            inputs = ln.split()[1:]
            i += 1
        elif ln.startswith('.outputs'):
            outputs = ln.split()[1:]
            i += 1
        elif ln.startswith('.names'):
            toks = ln.split()[1:]
            cubes = []
            j = i + 1
            while j < n and not lines[j].strip().startswith('.'):
                t = lines[j].strip()
                if t and not t.startswith('#'):
                    cubes.append(t)
                j += 1
            i = j
            n_in = len(toks) - 1
            out = toks[-1]
            ins = toks[:-1]
            kind = classify(n_in, cubes)
            gates.append((out, kind, ins))
        else:
            i += 1
    return inputs, outputs, gates


def classify(n_in, cubes):
    if n_in == 0:
        if not cubes:
            return ('CONST0', [])
        if cubes == ['1']:
            return ('CONST1', [])
        raise ValueError(f"Bad const: {cubes}")
    if n_in == 1:
        if cubes == ['1 1']:
            return ('BUF',)
        if cubes == ['0 1']:
            return ('NOT',)
        raise ValueError(f"Bad 1-in: {cubes}")
    if n_in == 2:
        cset = frozenset(c.split()[0] for c in cubes)
        if cset == frozenset({'11'}):
            return ('AND',)
        if cset == frozenset({'01', '10', '11'}):
            return ('OR',)
        if cset == frozenset({'01', '10'}):
            return ('XOR',)
        if cset == frozenset({'00', '11'}):
            return ('XNOR',)
        if cset == frozenset({'00', '01', '10'}):
            return ('NAND',)
        if cset == frozenset({'00'}):
            return ('NOR',)
        if cset == frozenset({'01'}):
            return ('ANDN_A',)
        if cset == frozenset({'10'}):
            return ('ANDN_B',)
        if cset == frozenset({'11', '01'}):
            return ('BUF_B',)
        if cset == frozenset({'11', '10'}):
            return ('BUF_A',)
        if cset == frozenset({'00', '01'}):
            return ('NOT_A',)
        if cset == frozenset({'00', '10'}):
            return ('NOT_B',)
        raise ValueError(f"Unknown 2-in: {cset}")
    if n_in == 3:
        cset = frozenset(c.split()[0] for c in cubes)
        if cset == frozenset({'001', '010', '100', '111'}):
            return ('XOR3',)
        if cset == frozenset({'111'}):
            return ('AND3',)
        if cset == frozenset({'001', '010', '011', '100', '101', '110', '111'}):
            return ('OR3',)
        raise ValueError(f"Unknown 3-in: {cset}")
    raise ValueError(f"too many inputs: {n_in}")


def translate(in_path, out_path, in_names, out_names, verbose=False):
    """Translate eSLIM flat BLIF to contest-cell BLIF.

    Returns (cell_counts: dict, total: int).
    """
    inputs, outputs, gates = parse_eslim_blif(in_path)
    assert len(inputs) == len(in_names)
    assert len(outputs) == len(out_names)
    rename = {}
    for src, dst in zip(inputs, in_names):
        rename[src] = dst
    for src, dst in zip(outputs, out_names):
        rename[src] = dst

    def n(name):
        if name in rename:
            return rename[name]
        return f"w_{name}"

    # First pass: collect which signals have NOTs available (existing inverter)
    # Each gate's output net x has been seen.
    # We need to know "signal s is available as ~s in the current netlist"
    # before deciding whether ANDN_A(s, t) introduces a new NOT.
    explicit_nots = {}  # src -> NOT_output_net_name
    for (out, kind, ins) in gates:
        if kind == ('NOT',):
            explicit_nots[ins[0]] = out

    # Demand for "negated input" — count how many distinct sources need ~src.
    # Sources: from ANDN_A (ins[0]), ANDN_B (ins[1]), NAND (both expanded as
    # ~AND output, so don't count), NOR (~OR output), XNOR (~XOR output),
    # NOT_A, NOT_B (single-input expressed as 2-in NOT), and any explicit NOT.
    neg_demand = Counter()  # source signal -> number of uses requiring ~it
    for (out, kind, ins) in gates:
        k = kind[0] if isinstance(kind, tuple) else kind
        if k == 'ANDN_A':
            neg_demand[ins[0]] += 1
        elif k == 'ANDN_B':
            neg_demand[ins[1]] += 1
        elif k == 'NOT':
            neg_demand[ins[0]] += 1
        elif k == 'NOT_A':
            neg_demand[ins[0]] += 1
        elif k == 'NOT_B':
            neg_demand[ins[1]] += 1

    # Allocate shared NOTs. Always emit one shared NOT per distinct source
    # whose negated form is needed at least once.
    shared_nots = {}  # src -> not_name
    not_count = 0
    for src in sorted(neg_demand):
        nname = f"not_{src}"
        shared_nots[src] = nname
        not_count += 1

    # Build cell list
    cells = []  # list of (kind, [pins], out)
    cell_counts = Counter()

    # Emit shared NOTs
    for src, nname in shared_nots.items():
        cells.append(('NOT1', [n(src)], nname))
        cell_counts['NOT1'] += 1

    def get_neg(s):
        return shared_nots[s]

    # Replace gate output names: any wire that's an alias for an output
    # name should write directly to the output. Collect aliases first.
    alias_to_output = {}
    for src, dst in zip(outputs, out_names):
        # dst is the canonical name; src may be an internal eSLIM name we
        # need to alias.
        pass

    for (out, kind, ins) in gates:
        k = kind[0] if isinstance(kind, tuple) else kind
        nout = n(out)
        if k == 'AND':
            cells.append(('AND2', [n(ins[0]), n(ins[1])], nout))
            cell_counts['AND2'] += 1
        elif k == 'OR':
            cells.append(('OR2', [n(ins[0]), n(ins[1])], nout))
            cell_counts['OR2'] += 1
        elif k == 'XOR':
            cells.append(('XOR2', [n(ins[0]), n(ins[1])], nout))
            cell_counts['XOR2'] += 1
        elif k == 'NOT':
            # Alias to shared NOT. Use a buffer if names differ.
            shared = shared_nots[ins[0]]
            if shared != nout:
                cells.append(('BUF_NAMES', [shared], nout))
            # The shared NOT was already counted.
        elif k == 'BUF' or k == 'BUF_A' or k == 'BUF_B':
            src = ins[0] if k != 'BUF_B' else ins[1]
            cells.append(('BUF_NAMES', [n(src)], nout))
        elif k == 'CONST0':
            cells.append(('CONST0', [], nout))
        elif k == 'CONST1':
            cells.append(('CONST1', [], nout))
        elif k == 'NAND':
            # NAND(a,b) = OR(~a, ~b) if both ~a and ~b are shared
            # Otherwise NAND(a,b) = NOT(AND(a,b))
            sa, sb = ins[0], ins[1]
            if sa in shared_nots and sb in shared_nots:
                cells.append(('OR2', [shared_nots[sa], shared_nots[sb]], nout))
                cell_counts['OR2'] += 1
            else:
                aux = f"aux_{out}"
                cells.append(('AND2', [n(sa), n(sb)], aux))
                cells.append(('NOT1', [aux], nout))
                cell_counts['AND2'] += 1
                cell_counts['NOT1'] += 1
        elif k == 'NOR':
            # NOR(a,b) = AND(~a, ~b) if both shared
            # Otherwise NOR(a,b) = NOT(OR(a,b))
            sa, sb = ins[0], ins[1]
            if sa in shared_nots and sb in shared_nots:
                cells.append(('AND2', [shared_nots[sa], shared_nots[sb]], nout))
                cell_counts['AND2'] += 1
            else:
                aux = f"aux_{out}"
                cells.append(('OR2', [n(sa), n(sb)], aux))
                cells.append(('NOT1', [aux], nout))
                cell_counts['OR2'] += 1
                cell_counts['NOT1'] += 1
        elif k == 'XNOR':
            # XNOR(a,b) = XOR(~a, b) = XOR(a, ~b). If exactly one of ~a, ~b
            # already exists, use it (saves the NOT).
            sa, sb = ins[0], ins[1]
            if sa in shared_nots:
                cells.append(('XOR2', [shared_nots[sa], n(sb)], nout))
                cell_counts['XOR2'] += 1
            elif sb in shared_nots:
                cells.append(('XOR2', [n(sa), shared_nots[sb]], nout))
                cell_counts['XOR2'] += 1
            else:
                aux = f"aux_{out}"
                cells.append(('XOR2', [n(sa), n(sb)], aux))
                cells.append(('NOT1', [aux], nout))
                cell_counts['XOR2'] += 1
                cell_counts['NOT1'] += 1
        elif k == 'ANDN_A':
            cells.append(('AND2', [shared_nots[ins[0]], n(ins[1])], nout))
            cell_counts['AND2'] += 1
        elif k == 'ANDN_B':
            cells.append(('AND2', [n(ins[0]), shared_nots[ins[1]]], nout))
            cell_counts['AND2'] += 1
        elif k == 'NOT_A':
            shared = shared_nots[ins[0]]
            if shared != nout:
                cells.append(('BUF_NAMES', [shared], nout))
        elif k == 'NOT_B':
            shared = shared_nots[ins[1]]
            if shared != nout:
                cells.append(('BUF_NAMES', [shared], nout))
        elif k == 'XOR3':
            aux = f"aux_{out}"
            cells.append(('XOR2', [n(ins[0]), n(ins[1])], aux))
            cells.append(('XOR2', [aux, n(ins[2])], nout))
            cell_counts['XOR2'] += 2
        elif k == 'AND3':
            aux = f"aux_{out}"
            cells.append(('AND2', [n(ins[0]), n(ins[1])], aux))
            cells.append(('AND2', [aux, n(ins[2])], nout))
            cell_counts['AND2'] += 2
        elif k == 'OR3':
            aux = f"aux_{out}"
            cells.append(('OR2', [n(ins[0]), n(ins[1])], aux))
            cells.append(('OR2', [aux, n(ins[2])], nout))
            cell_counts['OR2'] += 2
        else:
            raise ValueError(f"Unhandled kind {k}")

    # Write BLIF
    with open(out_path, 'w') as g:
        g.write(".model fp4_mul\n")
        g.write(".inputs " + " ".join(in_names) + "\n")
        g.write(".outputs " + " ".join(out_names) + "\n")
        for kind, pins, out in cells:
            if kind == 'AND2':
                g.write(f".gate AND2 A={pins[0]} B={pins[1]} Y={out}\n")
            elif kind == 'OR2':
                g.write(f".gate OR2 A={pins[0]} B={pins[1]} Y={out}\n")
            elif kind == 'XOR2':
                g.write(f".gate XOR2 A={pins[0]} B={pins[1]} Y={out}\n")
            elif kind == 'NOT1':
                g.write(f".gate NOT1 A={pins[0]} Y={out}\n")
            elif kind == 'BUF_NAMES':
                g.write(f".names {pins[0]} {out}\n1 1\n")
            elif kind == 'CONST0':
                g.write(f".names {out}\n")
            elif kind == 'CONST1':
                g.write(f".names {out}\n1\n")
        g.write(".end\n")

    total = sum(cell_counts.values())
    if verbose:
        print(f"Translated: cells={dict(cell_counts)} total={total}")
    return cell_counts, total


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("usage: eslim_translator2.py <in.blif> <out.blif>")
        sys.exit(1)
    in_names = ['a[0]', 'a[1]', 'a[2]', 'a[3]', 'b[0]', 'b[1]', 'b[2]', 'b[3]']
    out_names = ['y[0]', 'y[1]', 'y[2]', 'y[3]', 'y[4]', 'y[5]', 'y[6]', 'y[7]', 'y[8]']
    counts, total = translate(sys.argv[1], sys.argv[2], in_names, out_names, verbose=True)
