"""
Phase 0 triage gates G1, G3, G4 on the LonghornSilicon 64-gate netlist.

G1: For every wire, compute its 256-input care-set bitvector. Look for
    duplicate bitvectors (= identical truth tables) — eSLIM saturates locally
    but a global duplicate would still be a free 1-gate kill via DCE.

G3: Output mux algebra. Check if OR(w_24, w_52) or XOR(w_24, w_52) equals
    an existing wire bitvector (would let us factor w_34 AND (w_24|w_52) and
    cancel a downstream gate).

G4: Depth-2 resub. For every pair (i,j) of wires, compute AND/OR/XOR of
    their bitvectors and check whether the result equals any other wire's
    bitvector. A hit means we can replace the wire whose value matches with
    a simple 2-input expression of (i,j) — and if its current expression
    uses different parents, we may DCE those parents.

Care set: all 256 (a, b) input pairs over the σ = (0,1,2,3,6,7,4,5) remap.
We use the FULL 256 since their submission is verified on all 256 — even
duplicate code points should be functionally equivalent.

Outputs: text summary to stdout. No file writes (read-only triage).
"""
from __future__ import annotations
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)) + "/..")

# Their σ = (0,1,2,3,6,7,4,5) magnitude permutation
# Their convention: a[3]=sign, a[0]=LSB
_mag_to_code_long = {
    0.0: 0b0000, 0.5: 0b0001, 1.0: 0b0010, 1.5: 0b0011,
    2.0: 0b0110, 3.0: 0b0111, 4.0: 0b0100, 6.0: 0b0101,
}
# FP4 table for our harness
FP4_TABLE = [0.0, 0.5, 1.0, 1.5, 2.0, 3.0, 4.0, 6.0,
             0.0, -0.5, -1.0, -1.5, -2.0, -3.0, -4.0, -6.0]
INPUT_REMAP = []
for v in FP4_TABLE:
    s = 1 if v < 0 else 0
    INPUT_REMAP.append((s << 3) | _mag_to_code_long[abs(v)])

# Build 256-input bitvector representation
# Each "input pair" is (a_orig, b_orig) ∈ {0..15} × {0..15}, mapped via INPUT_REMAP.
# We encode each wire as a Python big int with 256 bits, indexed by
# (a_orig * 16 + b_orig).

N_INPUTS = 256

def build_input_bitvectors():
    """Return 8-tuple of bitvectors: (a0,a1,a2,a3,b0,b1,b2,b3) using their
    convention a[3]=sign, a[0]=LSB.
    Index 0..255 = (a_orig << 4) | b_orig in our harness order; we apply
    INPUT_REMAP to get actual circuit input bits."""
    a0=a1=a2=a3=b0=b1=b2=b3 = 0
    for idx in range(256):
        a_orig = (idx >> 4) & 0xF
        b_orig = idx & 0xF
        a_code = INPUT_REMAP[a_orig]   # 4-bit code with bit3=sign, bit0=LSB
        b_code = INPUT_REMAP[b_orig]
        # Their convention: a[0]=LSB of code, a[3]=sign(MSB)
        bit = 1 << idx
        if a_code & 1:        a0 |= bit
        if (a_code >> 1) & 1: a1 |= bit
        if (a_code >> 2) & 1: a2 |= bit
        if (a_code >> 3) & 1: a3 |= bit
        if b_code & 1:        b0 |= bit
        if (b_code >> 1) & 1: b1 |= bit
        if (b_code >> 2) & 1: b2 |= bit
        if (b_code >> 3) & 1: b3 |= bit
    return a0,a1,a2,a3,b0,b1,b2,b3


ALL_ONE = (1 << N_INPUTS) - 1


def simulate_64gate():
    """Replay the 64-gate body from longhorn_verify.py at the bitvector
    level. Returns (wires_dict, gates_list). wires_dict maps name -> bv.
    gates_list is the ordered list of (name, op, in_names) tuples for
    later analysis."""
    a0,a1,a2,a3,b0,b1,b2,b3 = build_input_bitvectors()
    W = {"a0":a0,"a1":a1,"a2":a2,"a3":a3,"b0":b0,"b1":b1,"b2":b2,"b3":b3}
    gates = []

    def AND(name, x, y):
        W[name] = W[x] & W[y]
        gates.append((name, "AND", (x, y)))
    def OR(name, x, y):
        W[name] = W[x] | W[y]
        gates.append((name, "OR", (x, y)))
    def XOR(name, x, y):
        W[name] = W[x] ^ W[y]
        gates.append((name, "XOR", (x, y)))
    def NOT(name, x):
        W[name] = ALL_ONE ^ W[x]
        gates.append((name, "NOT", (x,)))

    # Body of write_your_multiplier_here from longhorn_verify.py
    AND("w_35", "a1","a2"); AND("w_32","b1","b2")
    XOR("w_68","w_35","w_32"); OR("w_22","w_68","w_35")
    XOR("w_67","a2","b2"); XOR("w_37","w_22","w_67")
    AND("w_36","a2","b2"); OR("w_65","w_37","w_36")
    AND("w_42","a0","b0"); NOT("not_68","w_68")
    AND("w_43","w_42","not_68"); XOR("w_45","w_65","w_43")
    NOT("not_45","w_45"); OR("w_66","w_68","w_42")
    OR("w_33","b1","b2"); OR("w_39","a1","a2")
    AND("w_38","w_33","w_39"); AND("w_11","w_66","w_38")
    XOR("w_53","w_37","w_11"); AND("w_41","b0","w_39")
    AND("w_13","a0","w_33"); XOR("w_48","w_41","w_13")
    XOR("w_25","w_42","w_45"); AND("w_73","w_48","w_68")
    XOR("w_21","w_25","w_73"); XOR("w_58","w_48","w_21")
    XOR("w_26","w_37","w_58"); OR("w_47","w_53","w_26")
    NOT("not_47","w_47"); XOR("w_40","w_73","w_38")
    XOR("w_55","w_40","w_53"); NOT("not_55","w_55")
    NOT("not_58","w_58"); NOT("not_65","w_65")
    XOR("w_34","a3","b3"); XOR("w_15","w_37","w_25")
    AND("w_46","w_45","w_15"); AND("w_50","w_43","w_15")
    AND("y0","not_65","w_43"); AND("w_57","w_25","not_55")
    AND("w_10","w_34","w_57"); AND("w_18","w_55","not_45")
    AND("w_28","w_34","w_18"); AND("w_64","not_58","w_47")
    AND("w_59","w_34","w_64"); AND("w_71","w_65","not_47")
    AND("w_69","w_58","not_65"); OR("w_24","y0","w_69")
    AND("w_70","w_34","w_24"); XOR("y2","w_18","w_70")
    AND("w_61","w_43","w_70"); OR("w_14","w_28","w_70")
    XOR("y3","w_64","w_14"); OR("w_49","w_59","w_14")
    XOR("y4","w_57","w_49"); OR("w_17","w_49","w_10")
    XOR("y5","w_17","w_71"); OR("w_52","w_17","w_71")
    AND("w_51","w_34","w_52"); OR("w_56","w_26","w_51")
    AND("y8","w_34","w_56"); XOR("y7","w_50","y8")
    XOR("y6","w_46","w_51"); XOR("y1","w_69","w_61")

    return W, gates


def g1_duplicate_bitvectors(W: dict, gates: list):
    """G1: Look for any two NAMED wires with identical bitvectors."""
    print("=" * 60)
    print("G1: Duplicate-bitvector search on 64-gate netlist")
    print("=" * 60)
    by_bv = {}
    # only check internal wires (gates), not primary inputs
    inputs = {"a0","a1","a2","a3","b0","b1","b2","b3"}
    for name in W:
        if name in inputs: continue
        bv = W[name]
        by_bv.setdefault(bv, []).append(name)

    duplicates = {bv: names for bv, names in by_bv.items() if len(names) > 1}
    if not duplicates:
        print("  No duplicate bitvectors found among", len(W) - len(inputs), "internal wires.")
        print("  Conclusion: every gate computes a unique function over the 256 inputs.")
        print("  → eSLIM-level saturation confirmed at this level. G1 = NO HIT.")
        return False
    print(f"  Found {len(duplicates)} bitvector(s) with multiple wires:")
    for bv, names in duplicates.items():
        pop = bin(bv).count("1")
        print(f"    bv popcount={pop}: {names}")
    print("  → POTENTIAL FREE GATE — investigate which one to keep + DCE the others.")
    return True


def g3_output_mux_algebra(W: dict, gates: list):
    """G3: Test factoring w_34 AND (w_24 ⊕|⊕|XOR ... w_52)."""
    print()
    print("=" * 60)
    print("G3: Output mux algebra check (w_34 × {w_24, w_52})")
    print("=" * 60)
    w_24 = W["w_24"]; w_52 = W["w_52"]; w_34 = W["w_34"]
    print(f"  w_24 popcount={bin(w_24).count('1')}, w_52 popcount={bin(w_52).count('1')}")
    print(f"  w_34 popcount={bin(w_34).count('1')}  (sign bit)")

    or_24_52 = w_24 | w_52
    xor_24_52 = w_24 ^ w_52
    and_24_52 = w_24 & w_52

    print(f"  OR(w_24,w_52) popcount={bin(or_24_52).count('1')}")
    print(f"  XOR(w_24,w_52) popcount={bin(xor_24_52).count('1')}")
    print(f"  AND(w_24,w_52) popcount={bin(and_24_52).count('1')}")

    # Check whether any of these match an existing wire
    inputs = {"a0","a1","a2","a3","b0","b1","b2","b3"}
    targets = [("OR(w_24,w_52)", or_24_52), ("XOR(w_24,w_52)", xor_24_52),
               ("AND(w_24,w_52)", and_24_52)]
    hit = False
    for label, bv in targets:
        matches = [name for name in W if W[name] == bv and name not in inputs]
        if matches:
            print(f"  HIT: {label} == {matches}")
            hit = True
    if not hit:
        print("  No existing wire matches OR/XOR/AND of (w_24,w_52). G3 = NO HIT.")
    return hit


def g4_pair_resub(W: dict, gates: list, max_pairs: int = 200000):
    """G4: For every pair of wires (i,j), compute all four 2-input ops over
    their bitvectors. If any equals an existing wire's bitvector AND uses
    different parents than that wire's current definition, we have a
    candidate substitution."""
    print()
    print("=" * 60)
    print("G4: Depth-2 pair-resub on 64-gate netlist")
    print("=" * 60)
    # Index wires for ordered iteration
    inputs = ["a0","a1","a2","a3","b0","b1","b2","b3"]
    gate_names = [g[0] for g in gates]
    all_names = inputs + gate_names

    # Map bitvector -> set of wire names
    bv_to_names = {}
    for name in all_names:
        bv_to_names.setdefault(W[name], set()).add(name)

    n = len(all_names)
    n_pairs = n * (n - 1) // 2
    print(f"  Wires: {n} ({len(inputs)} inputs + {len(gates)} gates)")
    print(f"  Pairs to check: {n_pairs}")

    hits = []
    checked = 0
    for i in range(n):
        bvi = W[all_names[i]]
        for j in range(i+1, n):
            bvj = W[all_names[j]]
            for op_name, bv in (
                ("AND", bvi & bvj),
                ("OR",  bvi | bvj),
                ("XOR", bvi ^ bvj),
            ):
                # Does this match any wire whose current op uses DIFFERENT inputs?
                if bv in bv_to_names:
                    for target in bv_to_names[bv]:
                        # Skip if target is one of (i, j) themselves
                        if target == all_names[i] or target == all_names[j]:
                            continue
                        # If target is a primary input, it can't be replaced
                        if target in inputs: continue
                        # Find target's current gate definition
                        cur = next((g for g in gates if g[0] == target), None)
                        if cur is None: continue
                        cur_op = cur[1]
                        cur_in = cur[2]
                        # Skip if same expression (would be a no-op resub)
                        if cur_op == op_name and set(cur_in) == {all_names[i], all_names[j]}:
                            continue
                        hits.append((target, op_name, all_names[i], all_names[j],
                                     cur_op, cur_in))
            checked += 1
            if checked > max_pairs: break
        if checked > max_pairs: break

    if not hits:
        print(f"  No pair-resub hit. G4 = NO HIT.")
        return False
    print(f"  Found {len(hits)} candidate substitution(s):")
    # Show first 20
    for h in hits[:20]:
        target, op, i_name, j_name, cur_op, cur_in = h
        print(f"    {target} = {op}({i_name}, {j_name})  "
              f"(currently {cur_op}({', '.join(cur_in)}))")
    if len(hits) > 20:
        print(f"    ... and {len(hits) - 20} more")
    return True


def main():
    print("Building bitvector simulation of LonghornSilicon 64-gate netlist...")
    W, gates = simulate_64gate()
    n_internal = len(W) - 8  # subtract input wires
    print(f"  Simulated {len(gates)} gates / {n_internal} internal wires.")
    print(f"  Output wires: y0..y8 present: {all(f'y{i}' in W for i in range(9))}")
    print()

    # Sanity check: y8 should be 0 for all (a, b) where neither has nonzero magnitude AND signs differ
    # Quick spot check: for input pair (0=+0, 0=+0), all outputs should be 0.
    test_idx = 0  # a_orig=0, b_orig=0
    for k in range(9):
        bit = (W[f"y{k}"] >> test_idx) & 1
        if bit != 0:
            print(f"  WARNING: y{k} non-zero at input (0,0)")

    g1 = g1_duplicate_bitvectors(W, gates)
    g3 = g3_output_mux_algebra(W, gates)
    g4 = g4_pair_resub(W, gates)

    print()
    print("=" * 60)
    print("Phase 0 Triage Summary")
    print("=" * 60)
    print(f"  G1 (duplicate bitvectors): {'HIT' if g1 else 'NO HIT'}")
    print(f"  G3 (output mux algebra):   {'HIT' if g3 else 'NO HIT'}")
    print(f"  G4 (pair resub):           {'HIT' if g4 else 'NO HIT'}")
    if g1 or g3 or g4:
        print("  → Investigate hits before installing tooling.")
    else:
        print("  → All triage gates clean. 64-gate netlist is locally saturated")
        print("    at the gate level. Proceeding to Phase 1 (toolchain install)")
        print("    is justified.")


if __name__ == "__main__":
    main()
