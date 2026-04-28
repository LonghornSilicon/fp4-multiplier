"""
PyEDA Espresso SOP minimization for FP4 sub-functions.
Runs two-level minimization and reports SOP gate costs.

Multi-output Espresso shares prime implicants across outputs.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from pyeda.inter import espresso_tts
from eval_circuit import FP4_TABLE

_mag_to_code = {0.0:0,1.5:1,3.0:2,6.0:3,0.5:4,1.0:5,2.0:6,4.0:7}
REMAP = [(1 if v < 0 else 0) << 3 | _mag_to_code[abs(v)] for v in FP4_TABLE]

def build_mag_tt():
    """6→8 magnitude truth table as list of (inp6, out8) integer pairs."""
    seen = {}
    for a in range(16):
        for b in range(16):
            a_mag = REMAP[a] & 7; b_mag = REMAP[b] & 7
            inp = (a_mag << 3) | b_mag
            mag = int(round(abs(FP4_TABLE[a]) * abs(FP4_TABLE[b]) * 4))
            seen[inp] = mag
    return [(inp, seen[inp]) for inp in range(64)]

def build_full_tt():
    """8→9 full signed circuit truth table."""
    rows = {}
    for a in range(16):
        for b in range(16):
            a_code = REMAP[a]; b_code = REMAP[b]
            inp = (a_code << 4) | b_code
            qi9 = int(round(FP4_TABLE[a] * FP4_TABLE[b] * 4)) & 0x1FF
            # Convert to MSB-first 9-bit value
            pla_out = sum(((qi9 >> (8-bit)) & 1) << (8-bit) for bit in range(9))
            rows[inp] = qi9
    return rows

def espresso_mag():
    """Run Espresso on magnitude (6→8) per-bit and jointly."""
    tt = build_mag_tt()

    print("=== Magnitude function: Espresso SOP minimization ===")
    print("Per-bit minimization (independent):")
    total_and = 0
    total_or = 0
    for bit in range(7, -1, -1):
        ones  = [inp for inp, out in tt if (out >> bit) & 1]
        zeros = [inp for inp, out in tt if not ((out >> bit) & 1)]
        # Build TT for pyeda
        # espresso_tts takes arrays of 0/1/-1 (don't care) for each minterm
        # We'll use the expression-based interface instead
        n_terms_sop = count_espresso_terms(6, ones, zeros)
        total_and += n_terms_sop
        total_or += max(0, n_terms_sop - 1)
        print(f"  m{bit}: {len(ones):2d} ones -> {n_terms_sop} PI terms "
              f"({n_terms_sop} AND + {max(0,n_terms_sop-1)} OR = {max(0, 2*n_terms_sop-1)} gates)")

    print(f"  Per-bit total (naive sum): {total_and} AND + {total_or} OR = {total_and+total_or} gates")
    print(f"  (compare current: 46 gates for S-decoder+AND-terms+mag-OR)")

def count_espresso_terms(n_vars, ones, zeros):
    """
    Run Espresso on a single-output function and count the SOP terms.
    Uses pyeda's BDD/SOP minimization via truth table interface.
    """
    from pyeda.inter import truthtable, espresso_tts
    # Build truth table: indexed 0..2^n-1, value = 0/1/X
    # For don't-cares: inputs not in ones or zeros
    tt_vals = {}
    for inp in ones:
        tt_vals[inp] = '1'
    for inp in zeros:
        tt_vals[inp] = '0'
    # Fill remaining as don't-care
    tt_str = ''.join(tt_vals.get(i, '-') for i in range(2**n_vars))

    # Use pyeda truthtable
    xs = [f'x{i}' for i in range(n_vars)]
    try:
        f = truthtable(xs, tt_str)
        (f_min,) = espresso_tts(f)
        # Count SOP terms by converting to DNF
        terms = list(f_min.satisfy_all())
        # Actually, espresso_tts returns an Expression; count cubes
        dnf = f_min.to_dnf()
        if hasattr(dnf, 'xs'):  # OrOp
            return len(dnf.xs)
        elif hasattr(dnf, 'literals'):  # single AND term
            return 1
        else:  # 0 or 1
            return 0
    except Exception as e:
        # Fallback: count 1-minterms as upper bound
        return len(ones)

def espresso_shared():
    """Run multi-output Espresso on magnitude (shares PI across outputs)."""
    print("\n=== Multi-output Espresso: shared prime implicants ===")
    tt = build_mag_tt()
    from pyeda.inter import truthtable, espresso_tts

    n_vars = 6
    n_out = 8
    xs = [f'x{i}' for i in range(n_vars)]

    # Build per-output truth tables
    tt_strs = []
    for bit in range(7, -1, -1):
        tt_str = ''.join(('1' if (out >> bit) & 1 else '0') for _, out in sorted(tt))
        tt_strs.append(tt_str)

    try:
        funcs = [truthtable(xs, s) for s in tt_strs]
        minimized = espresso_tts(*funcs)

        total_terms = 0
        total_gates = 0
        for o, f_min in enumerate(minimized):
            dnf = f_min.to_dnf()
            if hasattr(dnf, 'xs'):
                n_terms = len(dnf.xs)
            elif str(dnf) in ('0', '1'):
                n_terms = 0
            else:
                n_terms = 1
            total_terms += n_terms
            # Gates: each term needs (literals-1) ANDs, then OR tree
            total_gates += n_terms  # simplified: each term = 1 AND gate
            bit = 7 - o
            print(f"  m{bit}: {n_terms} terms")

        print(f"  Total AND terms: {total_terms}")
        print(f"  Total SOP gates (AND + OR): ~{total_terms + max(0, total_terms - n_out)} gates")
        print(f"  Note: shared PI representation may reduce AND gate count further")

    except Exception as e:
        print(f"  Error: {e}")
        print("  Falling back to per-bit minimization")
        espresso_mag()

def analyze_mag_structure():
    """Analyze the structural constraints of the magnitude function."""
    print("\n=== Magnitude function structural analysis ===")
    tt = build_mag_tt()

    nonzero = [(inp, out) for inp, out in tt if out > 0]
    zero    = [(inp, out) for inp, out in tt if out == 0]
    print(f"  Total input combinations: 64")
    print(f"  Non-zero outputs: {len(nonzero)}")
    print(f"  Zero outputs: {len(zero)}")

    # Count distinct output values
    distinct = sorted(set(out for _, out in tt))
    print(f"  Distinct output values: {len(distinct)}")
    for v in distinct:
        count = sum(1 for _, out in tt if out == v)
        bits_set = bin(v).count('1')
        print(f"    0x{v:02x} ({v:8b}) — {bits_set} bits set — appears {count} times")

    # Symmetry analysis: f(a,b) == f(b,a)?
    seen_nonsymm = 0
    for inp, out in tt:
        a_mag = (inp >> 3) & 7
        b_mag = inp & 7
        inp_swap = (b_mag << 3) | a_mag
        out_swap = dict(tt).get(inp_swap, 0)
        if out != out_swap:
            seen_nonsymm += 1
    print(f"  Symmetric f(a,b)=f(b,a)? {'YES' if seen_nonsymm==0 else f'NO ({seen_nonsymm} violations)'}")

    # Bit independence analysis
    print("\n  Per-bit one-count and Hamming-1 analysis:")
    for bit in range(7, -1, -1):
        ones = [inp for inp, out in tt if (out >> bit) & 1]
        print(f"    m{bit}: {len(ones)} ones")


if __name__ == "__main__":
    analyze_mag_structure()
    espresso_mag()
    espresso_shared()
