"""
BDD-based multi-output synthesis for the FP4 magnitude function.

Uses the `dd` library to build shared BDDs across all 8 output bits, then
extracts a circuit by traversing the BDD and counting shared AND/OR nodes.

The shared BDD approach reveals opportunities for subexpression sharing that
per-bit Espresso misses.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from eval_circuit import FP4_TABLE

_mag_to_code = {0.0:0,1.5:1,3.0:2,6.0:3,0.5:4,1.0:5,2.0:6,4.0:7}
REMAP = [(1 if v < 0 else 0) << 3 | _mag_to_code[abs(v)] for v in FP4_TABLE]


def build_mag_truth_table():
    """6->8 magnitude truth table: returns dict {inp6: out8}."""
    seen = {}
    for a in range(16):
        for b in range(16):
            a_mag = REMAP[a] & 7
            b_mag = REMAP[b] & 7
            inp = (a_mag << 3) | b_mag
            a_val = abs(FP4_TABLE[a])
            b_val = abs(FP4_TABLE[b])
            mag = int(round(a_val * b_val * 4))
            seen[inp] = mag
    return seen


def build_full_signed_tt():
    """8->9 full signed truth table: {inp8: qi9}."""
    rows = {}
    for a in range(16):
        for b in range(16):
            a_code = REMAP[a]; b_code = REMAP[b]
            inp = (a_code << 4) | b_code
            qi9 = int(round(FP4_TABLE[a] * FP4_TABLE[b] * 4)) & 0x1FF
            rows[inp] = qi9
    return rows


def analyze_bdd_sharing(tt, n_in, n_out, label):
    """
    Build shared BDDs for all n_out bits and analyze node sharing.
    This gives a lower bound on the number of distinct sub-functions.
    """
    from dd.autoref import BDD
    print(f"\n=== BDD analysis: {label} ({n_in}-in {n_out}-out) ===")

    bdd = BDD()
    # Declare variables in good order (try natural order first)
    var_names = [f'x{i}' for i in range(n_in)]
    bdd.declare(*var_names)

    # Build BDD for each output bit
    bdds = []
    for bit in range(n_out):
        # Build the minterms
        ones = [inp for inp in range(2**n_in) if inp in tt and ((tt[inp] >> bit) & 1)]
        # Build BDD via OR of minterms
        f = bdd.false
        for m in ones:
            cube = bdd.true
            for i, v in enumerate(var_names):
                if (m >> (n_in - 1 - i)) & 1:
                    cube = bdd.apply('and', cube, bdd.var(v))
                else:
                    cube = bdd.apply('and', cube, ~bdd.var(v))
            f = bdd.apply('or', f, cube)
        bdds.append(f)

    # Count shared BDD nodes
    total_nodes = len(bdd)
    print(f"  Total BDD nodes (shared): {total_nodes}")

    # Per-bit node counts (unshared)
    per_bit_nodes = []
    for bit, f in enumerate(bdds):
        n = len(bdd.descendants([f]))
        per_bit_nodes.append(n)
        print(f"  Bit {bit}: {n} BDD nodes")

    total_unshared = sum(per_bit_nodes)
    print(f"  Total nodes (unshared): {total_unshared}")
    print(f"  Sharing factor: {total_unshared}/{total_nodes} = {total_unshared/max(1,total_nodes):.2f}x")
    print(f"  Note: BDD nodes != circuit gates, but sharing ratio guides potential savings")

    return total_nodes, total_unshared


def shared_sop_analysis(tt, n_in, n_out, label):
    """
    Run Espresso per bit, then count unique cubes (AND terms) across all bits.
    This is the 'two-level with perfect sharing' lower bound.
    """
    from pyeda.inter import espresso_tts, truthtable, exprvar
    print(f"\n=== Shared SOP analysis: {label} ({n_in}-in {n_out}-out) ===")

    xs = [exprvar(f'x{i}') for i in range(n_in)]

    all_cubes_str = []  # list of sets (one per output bit)
    for bit in range(n_out):
        tt_str = ''.join(
            str((tt[inp] >> bit) & 1) if inp in tt else '-'
            for inp in range(2**n_in)
        )
        f = truthtable(xs, tt_str)
        (f_min,) = espresso_tts(f)
        dnf = f_min.to_dnf()
        if hasattr(dnf, 'xs'):
            cubes = {str(t) for t in dnf.xs}
        elif str(dnf) not in ('0', '1', 'False', 'True'):
            cubes = {str(dnf)}
        else:
            cubes = set()
        all_cubes_str.append(cubes)
        print(f"  Bit {bit}: {len(cubes)} cubes")

    total_instances = sum(len(c) for c in all_cubes_str)
    unique_cubes = set()
    for c in all_cubes_str: unique_cubes |= c
    shared_count = total_instances - len(unique_cubes)

    print(f"  Total cube instances: {total_instances}")
    print(f"  Unique cubes: {len(unique_cubes)}")
    print(f"  Shared cubes (appear in >=2 bits): {shared_count}")
    print(f"  With perfect AND sharing: {len(unique_cubes)} AND + ~{total_instances - n_out} OR = ~{len(unique_cubes) + total_instances - n_out} gates")
    print(f"  (vs current magnitude: 46 gates for S-dec+AND+OR)")

    return unique_cubes, all_cubes_str


def analyze_output_reachability(tt, n_in):
    """Find which input combinations are actually reachable vs don't-cares."""
    reachable = {inp for inp in tt}
    total = 2**n_in
    dc = total - len(reachable)
    print(f"\n=== Reachability: {len(reachable)}/{total} inputs reachable, {dc} don't-cares ===")
    print(f"  Don't-care ratio: {dc/total:.1%}")
    print(f"  (Espresso uses don't-cares; BDD approach above ignores them)")


def analyze_algebraic_structure(tt):
    """
    Analyze the 6-in 8-out magnitude function for algebraic structure
    that can be exploited in multi-level synthesis.
    """
    print("\n=== Algebraic structure of magnitude function ===")
    nonzero = {inp: out for inp, out in tt.items() if out > 0}

    # How many bits are set in each output?
    bit_counts = {}
    for inp, out in tt.items():
        bc = bin(out).count('1')
        bit_counts[bc] = bit_counts.get(bc, 0) + 1
    print(f"  Output popcount distribution:")
    for k in sorted(bit_counts):
        print(f"    {k} bits set: {bit_counts[k]} inputs")

    # Which input pairs (a_mag, b_mag) give which output?
    # Focus on the 3 K-classes
    k1_count = k3_count = k9_count = k0_count = 0
    for inp in range(64):
        a_mag = (inp >> 3) & 7
        b_mag = inp & 7
        a1 = (a_mag >> 2) & 1  # bit 2 of 3-bit code (MSB)
        b1 = (b_mag >> 2) & 1
        if a_mag == 0 or b_mag == 0:
            k0_count += 1
        elif a1 == 1 and b1 == 1:
            k9_count += 1
        elif a1 == 0 and b1 == 0:
            k1_count += 1
        else:
            k3_count += 1

    print(f"\n  K-type distribution (all 64 6-bit inputs):")
    print(f"    K=0 (zero):  {k0_count} inputs")
    print(f"    K=1 (pure power-of-2):  {k1_count} inputs")
    print(f"    K=3 (one M=1): {k3_count} inputs")
    print(f"    K=9 (both M=1): {k9_count} inputs")

    # Count distinct outputs per K-class
    print(f"\n  Distinct output values per K-class (6-in 8-out):")
    for k_name, k_pred in [
        ('K=1', lambda a,b: a!=0 and b!=0 and not((a>>2)&1) and not((b>>2)&1)),
        ('K=3', lambda a,b: a!=0 and b!=0 and (((a>>2)&1) != ((b>>2)&1))),
        ('K=9', lambda a,b: a!=0 and b!=0 and ((a>>2)&1) and ((b>>2)&1)),
    ]:
        vals = set(tt[(a<<3)|b] for a in range(8) for b in range(8)
                   if k_pred(a,b) and (a<<3|b) in tt)
        print(f"    {k_name}: {len(vals)} distinct values: {sorted(vals)}")


if __name__ == "__main__":
    mag_tt = build_mag_truth_table()
    full_tt = build_full_signed_tt()

    analyze_output_reachability(mag_tt, 6)
    analyze_algebraic_structure(mag_tt)

    print("\n--- Magnitude function (6-in 8-out, 64 rows) ---")
    shared_sop_analysis(mag_tt, 6, 8, "magnitude")

    print("\n--- Full signed function (8-in 9-out) ---")
    shared_sop_analysis(full_tt, 8, 9, "full signed")
