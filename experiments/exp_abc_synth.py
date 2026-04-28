"""
Track D: ABC logic synthesis tool.

Generates PLA truth table files and runs them through ABC (Berkeley Logic Synthesis)
to find multi-level minimized gate counts.

ABC uses resyn2 (iterative rewriting) which is state-of-the-art for multi-level
technology-independent synthesis.

Requirements:
  - ABC binary in PATH or specified via ABC_PATH env var
  - OR: pip install pyabc-trig (Python ABC bindings, if available)

Fallback: if ABC not available, uses ESPRESSO via pyeda.
"""

import sys
import os
import subprocess
import tempfile
import json
import shutil

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fp4_core import build_truth_table, tt_to_bit_functions, MAGNITUDES


FP4_TABLE = [0.0, 0.5, 1.0, 1.5, 2.0, 3.0, 4.0, 6.0,
             0.0, -0.5, -1.0, -1.5, -2.0, -3.0, -4.0, -6.0]


# ── PLA file generation ───────────────────────────────────────────────────────

def build_pla(mag_perm, output_file, n_inputs=8, outputs_to_include=None):
    """
    Generate a PLA (Programmable Logic Array) file for ABC.

    For 8-input (a0..a3, b0..b3) → 9-output (res0..res8) circuit.
    """
    from fp4_core import build_truth_table, tt_to_bit_functions

    # Build full remap
    remap = {}
    for orig_idx in range(16):
        val = FP4_TABLE[orig_idx]
        sign = 1 if val < 0 else 0
        mag_idx = MAGNITUDES.index(abs(val))
        new_code = (sign << 3) | mag_perm[mag_idx]
        remap[orig_idx] = new_code

    # Build 9-output truth table
    tt = build_truth_table(mag_perm)
    funcs = tt_to_bit_functions(tt)

    if outputs_to_include is None:
        outputs_to_include = list(range(9))

    n_outputs = len(outputs_to_include)

    with open(output_file, 'w') as f:
        f.write(f".i {n_inputs}\n")
        f.write(f".o {n_outputs}\n")
        f.write(f".ilb " + " ".join(f"a{i}" if i < 4 else f"b{i-4}" for i in range(n_inputs)) + "\n")
        f.write(f".ob " + " ".join(f"res{i}" for i in outputs_to_include) + "\n")
        f.write(".type fr\n")

        for idx in range(256):
            # Input: a0..a3 b0..b3
            input_bits = ''.join(str((idx >> (7 - i)) & 1) for i in range(8))
            # Output: selected result bits
            output_bits = ''.join(str(funcs[i][idx]) for i in outputs_to_include)
            f.write(f"{input_bits} {output_bits}\n")

        f.write(".e\n")


def build_pla_magnitude(mag_perm, output_file, n_inputs=6):
    """Generate PLA for magnitude-only circuit (6 inputs → 8 outputs)."""
    from fp4_synth_real import build_magnitude_tt, mag_tt_to_funcs

    mag_tt = build_magnitude_tt(mag_perm)
    funcs = mag_tt_to_funcs(mag_tt)

    with open(output_file, 'w') as f:
        f.write(f".i {n_inputs}\n")
        f.write(f".o 8\n")
        f.write(f".ilb a1 a2 a3 b1 b2 b3\n")
        f.write(f".ob m7 m6 m5 m4 m3 m2 m1 m0\n")
        f.write(".type fr\n")

        for idx in range(64):
            input_bits = ''.join(str((idx >> (5 - i)) & 1) for i in range(6))
            output_bits = ''.join(str(funcs[i][idx]) for i in range(8))
            f.write(f"{input_bits} {output_bits}\n")

        f.write(".e\n")


# ── ABC runner ────────────────────────────────────────────────────────────────

def find_abc():
    """Try to find the ABC binary."""
    # Check env var
    if 'ABC_PATH' in os.environ:
        return os.environ['ABC_PATH']
    # Check common locations
    for name in ['abc', 'abc.exe', 'abc64', 'yosys-abc']:
        path = shutil.which(name)
        if path:
            return path
    return None


def run_abc(pla_file, abc_binary=None, script='resyn2'):
    """
    Run ABC on a PLA file with the given synthesis script.
    Returns (gate_count, and_count, or_count, not_count) or None on failure.
    """
    if abc_binary is None:
        abc_binary = find_abc()
    if abc_binary is None:
        return None

    # ABC script: read PLA, optimize, count gates
    abc_script = f"""read_pla {pla_file}; strash; {script}; strash; print_stats;"""

    try:
        result = subprocess.run(
            [abc_binary, '-c', abc_script],
            capture_output=True, text=True, timeout=60
        )
        output = result.stdout + result.stderr

        # Parse gate count from print_stats output
        # Format: "nd =  42  lat =   0  invs =   8  levs = 5"
        import re
        nd_match = re.search(r'nd\s*=\s*(\d+)', output)
        inv_match = re.search(r'invs\s*=\s*(\d+)', output)
        if nd_match:
            nd = int(nd_match.group(1))
            inv = int(inv_match.group(1)) if inv_match else 0
            return {'and_nodes': nd, 'inverters': inv, 'total': nd + inv, 'raw': output}
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        pass
    return None


def run_abc_map_to_gates(pla_file, abc_binary=None):
    """
    Run ABC with full gate mapping to AND/OR/XOR/NOT cells and count.
    Uses the standard cell library mapping.
    """
    if abc_binary is None:
        abc_binary = find_abc()
    if abc_binary is None:
        return None

    # Map to a library with AND2, OR2, XOR2, NOT gates (all cost 1)
    abc_script = f"""
read_pla {pla_file};
strash;
resyn2;
resyn2;
resyn2;
&get;
&if -K 2 -C 8;
&put;
print_stats;
"""
    try:
        result = subprocess.run(
            [abc_binary, '-c', abc_script.replace('\n', ' ')],
            capture_output=True, text=True, timeout=120
        )
        output = result.stdout + result.stderr
        import re
        nd_match = re.search(r'nd\s*=\s*(\d+)', output)
        inv_match = re.search(r'invs\s*=\s*(\d+)', output)
        if nd_match:
            nd = int(nd_match.group(1))
            inv = int(inv_match.group(1)) if inv_match else 0
            return {'and_nodes': nd, 'inverters': inv, 'total': nd + inv, 'raw': output}
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        pass
    return None


# ── ESPRESSO fallback (via pyeda) ─────────────────────────────────────────────

def run_espresso_fallback(mag_perm, n_vars=6):
    """
    Use pyeda's ESPRESSO minimization as ABC fallback.
    Returns per-bit costs after ESPRESSO minimization.
    """
    try:
        from pyeda.inter import espresso_tts, truthtable
    except ImportError:
        print("pyeda not available. Install with: pip install pyeda")
        return None

    from fp4_synth_real import build_magnitude_tt, mag_tt_to_funcs

    mag_tt = build_magnitude_tt(mag_perm)
    funcs = mag_tt_to_funcs(mag_tt)

    total_cost = 0
    per_bit = []

    for bit_idx, f in enumerate(funcs):
        # Create truth table for pyeda
        tt_val = ''.join(str(v) for v in f)

        try:
            # This uses ESPRESSO for exact 2-level minimization
            # (better than Quine-McCluskey greedy cover)
            tt_obj = truthtable(
                [f'a{i}' for i in range(n_vars)],
                tt_val
            )
            # ESPRESSO minimize
            minimized, = espresso_tts(tt_obj)
            # Count gates in minimized form
            from pyeda.inter import exprvar, Not, And, Or
            terms = list(minimized.to_dnf().args) if hasattr(minimized, 'to_dnf') else [minimized]
            cost = len(terms) - 1  # OR gates
            for term in terms:
                lits = list(term.args) if hasattr(term, 'args') else [term]
                cost += len(lits) - 1  # AND gates per term
                cost += sum(1 for l in lits if hasattr(l, 'args'))  # NOT gates
            per_bit.append(cost)
            total_cost += cost
        except Exception as e:
            per_bit.append(None)

    return total_cost, per_bit


# ── Search over remappings with ABC/ESPRESSO ──────────────────────────────────

def search_with_abc(top_perms=20, abc_binary=None):
    """
    Run ABC on the top remappings found by QM search.
    """
    import itertools
    from fp4_synth_real import synthesize_with_remap

    if abc_binary is None:
        abc_binary = find_abc()

    if abc_binary is None:
        print("ABC not found. To install:")
        print("  Ubuntu/Debian: sudo apt-get install abc")
        print("  Or download from: https://github.com/berkeley-abc/abc")
        print("  Or: pip install pyabc-trig")
        return None

    print(f"Using ABC at: {abc_binary}")

    # Quick QM search to find top remappings
    print("Running QM search to find top remappings...")
    qm_results = []
    best_qm = float('inf')
    for i, perm in enumerate(itertools.permutations(range(8))):
        total, _, _ = synthesize_with_remap(perm)
        qm_results.append((total, perm))
        if total < best_qm:
            best_qm = total
    qm_results.sort()

    print(f"Top {top_perms} remappings (QM):")
    for total, perm in qm_results[:top_perms]:
        print(f"  {total} gates: perm={list(perm)}")

    # Run ABC on top permutations
    abc_results = []
    with tempfile.TemporaryDirectory() as tmpdir:
        for rank, (qm_total, perm) in enumerate(qm_results[:top_perms]):
            pla_9bit = os.path.join(tmpdir, f"mult_{rank}_9bit.pla")
            pla_6bit = os.path.join(tmpdir, f"mult_{rank}_6bit.pla")

            build_pla(perm, pla_9bit)
            build_pla_magnitude(perm, pla_6bit)

            # Run ABC
            result_9 = run_abc(pla_9bit, abc_binary)
            result_6 = run_abc(pla_6bit, abc_binary)

            abc_9 = result_9['total'] if result_9 else None
            abc_6 = result_6['total'] if result_6 else None

            # For 2-stage: ABC mag count + 1 (sign) + 23 (cond neg)
            abc_2stage = (abc_6 + 1 + 23) if abc_6 is not None else None

            print(f"  perm={list(perm)}: QM={qm_total}, "
                  f"ABC(9bit)={abc_9}, ABC(6bit+overhead)={abc_2stage}")

            abc_results.append({
                "perm": list(perm),
                "qm_total": qm_total,
                "abc_9bit": abc_9,
                "abc_6bit": abc_6,
                "abc_2stage": abc_2stage,
                "best_abc": min(v for v in [abc_9, abc_2stage] if v is not None) if any(v is not None for v in [abc_9, abc_2stage]) else None,
            })

    abc_results.sort(key=lambda x: x['best_abc'] or 9999)
    return abc_results


# ── Main ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 70)
    print("Track D: ABC Logic Synthesis")
    print("=" * 70)

    abc = find_abc()
    if abc:
        print(f"\nFound ABC at: {abc}")
        results = search_with_abc(top_perms=20, abc_binary=abc)
        if results:
            print("\n=== ABC Results Summary ===")
            for r in results[:10]:
                print(f"  perm={r['perm']}: best={r['best_abc']} gates "
                      f"(9bit={r['abc_9bit']}, 2stage={r['abc_2stage']})")
    else:
        print("\nABC not found. Trying ESPRESSO via pyeda...")
        import itertools
        from fp4_synth_real import synthesize_with_remap

        # Quick test on default perm
        perm = tuple(range(8))
        result = run_espresso_fallback(perm)
        if result:
            total, per_bit = result
            print(f"ESPRESSO (default perm, 6-input): {total} mag gates "
                  f"→ total ~ {total + 1 + 23}")
        else:
            print("ESPRESSO also not available.")
            print("\nFalling back to generating PLA files for manual ABC usage.")
            # Generate PLA files anyway so user can run ABC manually
            out_dir = os.path.join(os.path.dirname(__file__), "..", "autoresearch", "data", "pla_files")
            os.makedirs(out_dir, exist_ok=True)

            for perm_name, perm in [("default", tuple(range(8))),
                                     ("reversed", tuple(range(7, -1, -1)))]:
                pla_9 = os.path.join(out_dir, f"mult_{perm_name}_9bit.pla")
                pla_6 = os.path.join(out_dir, f"mult_{perm_name}_6bit.pla")
                build_pla(perm, pla_9)
                build_pla_magnitude(perm, pla_6)
                print(f"Generated: {pla_9}")
                print(f"Generated: {pla_6}")

            print("\nTo use ABC manually:")
            print("  abc -c 'read_pla mult_default_9bit.pla; strash; resyn2; print_stats;'")

    # Save whatever we have
    out_path = os.path.join(os.path.dirname(__file__), "..", "autoresearch", "data",
                            "track_d_results.json")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    out = {"abc_available": abc is not None, "abc_path": abc}
    with open(out_path, 'w') as f:
        json.dump(out, f, indent=2)
    print(f"\nSaved status to {out_path}")
