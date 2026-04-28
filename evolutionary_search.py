"""
Evolutionary Circuit Search for FP4xFP4 -> QI9 Multiplier

Goal: Find circuits with fewer than 82 gates (current best).

Representation: Circuit as list of (op, in1, in2) tuples.
  - op: 'NOT', 'AND', 'OR', 'XOR'
  - in1, in2: indices (0-7 = inputs, 8+ = gate outputs)
  - NOT uses only in1

Fitness: Correct on all 225 care terms (hard), minimize gate count (soft).

Mutations:
  - Change gate operation
  - Rewire inputs
  - Delete unused gate
  - Insert gate
  - Swap gates

Uses parallel evaluation and efficient bitwise truth table simulation.
"""

import random
import time
import copy
import sys
from collections import defaultdict
from typing import List, Tuple, Dict, Optional, Set

# ============== TRUTH TABLE ==============
# FP4 table and encoding from the reference implementation
FP4_TABLE = [0.0, 0.5, 1.0, 1.5, 2.0, 3.0, 4.0, 6.0,
             0.0, -0.5, -1.0, -1.5, -2.0, -3.0, -4.0, -6.0]

_MAG_TO_CODE = {
    0.0: 0b000, 1.5: 0b001, 3.0: 0b010, 6.0: 0b011,
    0.5: 0b100, 1.0: 0b101, 2.0: 0b110, 4.0: 0b111,
}

def remap(orig_idx):
    """Map original FP4 index to our encoding."""
    v = FP4_TABLE[orig_idx]
    sign = 1 if v < 0 else 0
    return (sign << 3) | _MAG_TO_CODE[abs(v)]

def build_truth_table():
    """Build complete truth table: 8-bit input -> 9-bit output."""
    table = {}
    for a_orig in range(16):
        for b_orig in range(16):
            a_code = remap(a_orig)
            b_code = remap(b_orig)
            inp = (a_code << 4) | b_code
            qi9 = int(round(FP4_TABLE[a_orig] * FP4_TABLE[b_orig] * 4)) & 0x1FF
            table[inp] = qi9
    return table

# Build truth table once
TRUTH_TABLE = build_truth_table()

# Convert to list format for faster evaluation
# Each entry: (input_bits[8], output_bits[9])
CARE_TERMS = []
for inp, out in TRUTH_TABLE.items():
    in_bits = tuple((inp >> (7-i)) & 1 for i in range(8))
    out_bits = tuple((out >> (8-i)) & 1 for i in range(9))
    CARE_TERMS.append((in_bits, out_bits))

print(f"Loaded {len(CARE_TERMS)} care terms")

# ============== CIRCUIT REPRESENTATION ==============

class Circuit:
    """
    Circuit as a list of gates.

    Inputs: indices 0-7 (a0,a1,a2,a3,b0,b1,b2,b3)
    Constants: index 8 = False (0), index 9 = True (1)
    Gates: indices 10+

    Each gate: (op, in1, in2) where op in ['NOT', 'AND', 'OR', 'XOR']
    Output wires: list of 9 wire indices for res0, r1, ..., r8
    """

    NUM_INPUTS = 8
    CONST_FALSE = 8
    CONST_TRUE = 9
    FIRST_GATE = 10

    OPS = ['NOT', 'AND', 'OR', 'XOR']

    def __init__(self, gates=None, outputs=None):
        self.gates = gates if gates else []  # List of (op, in1, in2)
        self.outputs = outputs if outputs else [self.CONST_FALSE] * 9

    def copy(self):
        return Circuit(copy.deepcopy(self.gates), self.outputs[:])

    def num_gates(self):
        return len(self.gates)

    def max_wire(self):
        """Highest wire index available."""
        return self.FIRST_GATE + len(self.gates) - 1 if self.gates else self.CONST_TRUE

    def valid_input(self, idx):
        """Check if wire index is valid as input."""
        return 0 <= idx <= self.max_wire()

    def evaluate(self, inputs):
        """
        Evaluate circuit on given input tuple.
        inputs: 8-tuple of 0/1
        Returns: 9-tuple of 0/1
        """
        # Wire values: 0-7 = inputs, 8 = False, 9 = True, 10+ = gates
        wires = list(inputs) + [0, 1]  # Inputs + constants

        for op, in1, in2 in self.gates:
            v1 = wires[in1] if in1 < len(wires) else 0
            v2 = wires[in2] if in2 < len(wires) else 0

            if op == 'NOT':
                wires.append(1 - v1)
            elif op == 'AND':
                wires.append(v1 & v2)
            elif op == 'OR':
                wires.append(v1 | v2)
            elif op == 'XOR':
                wires.append(v1 ^ v2)
            else:
                wires.append(0)

        # Extract outputs
        result = []
        for oidx in self.outputs:
            if oidx < len(wires):
                result.append(wires[oidx])
            else:
                result.append(0)
        return tuple(result)

    def count_errors(self):
        """Count how many care terms are wrong."""
        errors = 0
        for in_bits, expected in CARE_TERMS:
            actual = self.evaluate(in_bits)
            if actual != expected:
                errors += 1
        return errors

    def is_correct(self):
        """Check if circuit is correct on all care terms."""
        return self.count_errors() == 0

    def used_gates(self):
        """Find which gates are actually used (transitively from outputs)."""
        used = set()
        to_check = list(self.outputs)

        while to_check:
            idx = to_check.pop()
            if idx >= self.FIRST_GATE:
                gate_idx = idx - self.FIRST_GATE
                if gate_idx not in used and gate_idx < len(self.gates):
                    used.add(gate_idx)
                    op, in1, in2 = self.gates[gate_idx]
                    to_check.append(in1)
                    if op != 'NOT':
                        to_check.append(in2)
        return used

    def compact(self):
        """Remove unused gates and renumber."""
        used = sorted(self.used_gates())
        if len(used) == len(self.gates):
            return  # Nothing to remove

        # Build mapping: old gate index -> new gate index
        old_to_new = {old: new for new, old in enumerate(used)}

        def remap_wire(idx):
            if idx < self.FIRST_GATE:
                return idx
            gate_idx = idx - self.FIRST_GATE
            if gate_idx in old_to_new:
                return self.FIRST_GATE + old_to_new[gate_idx]
            return self.CONST_FALSE  # Invalid reference

        # New gates with remapped inputs
        new_gates = []
        for old_idx in used:
            op, in1, in2 = self.gates[old_idx]
            new_gates.append((op, remap_wire(in1), remap_wire(in2)))

        # Remap outputs
        new_outputs = [remap_wire(o) for o in self.outputs]

        self.gates = new_gates
        self.outputs = new_outputs


# ============== RANDOM CIRCUIT GENERATION ==============

def random_circuit(target_gates=75, seed=None):
    """Generate a random circuit with approximately target_gates gates."""
    if seed is not None:
        random.seed(seed)

    c = Circuit()

    # Build up gates, each referencing earlier wires
    for _ in range(target_gates):
        op = random.choice(Circuit.OPS)
        max_in = c.max_wire()
        in1 = random.randint(0, max_in)
        in2 = random.randint(0, max_in) if op != 'NOT' else 0
        c.gates.append((op, in1, in2))

    # Set random outputs
    for i in range(9):
        c.outputs[i] = random.randint(0, c.max_wire())

    return c


def seeded_circuit():
    """
    Generate a circuit seeded with known-good structure from the 82-gate solution.
    This helps the search start from a better position.
    """
    c = Circuit()

    # Inputs: a0=0, a1=1, a2=2, a3=3, b0=4, b1=5, b2=6, b3=7
    # Constants: False=8, True=9

    # Sign (1 gate): XOR(a0, b0)
    c.gates.append(('XOR', 0, 4))  # gate 10 = sign

    # NZ detection (5 gates)
    c.gates.append(('OR', 2, 3))   # gate 11 = or_a23
    c.gates.append(('OR', 1, 11))  # gate 12 = nz_a
    c.gates.append(('OR', 6, 7))   # gate 13 = or_b23
    c.gates.append(('OR', 5, 13))  # gate 14 = nz_b
    c.gates.append(('AND', 12, 14)) # gate 15 = nz

    # E-sum (7 gates)
    c.gates.append(('XOR', 3, 7))  # gate 16 = s0
    c.gates.append(('AND', 3, 7))  # gate 17 = c0
    c.gates.append(('XOR', 2, 6))  # gate 18 = s1x
    c.gates.append(('XOR', 18, 17)) # gate 19 = s1
    c.gates.append(('AND', 2, 6))  # gate 20 = a2&b2
    c.gates.append(('AND', 18, 17)) # gate 21 = s1x&c0
    c.gates.append(('OR', 20, 21)) # gate 22 = s2

    # K-flags (3 gates)
    c.gates.append(('OR', 1, 5))   # gate 23 = or_a1b1
    c.gates.append(('NOT', 23, 0)) # gate 24 = k9_raw
    c.gates.append(('XOR', 1, 5))  # gate 25 = k3_raw

    # K-masking (3 gates)
    c.gates.append(('AND', 23, 15)) # gate 26 = nmc
    c.gates.append(('AND', 25, 15)) # gate 27 = k3
    c.gates.append(('AND', 24, 15)) # gate 28 = k9

    # S-decoder: compute sh0..sh6 from s0(16), s1(19), s2(22)
    # Using the 11-gate optimal circuit
    c.gates.append(('OR', 22, 19))  # gate 29 = _or01 (s2 | s1)
    c.gates.append(('OR', 16, 29))  # gate 30 = _or012
    c.gates.append(('NOT', 30, 0))  # gate 31 = sh0
    c.gates.append(('XOR', 29, 30)) # gate 32 = sh1
    c.gates.append(('XOR', 16, 30)) # gate 33 = _xor2
    c.gates.append(('AND', 22, 33)) # gate 34 = _and2
    c.gates.append(('AND', 19, 16)) # gate 35 = sh3
    c.gates.append(('AND', 22, 16)) # gate 36 = sh5
    c.gates.append(('XOR', 33, 34)) # gate 37 = sh2
    c.gates.append(('AND', 19, 34)) # gate 38 = sh6
    c.gates.append(('XOR', 34, 38)) # gate 39 = sh4

    # AND-terms (18 gates): nmc x sh[0-6], k3 x sh[1-6], k9 x sh[2-6]
    # nmc (26) x sh: 31,32,37,35,39,36,38
    c.gates.append(('AND', 26, 31)) # 40 = nmc0
    c.gates.append(('AND', 26, 32)) # 41 = nmc1
    c.gates.append(('AND', 26, 37)) # 42 = nmc2
    c.gates.append(('AND', 26, 35)) # 43 = nmc3
    c.gates.append(('AND', 26, 39)) # 44 = nmc4
    c.gates.append(('AND', 26, 36)) # 45 = nmc5
    c.gates.append(('AND', 26, 38)) # 46 = nmc6

    # k3 (27) x sh
    c.gates.append(('AND', 27, 32)) # 47 = k3_1
    c.gates.append(('AND', 27, 37)) # 48 = k3_2
    c.gates.append(('AND', 27, 35)) # 49 = k3_3
    c.gates.append(('AND', 27, 39)) # 50 = k3_4
    c.gates.append(('AND', 27, 36)) # 51 = k3_5
    c.gates.append(('AND', 27, 38)) # 52 = k3_6

    # k9 (28) x sh
    c.gates.append(('AND', 28, 37)) # 53 = k9_2
    c.gates.append(('AND', 28, 35)) # 54 = k9_3
    c.gates.append(('AND', 28, 39)) # 55 = k9_4
    c.gates.append(('AND', 28, 36)) # 56 = k9_5
    c.gates.append(('AND', 28, 38)) # 57 = k9_6

    # Magnitude bits m[0-7] (15 gates)
    c.gates.append(('OR', 47, 53))  # 58 = k3_1 | k9_2
    c.gates.append(('OR', 40, 58))  # 59 = m0
    c.gates.append(('OR', 48, 54))  # 60 = k3_2 | k9_3
    c.gates.append(('OR', 41, 60))  # 61 = m1
    c.gates.append(('OR', 49, 55))  # 62 = k3_3 | k9_4
    c.gates.append(('OR', 42, 62))  # 63 = m2
    c.gates.append(('OR', 50, 56))  # 64 = k3_4 | k9_5
    c.gates.append(('OR', 53, 64))  # 65 = k9_2 | (k3_4 | k9_5)
    c.gates.append(('OR', 43, 65))  # 66 = m3
    c.gates.append(('OR', 51, 57))  # 67 = k3_5 | k9_6
    c.gates.append(('OR', 54, 67))  # 68 = k9_3 | (k3_5 | k9_6)
    c.gates.append(('OR', 44, 68))  # 69 = m4
    c.gates.append(('OR', 52, 55))  # 70 = k3_6 | k9_4
    c.gates.append(('OR', 45, 70))  # 71 = m5
    c.gates.append(('OR', 46, 56))  # 72 = m6 = nmc6 | k9_5
    # m7 = k9_6 (57)

    # res0 = AND(sign, nz) (1 gate)
    c.gates.append(('AND', 10, 15)) # 73 = res0

    # Prefix-OR chain (5 gates)
    c.gates.append(('OR', 59, 61))  # 74 = p2
    c.gates.append(('OR', 74, 63))  # 75 = p3
    c.gates.append(('OR', 75, 66))  # 76 = p4
    c.gates.append(('OR', 76, 69))  # 77 = p5
    c.gates.append(('OR', 77, 71))  # 78 = p6

    # sp gates (6 gates)
    c.gates.append(('AND', 10, 59)) # 79 = sp1
    c.gates.append(('AND', 10, 74)) # 80 = sp2
    c.gates.append(('AND', 10, 75)) # 81 = sp3
    c.gates.append(('AND', 10, 76)) # 82 = sp4
    c.gates.append(('AND', 10, 77)) # 83 = sp5
    c.gates.append(('AND', 10, 78)) # 84 = sp6

    # XOR gates for r1-r7 (7 gates)
    c.gates.append(('XOR', 61, 79)) # 85 = r7
    c.gates.append(('XOR', 63, 80)) # 86 = r6
    c.gates.append(('XOR', 66, 81)) # 87 = r5
    c.gates.append(('XOR', 69, 82)) # 88 = r4
    c.gates.append(('XOR', 71, 83)) # 89 = r3
    c.gates.append(('XOR', 72, 84)) # 90 = r2
    c.gates.append(('XOR', 57, 73)) # 91 = r1

    # Outputs: res0, r1, r2, r3, r4, r5, r6, r7, r8
    # r8 = m0 (59)
    c.outputs = [73, 91, 90, 89, 88, 87, 86, 85, 59]

    return c


# ============== MUTATION OPERATORS ==============

def mutate_op(c):
    """Change a random gate's operation."""
    if not c.gates:
        return False
    idx = random.randrange(len(c.gates))
    op, in1, in2 = c.gates[idx]
    new_op = random.choice(Circuit.OPS)
    if new_op != op:
        c.gates[idx] = (new_op, in1, in2)
        return True
    return False

def mutate_input(c):
    """Rewire a random input of a random gate."""
    if not c.gates:
        return False
    idx = random.randrange(len(c.gates))
    op, in1, in2 = c.gates[idx]

    # Only reference earlier wires to maintain topological order
    max_in = Circuit.FIRST_GATE + idx - 1
    if max_in < 0:
        max_in = Circuit.CONST_TRUE

    if random.random() < 0.5:
        new_in1 = random.randint(0, max_in)
        c.gates[idx] = (op, new_in1, in2)
    else:
        new_in2 = random.randint(0, max_in)
        c.gates[idx] = (op, in1, new_in2)
    return True

def mutate_output(c):
    """Change a random output wire."""
    idx = random.randrange(9)
    c.outputs[idx] = random.randint(0, c.max_wire())
    return True

def mutate_delete(c):
    """Delete an unused gate."""
    used = c.used_gates()
    unused = [i for i in range(len(c.gates)) if i not in used]
    if not unused:
        return False

    # Delete one unused gate and renumber
    del_idx = random.choice(unused)

    def remap_wire(w):
        if w < Circuit.FIRST_GATE:
            return w
        g = w - Circuit.FIRST_GATE
        if g > del_idx:
            return w - 1
        return w

    new_gates = []
    for i, (op, in1, in2) in enumerate(c.gates):
        if i == del_idx:
            continue
        new_gates.append((op, remap_wire(in1), remap_wire(in2)))

    c.gates = new_gates
    c.outputs = [remap_wire(o) for o in c.outputs]
    return True

def mutate_insert(c):
    """Insert a new gate at a random position."""
    pos = random.randint(0, len(c.gates))
    op = random.choice(Circuit.OPS)

    max_in = Circuit.FIRST_GATE + pos - 1
    if max_in < Circuit.CONST_TRUE:
        max_in = Circuit.CONST_TRUE

    in1 = random.randint(0, max_in)
    in2 = random.randint(0, max_in) if op != 'NOT' else 0

    # Insert gate
    c.gates.insert(pos, (op, in1, in2))

    # Renumber all references after insertion point
    def remap_wire(w):
        if w < Circuit.FIRST_GATE:
            return w
        g = w - Circuit.FIRST_GATE
        if g >= pos:
            return w + 1
        return w

    for i in range(pos + 1, len(c.gates)):
        op, in1, in2 = c.gates[i]
        c.gates[i] = (op, remap_wire(in1), remap_wire(in2))

    c.outputs = [remap_wire(o) for o in c.outputs]
    return True

def mutate_swap(c):
    """Swap two adjacent gates if valid."""
    if len(c.gates) < 2:
        return False

    idx = random.randrange(len(c.gates) - 1)
    op1, in1_1, in2_1 = c.gates[idx]
    op2, in1_2, in2_2 = c.gates[idx + 1]

    wire1 = Circuit.FIRST_GATE + idx
    wire2 = Circuit.FIRST_GATE + idx + 1

    # Check if gate2 depends on gate1
    if in1_2 == wire1 or in2_2 == wire1:
        return False  # Can't swap

    # Swap and update any references
    c.gates[idx] = c.gates[idx + 1]
    c.gates[idx + 1] = (op1, in1_1, in2_1)

    # Update references: wire1 <-> wire2
    def swap_wire(w):
        if w == wire1:
            return wire2
        if w == wire2:
            return wire1
        return w

    for i in range(idx + 2, len(c.gates)):
        op, in1, in2 = c.gates[i]
        c.gates[i] = (op, swap_wire(in1), swap_wire(in2))

    c.outputs = [swap_wire(o) for o in c.outputs]
    return True


def mutate(c, mutation_rate=1.0):
    """Apply a random mutation to the circuit."""
    mutations = [
        (mutate_op, 0.25),
        (mutate_input, 0.3),
        (mutate_output, 0.15),
        (mutate_delete, 0.1),
        (mutate_insert, 0.1),
        (mutate_swap, 0.1),
    ]

    r = random.random()
    cumsum = 0
    for fn, prob in mutations:
        cumsum += prob
        if r < cumsum:
            return fn(c)
    return mutations[0][0](c)


# ============== EVOLUTIONARY SEARCH ==============

def fitness(c):
    """
    Fitness function: (correctness_score, -gate_count)
    Higher is better.
    correctness_score: 225 - num_errors (max 225 for correct circuit)
    """
    errors = c.count_errors()
    return (225 - errors, -c.num_gates())

def evolutionary_search(
    pop_size=100,
    generations=10000,
    mutation_rate=0.3,
    elite_size=5,
    tournament_size=3,
    timeout_minutes=30,
    seed_with_known=True,
    verbose=True
):
    """
    Run evolutionary search for low-gate circuits.

    Uses (mu + lambda) evolution with tournament selection.
    """
    start_time = time.time()
    timeout_sec = timeout_minutes * 60

    # Initialize population
    population = []

    if seed_with_known:
        # Start with perturbed versions of the known circuit
        for _ in range(pop_size // 2):
            c = seeded_circuit()
            # Apply some mutations
            for _ in range(random.randint(0, 10)):
                mutate(c)
            population.append(c)
        # Add random circuits
        for _ in range(pop_size - len(population)):
            population.append(random_circuit(random.randint(70, 90)))
    else:
        # Pure random initialization
        for _ in range(pop_size):
            population.append(random_circuit(random.randint(70, 90)))

    best_correct = None
    best_correct_gates = float('inf')
    best_fitness = (-1000, -1000)

    generation = 0
    last_improvement = 0

    while generation < generations:
        elapsed = time.time() - start_time
        if elapsed > timeout_sec:
            print(f"\nTimeout reached after {elapsed/60:.1f} minutes")
            break

        # Evaluate population
        scored = [(fitness(c), c) for c in population]
        scored.sort(key=lambda x: x[0], reverse=True)

        # Track best
        if scored[0][0] > best_fitness:
            best_fitness = scored[0][0]
            last_improvement = generation

        # Check for correct circuits
        for fit, c in scored:
            if fit[0] == 225:  # Correct
                gates = c.num_gates()
                if gates < best_correct_gates:
                    best_correct = c.copy()
                    best_correct_gates = gates
                    print(f"\n*** NEW BEST CORRECT: {gates} gates at gen {generation} ***")
                    if gates < 82:
                        print("!!!! BREAKTHROUGH: Under 82 gates! !!!!")

        # Progress report
        if verbose and generation % 100 == 0:
            top_fit = scored[0][0]
            top_gates = scored[0][1].num_gates()
            correct_count = sum(1 for f, _ in scored if f[0] == 225)
            print(f"Gen {generation:5d}: best_fit={top_fit}, gates={top_gates}, "
                  f"correct={correct_count}/{pop_size}, "
                  f"best_correct={best_correct_gates if best_correct else 'none'}, "
                  f"time={elapsed:.0f}s")

        # Selection: tournament
        new_population = []

        # Elitism: keep top circuits
        for _, c in scored[:elite_size]:
            new_population.append(c.copy())

        # Tournament selection for rest
        while len(new_population) < pop_size:
            # Tournament
            tournament = random.sample(scored, min(tournament_size, len(scored)))
            winner = max(tournament, key=lambda x: x[0])[1]

            # Clone and mutate
            child = winner.copy()

            # Apply mutations
            num_mutations = 1 + int(random.expovariate(1.0))  # Geometric distribution
            for _ in range(num_mutations):
                mutate(child)

            new_population.append(child)

        population = new_population
        generation += 1

        # Occasional compaction
        if generation % 50 == 0:
            for c in population:
                c.compact()

    elapsed = time.time() - start_time
    print(f"\nSearch complete. Time: {elapsed/60:.1f} minutes, Generations: {generation}")

    if best_correct:
        print(f"Best correct circuit: {best_correct_gates} gates")
        return best_correct
    else:
        print("No correct circuit found")
        return None


# ============== SIMULATED ANNEALING VARIANT ==============

def simulated_annealing(
    initial_circuit=None,
    max_iterations=100000,
    initial_temp=10.0,
    final_temp=0.01,
    timeout_minutes=30,
    verbose=True
):
    """
    Simulated annealing search starting from the known circuit.
    """
    start_time = time.time()
    timeout_sec = timeout_minutes * 60

    if initial_circuit is None:
        current = seeded_circuit()
    else:
        current = initial_circuit.copy()

    current_fit = fitness(current)
    best = current.copy()
    best_fit = current_fit
    best_gates = current.num_gates() if current_fit[0] == 225 else float('inf')

    temp = initial_temp
    cooling_rate = (final_temp / initial_temp) ** (1.0 / max_iterations)

    accepted = 0
    rejected = 0

    for iteration in range(max_iterations):
        elapsed = time.time() - start_time
        if elapsed > timeout_sec:
            print(f"\nTimeout reached after {elapsed/60:.1f} minutes")
            break

        # Create neighbor
        neighbor = current.copy()
        num_mutations = 1 + int(random.expovariate(2.0))
        for _ in range(num_mutations):
            mutate(neighbor)

        neighbor_fit = fitness(neighbor)

        # Acceptance criterion
        delta = (neighbor_fit[0] - current_fit[0]) * 10 + (neighbor_fit[1] - current_fit[1])

        if delta > 0:
            accept = True
        else:
            prob = min(1.0, pow(2.718, delta / temp))
            accept = random.random() < prob

        if accept:
            current = neighbor
            current_fit = neighbor_fit
            accepted += 1

            # Track best correct
            if current_fit[0] == 225:
                gates = current.num_gates()
                if gates < best_gates:
                    best = current.copy()
                    best_fit = current_fit
                    best_gates = gates
                    print(f"\n*** NEW BEST: {gates} gates at iter {iteration} ***")
                    if gates < 82:
                        print("!!!! BREAKTHROUGH: Under 82 gates! !!!!")
        else:
            rejected += 1

        # Cool down
        temp *= cooling_rate

        # Progress report
        if verbose and iteration % 1000 == 0:
            print(f"Iter {iteration:6d}: temp={temp:.4f}, current={current_fit}, "
                  f"best_gates={best_gates if best_gates < float('inf') else 'none'}, "
                  f"accept_rate={accepted/(accepted+rejected+1):.2f}")
            accepted = rejected = 0

        # Occasional compaction
        if iteration % 100 == 0:
            current.compact()

    elapsed = time.time() - start_time
    print(f"\nSA complete. Time: {elapsed/60:.1f} minutes")

    if best_fit[0] == 225:
        print(f"Best correct circuit: {best_gates} gates")
        return best
    return None


# ============== LOCAL SEARCH (HILL CLIMBING) ==============

def local_search(
    initial_circuit=None,
    max_iterations=50000,
    timeout_minutes=10,
    verbose=True
):
    """
    Simple hill-climbing local search.
    Focus on reducing gates while maintaining correctness.
    """
    start_time = time.time()
    timeout_sec = timeout_minutes * 60

    if initial_circuit is None:
        current = seeded_circuit()
    else:
        current = initial_circuit.copy()

    current.compact()
    current_errors = current.count_errors()
    current_gates = current.num_gates()

    if current_errors != 0:
        print(f"Warning: Initial circuit has {current_errors} errors")

    best_gates = current_gates if current_errors == 0 else float('inf')
    best = current.copy() if current_errors == 0 else None

    print(f"Starting local search from {current_gates} gates, {current_errors} errors")

    iterations = 0
    improvements = 0

    while iterations < max_iterations:
        elapsed = time.time() - start_time
        if elapsed > timeout_sec:
            print(f"\nTimeout after {elapsed/60:.1f} minutes")
            break

        # Try a mutation
        neighbor = current.copy()
        mutate(neighbor)
        neighbor.compact()

        neighbor_errors = neighbor.count_errors()
        neighbor_gates = neighbor.num_gates()

        # Accept if: correct and fewer gates, or fewer errors
        accept = False
        if current_errors > 0:
            # Not yet correct: prioritize reducing errors
            if neighbor_errors < current_errors:
                accept = True
            elif neighbor_errors == current_errors and neighbor_gates < current_gates:
                accept = True
        else:
            # Currently correct: only accept if still correct and fewer gates
            if neighbor_errors == 0 and neighbor_gates < current_gates:
                accept = True

        if accept:
            current = neighbor
            current_errors = neighbor_errors
            current_gates = neighbor_gates
            improvements += 1

            if current_errors == 0 and current_gates < best_gates:
                best = current.copy()
                best_gates = current_gates
                print(f"*** NEW BEST: {best_gates} gates at iter {iterations} ***")
                if best_gates < 82:
                    print("!!!! BREAKTHROUGH: Under 82 gates! !!!!")

        iterations += 1

        if verbose and iterations % 5000 == 0:
            print(f"Iter {iterations}: gates={current_gates}, errors={current_errors}, "
                  f"improvements={improvements}, best={best_gates}")

    print(f"\nLocal search complete. Best: {best_gates} gates")
    return best


# ============== MAIN ==============

def verify_seeded():
    """Verify the seeded circuit is correct."""
    c = seeded_circuit()
    errors = c.count_errors()
    gates = c.num_gates()
    print(f"Seeded circuit: {gates} gates, {errors} errors")
    return errors == 0

def main():
    print("=" * 60)
    print("FP4xFP4 Evolutionary Circuit Search")
    print("Target: < 82 gates (current best)")
    print("=" * 60)

    # Verify our seeded circuit is correct
    print("\nVerifying seeded circuit...")
    if not verify_seeded():
        print("ERROR: Seeded circuit is incorrect!")
        return
    print("Seeded circuit verified correct.")

    # Run search algorithms
    print("\n" + "=" * 60)
    print("Phase 1: Local Search (10 min)")
    print("=" * 60)
    best_local = local_search(timeout_minutes=10)

    print("\n" + "=" * 60)
    print("Phase 2: Simulated Annealing (10 min)")
    print("=" * 60)
    best_sa = simulated_annealing(timeout_minutes=10)

    print("\n" + "=" * 60)
    print("Phase 3: Evolutionary Search (10 min)")
    print("=" * 60)
    best_evo = evolutionary_search(timeout_minutes=10)

    # Report results
    print("\n" + "=" * 60)
    print("FINAL RESULTS")
    print("=" * 60)

    results = []
    if best_local and best_local.is_correct():
        results.append(("Local Search", best_local.num_gates(), best_local))
    if best_sa and best_sa.is_correct():
        results.append(("Simulated Annealing", best_sa.num_gates(), best_sa))
    if best_evo and best_evo.is_correct():
        results.append(("Evolutionary", best_evo.num_gates(), best_evo))

    if results:
        results.sort(key=lambda x: x[1])
        print(f"\nBest results found:")
        for name, gates, _ in results:
            status = "*** BREAKTHROUGH ***" if gates < 82 else ""
            print(f"  {name}: {gates} gates {status}")

        overall_best = results[0][2]
        if results[0][1] < 82:
            print(f"\n!!! FOUND CIRCUIT WITH {results[0][1]} GATES !!!")
            print_circuit(overall_best)
    else:
        print("No correct circuits found in search")


def print_circuit(c):
    """Print a circuit in readable format."""
    print(f"\nCircuit with {c.num_gates()} gates:")
    print("Gates:")
    for i, (op, in1, in2) in enumerate(c.gates):
        wire = Circuit.FIRST_GATE + i
        if op == 'NOT':
            print(f"  g{wire} = NOT(w{in1})")
        else:
            print(f"  g{wire} = {op}(w{in1}, w{in2})")
    print(f"Outputs: {c.outputs}")


if __name__ == "__main__":
    main()
