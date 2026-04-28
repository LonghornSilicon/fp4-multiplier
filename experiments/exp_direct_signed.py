"""
Direct signed computation: analyze the 8-input 9-output FP4×FP4 function
via Espresso SOP minimization and multi-level algebraic factoring.

The current circuit decomposes into sign-magnitude + conditional negation.
This experiment asks: what if we compute each output bit directly?

Key results:
  - Espresso SOP per-bit gate cost
  - Symmetry and structural analysis
  - Shared terms across output bits
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from pyeda.inter import espresso_tts, truthtable, exprvar
from eval_circuit import FP4_TABLE

_mag_to_code = {0.0:0,1.5:1,3.0:2,6.0:3,0.5:4,1.0:5,2.0:6,4.0:7}
REMAP = [(1 if v < 0 else 0) << 3 | _mag_to_code[abs(v)] for v in FP4_TABLE]

def build_full_signed_tt():
    """All 256 FP4×FP4 pairs -> 9-bit QI9."""
    rows = {}
    for a in range(16):
        for b in range(16):
            a_code = REMAP[a]; b_code = REMAP[b]
            inp = (a_code << 4) | b_code
            qi9 = int(round(FP4_TABLE[a] * FP4_TABLE[b] * 4)) & 0x1FF
            rows[inp] = qi9
    return rows

def qi9_bit(qi9_int, bit_index):
    """Extract bit_index from 9-bit QI9 (bit 0 = MSB = sign)."""
    return (qi9_int >> (8 - bit_index)) & 1

def espresso_per_bit(rows):
    """Run Espresso on each of the 9 output bits independently."""
    print("\n=== Direct signed circuit: per-bit Espresso SOP ===")
    print("(8-in 9-out function, all 256 input combinations)")
    xs = [exprvar(f'x{i}') for i in range(8)]
    total_and = 0
    total_or = 0
    for bit in range(9):
        tt_str = ''.join(str(qi9_bit(rows[inp], bit)) if inp in rows else '-' for inp in range(256))
        f = truthtable(xs, tt_str)
        (f_min,) = espresso_tts(f)
        dnf = f_min.to_dnf()
        if hasattr(dnf, 'xs'):
            n_terms = len(dnf.xs)
        elif str(dnf) in ('0', '1', 'False', 'True'):
            n_terms = 0
        else:
            n_terms = 1
        total_and += n_terms
        total_or += max(0, n_terms - 1)
        print(f"  res{bit}: {n_terms} terms  ({n_terms} AND + {max(0,n_terms-1)} OR = {max(0,2*n_terms-1)} gates)")
    print(f"  Total per-bit naive SOP: {total_and} AND + {total_or} OR = {total_and+total_or} gates")
    print(f"  (compare current circuit: 86 gates, multi-level)")
    return total_and + total_or

def analyze_symmetry(rows):
    """Analyze symmetries in the signed function."""
    print("\n=== Symmetry analysis (8-in 9-out) ===")

    # Sign symmetry: f(NOT(a0), a1..a3, b0..b3) relates to negation
    # f(a, b) should equal -f(-a, b) for sign symmetry
    sign_sym_violations = 0
    for inp in range(256):
        a_code = (inp >> 4) & 0xF
        b_code = inp & 0xF
        a_neg = a_code ^ 0x8  # flip sign bit
        inp_neg = (a_neg << 4) | b_code
        qi9 = rows.get(inp, 0)
        qi9_neg = rows.get(inp_neg, 0)
        # qi9 should be -(qi9_neg) when flipping sign of a
        expected = (-qi9) & 0x1FF
        if qi9_neg != expected:
            sign_sym_violations += 1
    print(f"  Sign antisymmetry violations (negate a): {sign_sym_violations}")

    # Commutativity: f(a, b) = f(b, a)
    comm_violations = 0
    for inp in range(256):
        a_code = (inp >> 4) & 0xF
        b_code = inp & 0xF
        inp_swap = (b_code << 4) | a_code
        if rows.get(inp, 0) != rows.get(inp_swap, 0):
            comm_violations += 1
    print(f"  Commutativity violations (swap a,b): {comm_violations}")

    # Count distinct non-zero outputs
    distinct = sorted(set(v for v in rows.values()))
    nonzero = sorted(set(v for v in rows.values() if v != 0))
    print(f"  Distinct QI9 output values: {len(distinct)} (including 0)")
    print(f"  Distinct non-zero outputs: {len(nonzero)}")
    vals_positive = sorted(set(v for v in nonzero if v < 256))  # positive
    vals_negative = sorted(set(v for v in nonzero if v >= 256))  # negative (2's comp)
    print(f"  Positive outputs: {len(vals_positive)} distinct values")
    print(f"  Negative outputs: {len(vals_negative)} distinct values")

def shared_terms_analysis(rows):
    """Look for shared AND terms across output bits."""
    print("\n=== Shared SOP term analysis ===")
    from pyeda.inter import espresso_tts, truthtable, exprvar
    xs = [exprvar(f'x{i}') for i in range(8)]

    all_cubes = []
    for bit in range(9):
        tt_str = ''.join(str(qi9_bit(rows[inp], bit)) if inp in rows else '-' for inp in range(256))
        f = truthtable(xs, tt_str)
        (f_min,) = espresso_tts(f)
        dnf = f_min.to_dnf()
        if hasattr(dnf, 'xs'):
            cubes = set(str(t) for t in dnf.xs)
        elif str(dnf) not in ('0', '1', 'False', 'True'):
            cubes = {str(dnf)}
        else:
            cubes = set()
        all_cubes.append(cubes)

    # Count sharing
    total_cubes = sum(len(c) for c in all_cubes)
    unique_cubes = set()
    for c in all_cubes:
        unique_cubes |= c
    shared = total_cubes - len(unique_cubes)
    print(f"  Total cube instances across 9 bits: {total_cubes}")
    print(f"  Unique cubes: {len(unique_cubes)}")
    print(f"  Shared cubes (appear in 2+ bits): {shared}")
    print(f"  Potential saving with perfect sharing: {shared} AND gates")

def analyze_output_structure(rows):
    """How many input combinations produce each specific bit pattern?"""
    print("\n=== Output bit pattern distribution ===")
    from collections import Counter
    cnt = Counter(rows.values())
    print(f"  Most common outputs:")
    for v, c in cnt.most_common(10):
        if v == 0:
            sign = 0; mag = 0
        else:
            sign = (v >> 8) & 1
            mag = v & 0xFF
        print(f"    QI9=0x{v:03x} ({'+' if not sign else '-'}{mag*0.25:.2f}): {c} times")


if __name__ == "__main__":
    rows = build_full_signed_tt()
    analyze_symmetry(rows)
    analyze_output_structure(rows)
    espresso_per_bit(rows)
    # shared_terms_analysis(rows)  # slow, run separately
