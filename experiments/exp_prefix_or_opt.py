"""
Verify the prefix_or_7 = nz optimization.

Claim: For all achievable FP4 products, prefix_or_7 = OR(m0..m6) = nz.
Proof: all 18 non-zero magnitudes have at least one bit in m0..m6
       (magnitude=144 sets both m7 and m4, so OR(m0..m6) >= m4 = 1).

If true, we can replace sp7 = AND(sign, p7) with res0 = AND(sign, nz),
saving p7 (1 OR gate) + sp7 (1 AND gate) = 2 gates.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from eval_circuit import FP4_TABLE

_mag_to_code = {0.0:0,1.5:1,3.0:2,6.0:3,0.5:4,1.0:5,2.0:6,4.0:7}
REMAP = [(1 if v < 0 else 0) << 3 | _mag_to_code[abs(v)] for v in FP4_TABLE]


def verify_p7_equals_nz():
    """Check for all 256 products: does OR(m0..m6) == nz?"""
    violations = 0
    magnitudes_checked = {}

    for a in range(16):
        for b in range(16):
            a_code = REMAP[a]; b_code = REMAP[b]
            # Compute QI9
            qi9 = int(round(FP4_TABLE[a] * FP4_TABLE[b] * 4)) & 0x1FF
            sign_bit = (qi9 >> 8) & 1
            magnitude = qi9 & 0xFF

            # nz = 1 iff product is nonzero
            nz = 1 if (FP4_TABLE[a] * FP4_TABLE[b] != 0) else 0

            # OR(m0..m6) = (magnitude & 0x7F) != 0, i.e., any of bits 0..6 are set
            prefix_or_7 = 1 if (magnitude & 0x7F) != 0 else 0

            if prefix_or_7 != nz:
                violations += 1
                print(f"  VIOLATION: a={FP4_TABLE[a]}, b={FP4_TABLE[b]}, "
                      f"magnitude={magnitude:#010b} ({magnitude}), "
                      f"prefix_or_7={prefix_or_7}, nz={nz}")

    print(f"Checked 256 products: {violations} violations of prefix_or_7 == nz")

    if violations == 0:
        print("OPTIMIZATION VALID: p7 = OR(p6, m6) can be replaced by nz")
        print("  -> sp7 = AND(sign, p7) = AND(sign, nz) = res0 (already computed!)")
        print("  -> Saves 2 gates: p7 (1 OR) + sp7 (1 AND)")
        print("  -> New gate count: 86 - 2 = 84")


def verify_p6_equals_nz():
    """Check if OR(m0..m5) == nz (analogous claim for p6)."""
    violations = 0
    for a in range(16):
        for b in range(16):
            qi9 = int(round(FP4_TABLE[a] * FP4_TABLE[b] * 4)) & 0x1FF
            magnitude = qi9 & 0xFF
            nz = 1 if (FP4_TABLE[a] * FP4_TABLE[b] != 0) else 0
            prefix_or_6 = 1 if (magnitude & 0x3F) != 0 else 0
            if prefix_or_6 != nz:
                violations += 1
                print(f"  p6 violation: a={FP4_TABLE[a]:.1f}, b={FP4_TABLE[b]:.1f}, "
                      f"mag={magnitude} ({magnitude:08b})")

    print(f"p6==nz: {violations} violations {'(CANNOT use p6=nz)' if violations else '(valid!)'}")


def check_all_prefix_ors():
    """Check which prefix_or_i values equal nz."""
    for threshold_bit in range(8):
        mask = (1 << threshold_bit) - 1  # bits 0..threshold_bit-1
        violations = 0
        for a in range(16):
            for b in range(16):
                qi9 = int(round(FP4_TABLE[a] * FP4_TABLE[b] * 4)) & 0x1FF
                magnitude = qi9 & 0xFF
                nz = 1 if (FP4_TABLE[a] * FP4_TABLE[b] != 0) else 0
                prefix_or_i = 1 if (magnitude & mask) != 0 else 0
                if prefix_or_i != nz:
                    violations += 1
        status = "= nz (VALID!)" if violations == 0 else f"!= nz ({violations} violations)"
        print(f"  prefix_or_{threshold_bit} = OR(m0..m{threshold_bit-1}) {status}")


if __name__ == "__main__":
    print("=== Checking prefix_or optimizations ===\n")
    print("Which prefix_or_i = nz?")
    check_all_prefix_ors()
    print()
    verify_p7_equals_nz()
    print()
    verify_p6_equals_nz()
