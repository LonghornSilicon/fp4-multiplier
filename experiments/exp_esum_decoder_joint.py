"""
Investigate joint E-sum + S-decoder optimization.

ABC found 17 ANDs for the 4->7 (a2,a3,b2,b3) -> (sh0..sh6) function.
Our current implementation uses 18 gates (7 E-sum + 11 S-decoder).

If we can translate this to our {AND,OR,XOR,NOT} basis with <= 17 gates,
we save 1 gate from the total circuit.

Run: python3 experiments/exp_esum_decoder_joint.py
"""

import os
import subprocess
import re

ABC_BIN = "/home/tit/abc/abc"
ABC_CWD = "/home/tit/abc"


def run_abc(script, timeout=120):
    """Run ABC and return output."""
    result = subprocess.run(
        [ABC_BIN, "-c", script],
        cwd=ABC_CWD,
        capture_output=True, text=True, timeout=timeout
    )
    return result.stdout + result.stderr


def create_esum_decoder_pla():
    """Create PLA for E-sum + decoder function."""
    pla_path = "/tmp/esum_decoder.pla"
    with open(pla_path, 'w') as f:
        f.write(".i 4\n.o 7\n")
        f.write(".ilb a2 a3 b2 b3\n")
        f.write(".ob sh0 sh1 sh2 sh3 sh4 sh5 sh6\n")
        f.write(".type fr\n")
        for a2 in range(2):
            for a3 in range(2):
                for b2 in range(2):
                    for b3 in range(2):
                        s = (a2*2 + a3) + (b2*2 + b3)  # E-sum in 0..6
                        in_bits = f"{a2}{a3}{b2}{b3}"
                        out_bits = "".join("1" if i == s else "0" for i in range(7))
                        f.write(f"{in_bits} {out_bits}\n")
        f.write(".e\n")
    return pla_path


def dump_and_analyze_circuit():
    """Get the 17-AND circuit from ABC and analyze it."""
    print("=" * 70)
    print("E-SUM + DECODER JOINT OPTIMIZATION ANALYSIS")
    print("=" * 70)

    pla_path = create_esum_decoder_pla()

    # Get the optimized circuit
    script = (
        f"read_pla {pla_path}; strash; "
        "&get; &deepsyn -T 60; &put; "
        "print_stats; write_verilog /tmp/esum_dec.v"
    )
    out = run_abc(script, timeout=90)
    print(out)

    # Read the Verilog
    if os.path.exists("/tmp/esum_dec.v"):
        print("\n" + "-" * 70)
        print("AIG Verilog circuit:")
        with open("/tmp/esum_dec.v") as f:
            content = f.read()
        print(content)

        # Analyze the circuit
        lines = content.split('\n')
        and_ops = [l for l in lines if ' & ' in l]
        not_ops = [l for l in lines if '~' in l]
        or_ops = [l for l in lines if ' | ' in l]

        print("\n" + "-" * 70)
        print("Gate analysis:")
        print(f"  AND operations: {len(and_ops)}")
        print(f"  Lines with NOT: {len(not_ops)}")
        print(f"  OR operations: {len(or_ops)}")

        # Count unique operations
        # In AIG: OR(a,b) = NOT(AND(NOT(a), NOT(b)))
        # So each | is actually equivalent to 1 AND + 2 NOTs, but
        # we have native OR, so | = 1 gate
        #
        # In AIG: XOR(a,b) = OR(AND(a, NOT(b)), AND(NOT(a), b))
        # = 4 ANDs + 2 NOTs in pure AIG
        # But in our basis, XOR = 1 gate

        # The ABC output uses De Morgan, so we need to translate
        return content


def translate_to_our_basis(verilog):
    """
    Attempt to translate AIG Verilog to our {AND, OR, XOR, NOT} basis.

    AIG uses only AND and NOT (inverters on edges).
    Key patterns:
    - a & b = AND(a, b)
    - ~(a & b) = NOT(AND(a, b)) = NAND(a, b)
    - ~a & ~b = AND(NOT(a), NOT(b)) = NOR(a, b) (after De Morgan)
    - (~a & b) | (a & ~b) = XOR(a, b)

    We can often recognize XOR patterns and simplify.
    """
    print("\n" + "=" * 70)
    print("TRANSLATION TO OUR BASIS")
    print("=" * 70)

    # Parse the Verilog assignments
    lines = verilog.split('\n')
    assigns = {}
    for line in lines:
        if 'assign' in line and '=' in line:
            # Parse: assign new_n15 = pi1 & pi4;
            m = re.match(r'\s*assign\s+(\w+)\s*=\s*(.+?);', line)
            if m:
                var = m.group(1)
                expr = m.group(2).strip()
                assigns[var] = expr
                print(f"  {var} = {expr}")

    print("\n" + "-" * 70)
    print("Looking for XOR patterns...")

    # Look for XOR patterns: (a & ~b) | (~a & b)
    # In AIG, this often appears as multiple steps


def analyze_structure_manually():
    """Manually analyze the E-sum + decoder structure."""
    print("\n" + "=" * 70)
    print("MANUAL STRUCTURE ANALYSIS")
    print("=" * 70)

    print("""
    Current implementation (18 gates):
    ----------------------------------
    E-sum (7 gates):
      s0 = XOR(a3, b3)        # bit 0 of sum
      c0 = AND(a3, b3)        # carry from bit 0
      s1x = XOR(a2, b2)       # pre-xor for bit 1
      s1 = XOR(s1x, c0)       # bit 1 of sum
      s2 = OR(AND(a2, b2), AND(s1x, c0))  # bit 2 of sum (carry-out)

    S-decoder (11 gates):
      _or01 = OR(s2, s1)
      _or012 = OR(s0, _or01)
      sh0 = NOT(_or012)
      sh1 = XOR(_or01, _or012)
      _xor2 = XOR(s0, _or012)
      _and2 = AND(s2, _xor2)
      sh3 = AND(s1, s0)
      sh5 = AND(s2, s0)
      sh2 = XOR(_xor2, _and2)
      sh6 = AND(s1, _and2)
      sh4 = XOR(_and2, sh6)

    Total: 18 gates

    Observation: s0, s1, s2 are computed first, then decoded.
    But ABC found 17 ANDs by merging these stages.

    Let's think about what we're computing:
    - S = E'_a + E'_b where E'_a = 2*a2 + a3, E'_b = 2*b2 + b3
    - S ranges 0..6

    sh_i = 1 iff S = i

    Direct computation:
    sh0: S=0 means a2=a3=b2=b3=0
         sh0 = NOR(a2, a3, b2, b3) = NOT(OR(OR(a2,a3), OR(b2,b3))) = 3 gates

    sh1: S=1 means exactly one of {a3, b3} is 1, and a2=b2=0
         sh1 = XOR(a3, b3) AND NOT(a2) AND NOT(b2)
         = AND(AND(XOR(a3,b3), NOT(a2)), NOT(b2))
         = 4 gates (XOR + 2 NOT + 2 AND)
         But we can share NOT(a2), NOT(b2), XOR(a3,b3) across outputs

    sh2: S=2 means...
         (a2=1, a3=0, b2=0, b3=0) OR (a2=0, a3=1, b2=0, b3=1) OR
         (a2=0, a3=0, b2=1, b3=0) OR (a2=0, a3=0, b2=0, b3=0) wait no...

    Actually: S=2 when (a2*2+a3) + (b2*2+b3) = 2
    Cases: (0,0)+(1,0), (0,1)+(0,1), (1,0)+(0,0), (0,2)+(0,0) - wait, a3,b3 are bits

    Let me enumerate:
    (a2,a3) + (b2,b3) = 2
    00 + 10 = 2 ✓
    01 + 01 = 2 ✓
    10 + 00 = 2 ✓

    sh2 = (a2=0 AND a3=0 AND b2=1 AND b3=0) OR
          (a2=0 AND a3=1 AND b2=0 AND b3=1) OR
          (a2=1 AND a3=0 AND b2=0 AND b3=0)
    This is 3 product terms, each 4 literals = messy

    The current approach (E-sum + decoder) is elegant because:
    - E-sum computes the 3-bit sum efficiently
    - Decoder converts 3 bits to 7 outputs efficiently

    Can we find alternative structure?
    """)

    # Alternative idea: compute sh_i directly from (a2,a3,b2,b3)
    # without intermediate E-sum

    print("\n--- Direct sh_i computation ---")
    for s in range(7):
        minterms = []
        for a2 in range(2):
            for a3 in range(2):
                for b2 in range(2):
                    for b3 in range(2):
                        if (a2*2 + a3) + (b2*2 + b3) == s:
                            minterms.append((a2, a3, b2, b3))
        print(f"  sh{s}: {len(minterms)} minterms: {minterms}")


def test_alternative_structures():
    """Test alternative circuit structures using ABC."""
    print("\n" + "=" * 70)
    print("ALTERNATIVE CIRCUIT STRUCTURES")
    print("=" * 70)

    # Idea 1: Use XAIG (allows XOR natively)
    # ABC's XAIG includes XOR/XNOR as native gates

    pla_path = create_esum_decoder_pla()

    # Test with extra XOR-aware optimization
    sequences = [
        ("baseline AIG", "strash; print_stats"),
        ("deepsyn", "strash; &get; &deepsyn -T 30; &put; print_stats"),
        ("xaig-dch", "strash; &get; &dch -x; &nf; &put; print_stats"),
        ("dc2", "strash; dc2; dc2; dc2; print_stats"),
        ("collapse", "collapse; strash; dc2; print_stats"),
    ]

    for label, seq in sequences:
        script = f"read_pla {pla_path}; {seq}"
        try:
            out = run_abc(script, timeout=60)
            m = re.search(r"and\s*=\s*(\d+)", out)
            if m:
                print(f"  {label:20s}: {m.group(1)} ANDs")
        except Exception as e:
            print(f"  {label:20s}: failed ({e})")


def verify_current_implementation():
    """Verify the current implementation gate count."""
    print("\n" + "=" * 70)
    print("CURRENT IMPLEMENTATION VERIFICATION")
    print("=" * 70)

    # E-sum (7 gates)
    print("E-sum:")
    print("  1. s0 = XOR(a3, b3)")
    print("  2. c0 = AND(a3, b3)")
    print("  3. s1x = XOR(a2, b2)")
    print("  4. s1 = XOR(s1x, c0)")
    print("  5. _t1 = AND(a2, b2)")
    print("  6. _t2 = AND(s1x, c0)")
    print("  7. s2 = OR(_t1, _t2)")
    print("  Total: 7 gates")

    # S-decoder (11 gates)
    print("\nS-decoder:")
    print("  8.  _or01 = OR(s2, s1)")
    print("  9.  _or012 = OR(s0, _or01)")
    print("  10. sh0 = NOT(_or012)")
    print("  11. sh1 = XOR(_or01, _or012)")
    print("  12. _xor2 = XOR(s0, _or012)")
    print("  13. _and2 = AND(s2, _xor2)")
    print("  14. sh3 = AND(s1, s0)")
    print("  15. sh5 = AND(s2, s0)")
    print("  16. sh2 = XOR(_xor2, _and2)")
    print("  17. sh6 = AND(s1, _and2)")
    print("  18. sh4 = XOR(_and2, sh6)")
    print("  Total: 11 gates")

    print("\n  GRAND TOTAL: 18 gates")

    # Now let's think about what ABC's 17-AND circuit implies
    print("\n" + "-" * 70)
    print("ABC's 17-AND AIG interpretation:")
    print("""
    ABC found a 17-AND AIG. In AIG:
    - AND = 1 gate
    - OR(a,b) = NOT(AND(NOT(a), NOT(b))) - but this is 1 AND + inverters
      In AIG, inverters are "free" (edge annotations), so OR = 1 AND

    So 17 AIG ANDs could mean:
    - If all gates are AND/OR: 17 gates in our basis (matching ABC)
    - If some require XOR: fewer gates (since XOR = 1 in our basis but 4 ANDs in AIG)

    But wait - ABC's AIG includes OR via De Morgan at zero cost.
    So 17 AIG ANDs = 17 {AND, OR} gates in our basis.

    If we can identify XOR patterns in the AIG and replace them:
    - Each XOR pattern in AIG = 4 ANDs
    - Replacing with native XOR saves 3 gates per XOR

    Let's count XORs needed:
    - E-sum uses 3 XOR (s0, s1x, s1)
    - Decoder uses 4 XOR (sh1, _xor2, sh2, sh4)
    - Total: 7 XORs = 28 AIG ANDs if done via AIG

    But current implementation = 18 gates
    If ABC found 17 ANDs WITHOUT using XOR optimization, that's impressive.

    More likely: ABC's 17-AND circuit has some NOTs that we're not counting.
    In our basis, NOT costs 1 gate.

    Let me check the Verilog more carefully...
    """)


def count_gates_from_verilog():
    """Count actual gates in our basis from ABC's Verilog output."""
    print("\n" + "=" * 70)
    print("VERILOG GATE COUNT ANALYSIS")
    print("=" * 70)

    # From the previous run, the Verilog was (let me re-run to capture it)
    pla_path = create_esum_decoder_pla()
    script = (
        f"read_pla {pla_path}; strash; "
        "&get; &deepsyn -T 60; &put; "
        "write_verilog /tmp/esum_dec.v"
    )
    out = run_abc(script, timeout=90)

    with open("/tmp/esum_dec.v") as f:
        content = f.read()

    # Parse all assignments
    assignments = []
    for line in content.split('\n'):
        if 'assign' in line and '=' in line:
            m = re.match(r'\s*assign\s+(\w+)\s*=\s*(.+?);', line)
            if m:
                var = m.group(1)
                expr = m.group(2).strip()
                assignments.append((var, expr))

    print(f"Total assignments: {len(assignments)}")

    # Count gate types
    and_count = 0
    or_count = 0
    not_count = 0

    for var, expr in assignments:
        if ' & ' in expr:
            and_count += 1
        if ' | ' in expr:
            or_count += 1
        if '~' in expr:
            # Count number of ~ in expression (NOT operations)
            # But some might be on inputs which are inverted edges
            pass

    # Actually, let's just print all assignments and count manually
    print("\nAll assignments:")
    for var, expr in assignments:
        print(f"  {var} = {expr}")

    # In AIG Verilog:
    # - Each 'assign x = a & b' is one AND
    # - Each 'assign x = a | b' is one OR (De Morgan form in AIG)
    # - Inverters (~) on wires are free in AIG but cost 1 gate in our basis

    # Let's count properly:
    # - Number of assignments = number of intermediate + output nodes
    # - But some are just wiring (no actual gate)

    total_gates = len(assignments) - 8  # Subtract 8 outputs (just wiring)
    print(f"\nIntermediate gates: {total_gates}")

    # Check for NOT that would need explicit gates
    # In our basis, NOT is explicit. In AIG, it's edge annotation.
    # If we see ~x where x is a computed value, we might need NOT gate.

    print("""
    Key insight:
    In AIG, ~x (inverted x) is free because it's an edge annotation.
    In our basis {AND, OR, XOR, NOT}:
    - ~x requires 1 NOT gate
    - BUT: if x is only used in inverted form, we might be able to
      restructure to avoid the NOT (e.g., use NAND instead of AND then NOT)

    In practice, ABC's 17 ANDs + free inverters likely translates to
    17-20 gates in our basis, depending on NOT placement.

    Our current 18 gates remains competitive.
    """)


def main():
    dump_and_analyze_circuit()
    analyze_structure_manually()
    test_alternative_structures()
    verify_current_implementation()
    count_gates_from_verilog()

    print("\n" + "=" * 70)
    print("CONCLUSIONS")
    print("=" * 70)
    print("""
    1. ABC found 17 AIG ANDs for the E-sum + decoder (4->7) function.

    2. In AIG, inverters are free (edge annotations). Translating to our
       {AND, OR, XOR, NOT} basis likely requires 17-20 gates.

    3. Our current implementation uses 18 gates and exploits XOR efficiently.

    4. The 17-AIG result suggests there MAY be a 17-gate implementation in
       our basis, but:
       - ABC's AIG doesn't use XOR natively
       - Extracting the actual circuit and translating is non-trivial
       - The gain would be only 1 gate

    5. For the ROM decomposition question:
       ROM-style (flat truth table) CANNOT beat the algebraic decomposition.
       ABC's best for the full 6->8 magnitude is 64 ANDs, which translates
       to ~70-80 gates in our basis - far worse than our 54-gate algebraic
       approach.

    6. The current K-type x shift architecture is near-optimal.
       Improvements must come from:
       - Cross-stage optimization (E-sum + decoder fusion)
       - Different negation strategy
       - Fundamentally different topology
    """)


if __name__ == "__main__":
    main()
