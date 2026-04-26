#!/usr/bin/env python3
"""Classify gates in a BLIF as AND/OR/XOR/NOT/MUX/etc and count."""
import sys
from collections import Counter

def main(p):
    with open(p) as f:
        lines = [ln.rstrip('\n') for ln in f]

    counts = Counter()
    i = 0
    n = len(lines)
    gate_details = []
    while i < n:
        ln = lines[i].strip()
        if ln.startswith('.names'):
            tokens = ln.split()[1:]
            cubes = []
            j = i + 1
            while j < n and not lines[j].strip().startswith('.'):
                if lines[j].strip() and not lines[j].strip().startswith('#'):
                    cubes.append(lines[j].strip())
                j += 1
            i = j
            n_in = len(tokens) - 1
            cube_str = sorted(cubes)
            key = (n_in, tuple(cube_str))
            kind = classify(n_in, cube_str)
            counts[kind] += 1
            gate_details.append((tokens, kind, cubes))
            continue
        i += 1

    for k, v in counts.most_common():
        print(f"  {k}: {v}")
    print(f"  TOTAL: {sum(counts.values())}")

def classify(n_in, cubes):
    if n_in == 0:
        if cubes == []:
            return 'CONST0'
        if cubes == ['1']:
            return 'CONST1'
        return 'CONST_OTHER'
    if n_in == 1:
        if cubes == ['1 1']:
            return 'BUF'
        if cubes == ['0 1']:
            return 'NOT'
        return 'UNARY_OTHER'
    if n_in == 2:
        # AND2: 11 1
        # OR2: 01,10,11 1
        # XOR2: 01,10 1
        # NAND2: 00,01,10 1
        # NOR2: 00 1
        # XNOR2: 00,11 1
        cset = set(c.split()[0] for c in cubes)
        if cset == {'11'}:
            return 'AND2'
        if cset == {'01','10','11'}:
            return 'OR2'
        if cset == {'01','10'}:
            return 'XOR2'
        if cset == {'00','01','10'}:
            return 'NAND2'
        if cset == {'00'}:
            return 'NOR2'
        if cset == {'00','11'}:
            return 'XNOR2'
        return f'2IN_{cset}'
    if n_in == 3:
        cset = set(c.split()[0] for c in cubes)
        if cset == {'111'}:
            return 'AND3'
        if cset == {'001','010','011','100','101','110','111'}:
            return 'OR3'
        # XOR3: odd parity
        if cset == {'001','010','100','111'}:
            return 'XOR3'
        return f'3IN_{len(cset)}cubes'
    return f'{n_in}IN'

if __name__ == "__main__":
    main(sys.argv[1])
