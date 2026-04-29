"""
G4 with DCE: for every candidate single-gate rewrite found by g4_pair_resub,
actually apply the substitution to the netlist, run dead-gate elimination,
and report any net reduction.

Because the 64-gate netlist has many fanout=1 gates, a substitution that
swaps the inputs of a fanout=1 gate to use DIFFERENT existing wires leaves
the old upstream gates orphaned only if NO OTHER wire references them.
"""
from __future__ import annotations
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)) + "/..")

# Reuse simulator from g1_g3_g4_64gate
from triage.g1_g3_g4_64gate import simulate_64gate, ALL_ONE


def build_gate_dict(gates):
    """gates is list of (name, op, in_tuple). Return dict name -> (op, in_tuple)."""
    return {g[0]: (g[1], g[2]) for g in gates}


def build_fanout(gates, output_names):
    """Return dict of name -> fanout count."""
    fanout = {}
    for name, op, ins in gates:
        for inp in ins:
            fanout[inp] = fanout.get(inp, 0) + 1
    for o in output_names:
        fanout[o] = fanout.get(o, 0) + 1
    return fanout


def dce(gates, output_names, primary_inputs):
    """Mark which gates are reachable from outputs. Return list of reachable
    gate names in original order."""
    reachable = set(output_names)
    # Walk backwards
    name_to_gate = {g[0]: g for g in gates}
    changed = True
    while changed:
        changed = False
        for name in list(reachable):
            if name in primary_inputs: continue
            if name not in name_to_gate: continue
            _, _, ins = name_to_gate[name]
            for inp in ins:
                if inp not in reachable:
                    reachable.add(inp)
                    changed = True
    return [g[0] for g in gates if g[0] in reachable]


def evaluate_with_subst(W: dict, gates: list, target: str, new_op: str,
                       new_inputs: tuple, output_names: list,
                       primary_inputs: set):
    """Apply substitution `target = new_op(new_inputs)`, recompute downstream
    bitvectors, and return (verified_correct, n_gates_after_dce, new_gates).
    """
    # Build a working copy of gates with the substitution applied
    new_gates = []
    for name, op, ins in gates:
        if name == target:
            new_gates.append((name, new_op, new_inputs))
        else:
            new_gates.append((name, op, ins))

    # Re-simulate from scratch to verify correctness
    Wv = {n: W[n] for n in primary_inputs}

    def apply(name, op, ins):
        if op == "AND": Wv[name] = Wv[ins[0]] & Wv[ins[1]]
        elif op == "OR":  Wv[name] = Wv[ins[0]] | Wv[ins[1]]
        elif op == "XOR": Wv[name] = Wv[ins[0]] ^ Wv[ins[1]]
        elif op == "NOT": Wv[name] = ALL_ONE ^ Wv[ins[0]]

    for name, op, ins in new_gates:
        # Check that all inputs are already computed (topological)
        for inp in ins:
            if inp not in Wv:
                # missing dependency — substitution introduced a forward ref
                return False, len(new_gates), new_gates
        apply(name, op, ins)

    # Verify outputs match the originals
    for o in output_names:
        if Wv.get(o) != W[o]:
            return False, len(new_gates), new_gates

    # Now DCE
    reachable_names = dce(new_gates, output_names, primary_inputs)
    return True, len(reachable_names), new_gates


def find_substitutions(W, gates, primary_inputs, output_names):
    """Find substitution candidates (target, op, i, j) such that applying
    them yields a strictly smaller netlist after DCE."""
    inputs = list(primary_inputs)
    gate_names = [g[0] for g in gates]
    all_names = inputs + gate_names

    # Pre-compute name -> gate map for current ops
    name_to_gate = {g[0]: g for g in gates}

    # bv -> set of names with that bv
    bv_to_names = {}
    for name in all_names:
        bv_to_names.setdefault(W[name], set()).add(name)

    base_count = len(gates)
    print(f"Base netlist: {base_count} gates")

    candidates = []
    for target in gate_names:
        cur_op, cur_in = name_to_gate[target][1], name_to_gate[target][2]
        target_bv = W[target]
        # Search every (i, j) pair for op(i, j) == target_bv where (i, j) ≠ cur_in
        for i_idx, i_name in enumerate(all_names):
            if i_name == target: continue
            bv_i = W[i_name]
            for j_idx in range(i_idx + 1, len(all_names)):
                j_name = all_names[j_idx]
                if j_name == target: continue
                bv_j = W[j_name]
                for op_name, bv in (
                    ("AND", bv_i & bv_j),
                    ("OR",  bv_i | bv_j),
                    ("XOR", bv_i ^ bv_j),
                ):
                    if bv != target_bv: continue
                    # Skip exact same expression
                    if op_name == cur_op and set([i_name, j_name]) == set(cur_in):
                        continue
                    candidates.append((target, op_name, i_name, j_name))

    print(f"Candidate substitutions: {len(candidates)}")

    # Apply each, DCE, see if smaller
    wins = []
    for target, op, i, j in candidates:
        # Skip if subst introduces a forward reference (i or j defined AFTER target in original order)
        target_idx = gate_names.index(target)
        for ref in (i, j):
            if ref in primary_inputs: continue
            ref_idx = gate_names.index(ref)
            if ref_idx >= target_idx:
                # forward ref — skip
                break
        else:
            # No forward ref. Try the substitution.
            ok, new_count, new_gates = evaluate_with_subst(
                W, gates, target, op, (i, j), output_names, primary_inputs
            )
            if ok and new_count < base_count:
                wins.append((target, op, i, j, new_count, new_gates))

    return wins, candidates


def main():
    print("Building 64-gate simulation...")
    W, gates = simulate_64gate()
    primary_inputs = {"a0","a1","a2","a3","b0","b1","b2","b3"}
    output_names = [f"y{i}" for i in range(9)]

    wins, cands = find_substitutions(W, gates, primary_inputs, output_names)
    print()
    if not wins:
        print(f"No DCE-net-positive substitutions found among {len(cands)} candidates.")
        print("→ G4-with-DCE = NO HIT.")
        print("  Confirms 64-gate netlist is locally saturated under depth-1 substitution + DCE.")
        return

    print(f"Found {len(wins)} substitution(s) yielding strict gate-count reduction:")
    for target, op, i, j, new_count, _ in wins[:30]:
        print(f"  {target} := {op}({i}, {j})  →  {new_count} gates "
              f"(saves {len(gates) - new_count})")
    if len(wins) > 30:
        print(f"  ... and {len(wins) - 30} more.")

    # Pick the one with biggest saving
    wins.sort(key=lambda w: w[4])
    target, op, i, j, new_count, new_gates = wins[0]
    print()
    print(f"Best: {target} := {op}({i}, {j})  →  {new_count} gates "
          f"(saves {len(gates) - new_count})")


if __name__ == "__main__":
    main()
