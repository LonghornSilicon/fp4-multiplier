"""
Joint synthesis of E-sum + S-decoder (4-in 7-out).

Currently: E-sum (7 gates) + S-decoder (13 gates) = 20 gates.
This experiment asks: can we compute sh0..sh6 directly from (a2,a3,b2,b3)?

The S = (a2,a3)_bin + (b2,b3)_bin, S ∈ {0..6}, output is one-hot.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from pyeda.inter import espresso_tts, truthtable, exprvar

def build_esumdec_tt():
    """4-in 7-out truth table: (a2,a3,b2,b3) -> (sh0..sh6) one-hot."""
    rows = {}
    for a2 in range(2):
        for a3 in range(2):
            for b2 in range(2):
                for b3 in range(2):
                    s = 2*a2 + a3 + 2*b2 + b3
                    inp = (a2 << 3) | (a3 << 2) | (b2 << 1) | b3
                    out = 1 << (6 - s)   # sh0 = bit 6, sh6 = bit 0
                    rows[inp] = out
    return rows


def espresso_per_bit(rows, n_in=4, n_out=7, label=""):
    from pyeda.inter import espresso_tts, truthtable, exprvar
    xs = [exprvar(f'x{i}') for i in range(n_in)]
    total_and = 0
    total_or = 0
    print(f"\n=== Espresso per-bit: {label} ({n_in}-in {n_out}-out) ===")
    bit_cubes = []
    for bit in range(n_out):
        tt_str = ''.join(
            str((rows[inp] >> bit) & 1) if inp in rows else '-'
            for inp in range(2**n_in)
        )
        f = truthtable(xs, tt_str)
        (f_min,) = espresso_tts(f)
        dnf = f_min.to_dnf()
        if hasattr(dnf, 'xs'):
            cubes = list(dnf.xs)
        elif str(dnf) not in ('0', '1', 'False', 'True'):
            cubes = [dnf]
        else:
            cubes = []
        bit_cubes.append(cubes)
        n_terms = len(cubes)
        total_and += n_terms
        total_or += max(0, n_terms - 1)
        print(f"  sh{6-bit}: {n_terms} terms -> {[str(c) for c in cubes]}")
    print(f"  Total AND: {total_and}, OR: {total_or}, gates: {total_and+total_or}")
    return bit_cubes


def shared_cube_analysis(bit_cubes, n_out=7):
    """Find shared AND terms across output bits."""
    print("\n=== Shared cube analysis ===")
    cubes_str = [set(str(c) for c in cs) for cs in bit_cubes]
    total_instances = sum(len(c) for c in cubes_str)
    unique = set()
    for c in cubes_str: unique |= c
    shared = total_instances - len(unique)
    print(f"  Total cube instances: {total_instances}")
    print(f"  Unique cubes: {len(unique)}")
    print(f"  Shared (appear in >=2 outputs): {shared}")
    print(f"  With perfect sharing: {len(unique)} AND + ~{total_instances - n_out} OR = ~{len(unique) + total_instances - n_out} gates")
    print(f"  (vs current: 20 gates for E-sum+decoder)")

    # Show which cubes are shared
    from collections import Counter
    cube_counts = Counter()
    for cs in cubes_str:
        for c in cs: cube_counts[c] += 1
    print(f"\n  Most shared cubes:")
    for cube, count in cube_counts.most_common(10):
        if count > 1:
            print(f"    '{cube}' appears in {count} output bits")


def manual_analysis():
    """Manual analysis: what structure does a joint 4->7 circuit have?"""
    print("\n=== Manual structural analysis ===")
    print("  The function S = 2*a2 + a3 + 2*b2 + b3, one-hot output")
    print("  S = (a2+b2)*2 + (a3+b3), range 0..6")
    print()
    print("  Observations:")
    print("  1. S is symmetric in (a2,a3) <-> (b2,b3) [commutative]")
    print("  2. a3+b3 is a 1-bit sum with carry: lsb=XOR(a3,b3), carry=AND(a3,b3)")
    print("  3. a2+b2 is similar: lsb=XOR(a2,b2), carry=AND(a2,b2)")
    print("  4. S = 2*(a2+b2) + (a3+b3) -- this IS the E-sum!")
    print()
    # Key: is there a more compact direct implementation?
    # The sh_j signals can be expressed as:
    # sh0 = (S==0) = NOT(a2) AND NOT(b2) AND NOT(a3) AND NOT(b3) -- 4-input AND = 3 gates
    # sh1 = (S==1) = NOT(a2) AND NOT(b2) AND XOR(a3,b3) -- uses XOR = ...
    # sh2 = (S==2) = (2*(a2+b2) + (a3+b3) == 2)
    #              = (a2+b2==1) AND (a3+b3==0) OR (a2+b2==0) AND (a3+b3==2)
    #              = XOR(a2,b2) AND NOR(a3,b3) OR NOR(a2,b2) AND AND(a3,b3)
    # etc.
    print("  sh0 (S=0): a2=b2=a3=b3=0")
    print("    Formula: AND(NOT(a2), NOT(b2), NOT(a3), NOT(b3))")
    print("    Gates: 2 NOT (shared with others) + 1 OR(a2,b2) + 1 AND with OR(a3,b3) = complex")
    print()

    # Let c0 = carry of a3+b3, s0 = XOR(a3,b3)  [1 AND + 1 XOR = 2 gates]
    # Let c1 = carry of a2+b2, s1 = XOR(a2,b2)  [1 AND + 1 XOR = 2 gates]
    # Then S = (c1, s1 XOR c0, s0 XOR carry... wait, it's just an adder
    # The 3-bit sum s2,s1,s0 from the E-sum uses the same logic as above:
    # s0 = XOR(a3,b3), c0 = AND(a3,b3)
    # s1x = XOR(a2,b2), s1 = XOR(s1x, c0)
    # s2 = carry-out = AND(a2,b2) OR AND(XOR(a2,b2), AND(a3,b3))
    #     = OR(AND(a2,b2), AND(XOR(a2,b2), AND(a3,b3)))
    # Total: 7 gates for E-sum ✓

    # Once we have (s2,s1,s0), the decoder needs 13 gates (or less? TBD)
    # The question is: jointly, can we do it in < 20?

    print("  Direct formulas for each sh_j using raw inputs a2,a3,b2,b3:")

    def compute_sh(s, a2, a3, b2, b3):
        return (2*a2 + a3 + 2*b2 + b3) == s

    from itertools import product
    for target_s in range(7):
        ones = [(a2,a3,b2,b3) for a2,a3,b2,b3 in product(range(2), repeat=4)
                if compute_sh(target_s, a2, a3, b2, b3)]
        print(f"    sh{target_s} (S={target_s}): {len(ones)} minterms")


def try_xor_structure():
    """Analyze whether XOR-based formulas for sh_j are more compact."""
    print("\n=== XOR structure analysis ===")
    # Key intermediate signals:
    # c0 = AND(a3,b3)  [carry of LSB sum]
    # s0 = XOR(a3,b3)  [sum bit 0]
    # c1 = AND(a2,b2)  [carry of bit-1 sum]
    # s1 = XOR(a2,b2)  [partial sum bit 1, before carry]
    # s1_full = XOR(s1, c0) = XOR(XOR(a2,b2), AND(a3,b3))  [full sum bit 1]
    # s2 = OR(c1, AND(s1, c0))  [sum bit 2 = carry out]
    #     = OR(AND(a2,b2), AND(XOR(a2,b2), AND(a3,b3)))

    print("  Intermediate signals from E-sum:")
    print("    c0 = AND(a3,b3): 1 gate")
    print("    s0 = XOR(a3,b3): 1 gate (= XOR(a3,b3))")
    print("    s1x = XOR(a2,b2): 1 gate")
    print("    c1 = AND(a2,b2): 1 gate")
    print("    s1 = XOR(s1x, c0): 1 gate")
    print("    s2 = OR(c1, AND(s1x, c0)): 2 gates")
    print("    Total E-sum: 7 gates")
    print()
    print("  Then S-decoder: 13 gates (NOT x3, AND x4 for u_xy, AND x6 for sh_j)")
    print("  Total: 20 gates")
    print()
    print("  Alternative: merge carry signals into decoder")
    print("  sh0 = (S=0) = AND(NOT(s2), NOT(s1), NOT(s0)) = AND(NOT(s2), NOT(s1), NOT(XOR(a3,b3)))")
    print("       = AND(ns2, ns1, XNOR(a3,b3))")
    print("       = AND(ns2, AND(ns1, XNOR(a3,b3)))  -- uses XNOR = XOR+NOT = 2 gates")
    print("       But in current circuit: sh0 = AND(u00, ns0) = AND(AND(ns2,ns1), ns0) = 2 AND gates (using 3 intermediates)")
    print()
    print("  Key question: is there a 4->7 circuit in fewer than 20 gates?")
    print("  The Espresso SOP analysis above gives the two-level upper bound.")
    print("  For multi-level: algebraic factoring might give ~14-16 gates.")


if __name__ == "__main__":
    tt = build_esumdec_tt()
    manual_analysis()
    try_xor_structure()
    bit_cubes = espresso_per_bit(tt, n_in=4, n_out=7, label="E-sum+decoder")
    shared_cube_analysis(bit_cubes)
