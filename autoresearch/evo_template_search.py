"""
Template-based evolutionary search scaffold (XOR-aware) for FP4×FP4 → QI9.

Why a new file?
--------------
`evolutionary_search.py` is a large, older prototype with a fixed remap and
fitness based on whole-vector equality. For sub-75 exploration we want:
  - pluggable 16→16 encoding (full bijection, not just magnitude permutes)
  - staged fitness (progressive constraint sets)
  - bitwise error scoring (Hamming distance over 9 outputs)

This script provides that infrastructure and can be iterated on quickly.
It reuses the same simple circuit representation: a list of gates referencing
previous wires.

Run
---
  python3 -u autoresearch/evo_template_search.py --minutes 5 --gates 75 --pop 80

Optional: provide a specific encoding (16 comma-separated ints: orig_code->new_code)
  python3 -u autoresearch/evo_template_search.py --remap16 "11,6,0,4,8,7,13,9,15,3,1,5,10,2,14,12"
"""

from __future__ import annotations

import argparse
import os
import random
import sys
import time
from dataclasses import dataclass
from typing import List, Tuple, Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from eval_circuit import FP4_TABLE, build_expected_table


# ----------------------------- Circuit representation -----------------------------

OPS = ("NOT", "AND", "OR", "XOR")


@dataclass
class Circuit:
    gates: List[Tuple[str, int, int]]
    outs: List[int]  # 9 wires

    def max_wire(self) -> int:
        # inputs 0..7, const 8=0, 9=1, gates start at 10
        return 10 + len(self.gates) - 1 if self.gates else 9

    def copy(self) -> "Circuit":
        return Circuit(self.gates[:], self.outs[:])

    def compact(self) -> None:
        # Remove unused gates (simple backwards reachability)
        used_gate = set()
        stack = list(self.outs)
        while stack:
            w = stack.pop()
            if w >= 10:
                gi = w - 10
                if 0 <= gi < len(self.gates) and gi not in used_gate:
                    used_gate.add(gi)
                    op, a, b = self.gates[gi]
                    stack.append(a)
                    if op != "NOT":
                        stack.append(b)

        used = sorted(used_gate)
        if len(used) == len(self.gates):
            return

        old_to_new = {old: new for new, old in enumerate(used)}

        def remap(w: int) -> int:
            if w < 10:
                return w
            gi = w - 10
            if gi in old_to_new:
                return 10 + old_to_new[gi]
            return 8  # dead reference -> const 0

        new_gates = []
        for old in used:
            op, a, b = self.gates[old]
            new_gates.append((op, remap(a), remap(b)))

        self.gates = new_gates
        self.outs = [remap(o) for o in self.outs]

    def eval_bits(self, in8: int) -> List[int]:
        # inputs 0..7 map to bits of in8 (bit7=input0 ... bit0=input7)
        wires = [(in8 >> (7 - i)) & 1 for i in range(8)] + [0, 1]
        for op, a, b in self.gates:
            va = wires[a]
            vb = wires[b]
            if op == "NOT":
                wires.append(1 - va)
            elif op == "AND":
                wires.append(va & vb)
            elif op == "OR":
                wires.append(va | vb)
            elif op == "XOR":
                wires.append(va ^ vb)
            else:
                wires.append(0)
        return [wires[o] for o in self.outs]


def random_circuit(rng: random.Random, n_gates: int) -> Circuit:
    gates: List[Tuple[str, int, int]] = []
    for g in range(n_gates):
        op = rng.choice(OPS)
        max_in = 9 if g == 0 else (10 + g - 1)
        a = rng.randint(0, max_in)
        b = rng.randint(0, max_in)
        if op == "NOT":
            b = 8
        gates.append((op, a, b))
    outs = [rng.randint(0, 10 + n_gates - 1) for _ in range(9)]
    return Circuit(gates=gates, outs=outs)


def mutate(rng: random.Random, c: Circuit) -> None:
    if not c.gates:
        return
    r = rng.random()
    if r < 0.35:
        # op change
        i = rng.randrange(len(c.gates))
        op, a, b = c.gates[i]
        op2 = rng.choice(OPS)
        if op2 == "NOT":
            b = 8
        c.gates[i] = (op2, a, b)
    elif r < 0.70:
        # rewire input
        i = rng.randrange(len(c.gates))
        op, a, b = c.gates[i]
        max_in = 9 if i == 0 else (10 + i - 1)
        if rng.random() < 0.5:
            a = rng.randint(0, max_in)
        else:
            b = rng.randint(0, max_in)
        if op == "NOT":
            b = 8
        c.gates[i] = (op, a, b)
    else:
        # output change
        j = rng.randrange(9)
        c.outs[j] = rng.randint(0, c.max_wire())


# ----------------------------- Truth table + staged fitness -----------------------------

def expected_bits_from_remap(remap: List[int]) -> List[List[int]]:
    expected = build_expected_table(remap)  # (a_code,b_code)->qi9 mask
    bits = [[0] * 9 for _ in range(256)]
    for a in range(16):
        for b in range(16):
            qi9 = expected[(a, b)]
            idx = (a << 4) | b
            bits[idx] = [(qi9 >> (8 - i)) & 1 for i in range(9)]
    return bits


def staged_patterns(stage: int, rng: random.Random) -> List[int]:
    """
    Stage schedule:
      0: easy structural patterns (few)
      1: add random 64
      2: add random 128
      3: all 256
    """
    base = [0x00, 0xFF, 0x0F, 0xF0, 0x33, 0xCC, 0x55, 0xAA]
    if stage == 0:
        return base
    if stage == 1:
        return base + [rng.randrange(256) for _ in range(64)]
    if stage == 2:
        return base + [rng.randrange(256) for _ in range(128)]
    return list(range(256))


def bit_hamming_error(c: Circuit, expected: List[List[int]], pats: List[int]) -> int:
    err = 0
    for p in pats:
        got = c.eval_bits(p)
        exp = expected[p]
        # Hamming distance over 9 bits
        for i in range(9):
            err += (got[i] ^ exp[i])
    return err


def evolve(
    expected: List[List[int]],
    minutes: float,
    pop: int,
    n_gates: int,
    seed: int,
) -> Tuple[Optional[Circuit], int]:
    rng = random.Random(seed)
    t_end = time.time() + 60.0 * minutes

    population = [random_circuit(rng, n_gates) for _ in range(pop)]
    best: Optional[Circuit] = None
    best_err = 10**18

    stage = 0
    pats = staged_patterns(stage, rng)
    last_stage_improve = time.time()

    gen = 0
    while time.time() < t_end:
        gen += 1

        # score
        scored = []
        for c in population:
            e = bit_hamming_error(c, expected, pats)
            scored.append((e, len(c.gates), c))
        scored.sort(key=lambda x: (x[0], x[1]))

        if scored[0][0] < best_err:
            best_err = scored[0][0]
            best = scored[0][2].copy()
            best.compact()
            print(f"[gen {gen}] stage={stage} best_err={best_err} gates={len(best.gates)}", flush=True)
            last_stage_improve = time.time()

            # stage promotion heuristic
            if best_err == 0 and stage < 3:
                stage += 1
                pats = staged_patterns(stage, rng)
                print(f"  -> PROMOTE to stage {stage} (patterns={len(pats)})", flush=True)

        # If stuck, bump stage (more constraints) or randomize some individuals
        if time.time() - last_stage_improve > 60 and stage < 3:
            stage += 1
            pats = staged_patterns(stage, rng)
            last_stage_improve = time.time()
            print(f"  -> TIMEOUT PROMOTE to stage {stage} (patterns={len(pats)})", flush=True)

        # selection + mutation
        elite = max(2, pop // 10)
        new_pop = [scored[i][2].copy() for i in range(elite)]
        while len(new_pop) < pop:
            # tournament
            a = scored[rng.randrange(pop)][2]
            b = scored[rng.randrange(pop)][2]
            parent = a if bit_hamming_error(a, expected, pats) <= bit_hamming_error(b, expected, pats) else b
            child = parent.copy()
            for _ in range(1 + (rng.random() < 0.5)):
                mutate(rng, child)
            new_pop.append(child)
        population = new_pop

    # final verify on full table
    if best is None:
        return None, best_err
    bad = bit_hamming_error(best, expected, list(range(256)))
    print(f"Final best full-table bit errors: {bad}", flush=True)
    return (best if bad == 0 else None), bad


def parse_remap16(s: str) -> List[int]:
    xs = [int(x.strip()) for x in s.split(",") if x.strip() != ""]
    if len(xs) != 16:
        raise ValueError("remap16 must have 16 integers")
    if sorted(xs) != list(range(16)):
        raise ValueError("remap16 must be a bijection of 0..15")
    return xs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--minutes", type=float, default=5.0)
    ap.add_argument("--pop", type=int, default=80)
    ap.add_argument("--gates", type=int, default=75)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--remap16", type=str, default="")
    args = ap.parse_args()

    remap = parse_remap16(args.remap16) if args.remap16 else random.sample(range(16), 16)
    print(f"Using remap(orig->new): {remap}")

    expected = expected_bits_from_remap(remap)
    best, full_err = evolve(expected, args.minutes, args.pop, args.gates, args.seed)

    if best is None:
        print("No correct circuit found.")
        return
    print(f"FOUND correct circuit with {len(best.gates)} gates.")
    print(f"outs: {best.outs}")
    for i, g in enumerate(best.gates):
        print(f"  g{i:02d}: {g}")


if __name__ == "__main__":
    main()

