"""
G2: Brute-force the not_65 cone.

Current cone (3 gates):
  not_65 = NOT(w_65)
  y0     = AND(not_65, w_43)
  w_69   = AND(w_58, not_65)

Using inputs {w_43, w_58, w_65}, can we produce both {y0, w_69} in ≤2 gates?
Enumerate all length-≤2 straight-line programs over {AND, OR, XOR, NOT} on 3
inputs, check whether some pair of intermediate / final values matches the
target bitvectors {y0_bv, w_69_bv}.
"""
from __future__ import annotations
import itertools, sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)) + "/..")
from triage.g1_g3_g4_64gate import simulate_64gate, ALL_ONE


def enumerate_programs(input_bvs, max_gates):
    """Yield (gates, value_dict) for every straight-line program of length
    ≤ max_gates. Each "gate" is (op, in_indices) where in_indices reference
    the (current) program's wire list."""
    init = list(input_bvs)
    n_inputs = len(init)

    def recur(wires, gates_so_far):
        yield wires, gates_so_far
        if len(gates_so_far) >= max_gates:
            return
        n = len(wires)
        # 1-input ops
        for i in range(n):
            new_v = ALL_ONE ^ wires[i]
            yield from recur(wires + [new_v], gates_so_far + [("NOT", i)])
        # 2-input ops
        for i in range(n):
            for j in range(i+1, n):
                for op_name, op_fn in (
                    ("AND", lambda x,y: x & y),
                    ("OR",  lambda x,y: x | y),
                    ("XOR", lambda x,y: x ^ y),
                ):
                    new_v = op_fn(wires[i], wires[j])
                    yield from recur(wires + [new_v], gates_so_far + [(op_name, i, j)])

    yield from recur(init, [])


def find_pair(target_bv1, target_bv2, programs):
    """For each program, check whether two of its wires match the targets."""
    for wires, gates in programs:
        idx1 = idx2 = None
        for k, v in enumerate(wires):
            if v == target_bv1 and idx1 is None: idx1 = k
            if v == target_bv2 and idx2 is None: idx2 = k
            if idx1 is not None and idx2 is not None:
                return gates, idx1, idx2
    return None


def main():
    W, _ = simulate_64gate()
    w_43 = W["w_43"]; w_58 = W["w_58"]; w_65 = W["w_65"]
    y0_bv = W["y0"]; w_69_bv = W["w_69"]

    print(f"Inputs: w_43 (popcount {bin(w_43).count('1')}), "
          f"w_58 (popcount {bin(w_58).count('1')}), "
          f"w_65 (popcount {bin(w_65).count('1')})")
    print(f"Targets: y0 (popcount {bin(y0_bv).count('1')}), "
          f"w_69 (popcount {bin(w_69_bv).count('1')})")
    print()

    # Try 1, 2, 3 gate programs
    for max_g in (1, 2, 3):
        print(f"Trying programs of length ≤ {max_g}...")
        programs = list(enumerate_programs([w_43, w_58, w_65], max_g))
        result = find_pair(y0_bv, w_69_bv, programs)
        if result:
            gates, idx1, idx2 = result
            print(f"  HIT at length {len(gates)}: y0=wire[{idx1}], w_69=wire[{idx2}]")
            print(f"  Gates: {gates}")
            return
        print(f"  No match in {len(programs)} programs.")

    print()
    print("→ G2 = NO HIT. Confirms not_65 cone needs at least 3 gates")
    print("  given inputs {w_43, w_58, w_65}, matching Longhorn's encoding.")
    print("  (Cirbo SAT would prove this UNSAT formally; brute force suffices here.)")


if __name__ == "__main__":
    main()
