"""
Multi-output Espresso for magnitude (6->8) and E-sum+decoder (4->7).

Multi-output Espresso finds a cover where prime implicants can be shared
across multiple outputs -- potentially better than per-bit minimization.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from eval_circuit import FP4_TABLE

_mag_to_code = {0.0:0,1.5:1,3.0:2,6.0:3,0.5:4,1.0:5,2.0:6,4.0:7}
REMAP = [(1 if v < 0 else 0) << 3 | _mag_to_code[abs(v)] for v in FP4_TABLE]


def build_mag_tt():
    seen = {}
    for a in range(16):
        for b in range(16):
            a_mag = REMAP[a] & 7
            b_mag = REMAP[b] & 7
            inp = (a_mag << 3) | b_mag
            seen[inp] = int(round(abs(FP4_TABLE[a]) * abs(FP4_TABLE[b]) * 4))
    return seen


def build_esumdec_tt():
    rows = {}
    for a2 in range(2):
        for a3 in range(2):
            for b2 in range(2):
                for b3 in range(2):
                    s = 2*a2 + a3 + 2*b2 + b3
                    inp = (a2 << 3) | (a3 << 2) | (b2 << 1) | b3
                    rows[inp] = 1 << (6 - s)
    return rows


def run_multi_output_espresso(tt, n_in, n_out, label):
    """
    Run multi-output Espresso using pyeda's espresso_tts with multiple functions.
    This shares prime implicants across outputs.
    """
    from pyeda.inter import espresso_tts, truthtable, exprvar
    print(f"\n=== Multi-output Espresso: {label} ({n_in}-in {n_out}-out) ===")

    xs = [exprvar(f'x{i}') for i in range(n_in)]

    # Build per-output truth table strings
    tt_strs = []
    for bit in range(n_out):
        tt_str = ''.join(
            str((tt[inp] >> bit) & 1) if inp in tt else '-'
            for inp in range(2**n_in)
        )
        tt_strs.append(tt_str)

    try:
        funcs = [truthtable(xs, s) for s in tt_strs]
        minimized = espresso_tts(*funcs)

        total_terms = 0
        for bit, f_min in enumerate(minimized):
            dnf = f_min.to_dnf()
            if hasattr(dnf, 'xs'):
                # OrOp: each element is a term (AND or literal)
                n_terms = len(dnf.xs)
                terms = [str(t) for t in dnf.xs]
            elif str(dnf) in ('0', '1', 'False', 'True'):
                n_terms = 0
                terms = []
            else:
                # Single term (AndOp or literal)
                n_terms = 1
                terms = [str(dnf)]
            total_terms += n_terms
            print(f"  Bit {bit}: {n_terms} terms -> {terms[:3]}{'...' if len(terms)>3 else ''}")

        print(f"  Total terms (shared): {total_terms}")
        print(f"  Estimated gates (AND + OR): ~{total_terms + max(0, total_terms - n_out)}")
        print(f"  Note: multi-output Espresso shares AND terms across bits")

    except Exception as e:
        print(f"  Error: {e}")
        import traceback; traceback.print_exc()


def run_pla_espresso(tt, n_in, n_out, label):
    """
    Write PLA file and call espresso binary if available (via WSL).
    This is the gold standard multi-output Espresso.
    """
    import subprocess, tempfile, os
    print(f"\n=== PLA-based Espresso (via espresso binary): {label} ===")

    # Write PLA file
    pla_lines = [f'.i {n_in}', f'.o {n_out}', f'.p {len(tt)}']
    for inp in sorted(tt):
        ibits = format(inp, f'0{n_in}b')
        obits = format(tt[inp], f'0{n_out}b')
        pla_lines.append(f'{ibits} {obits}')
    pla_lines.append('.e')
    pla_content = '\n'.join(pla_lines)

    # Try to call espresso binary
    pla_path = os.path.join(os.path.dirname(__file__), 'data', f'{label.replace(" ", "_")}.pla')
    os.makedirs(os.path.dirname(pla_path), exist_ok=True)
    with open(pla_path, 'w') as f:
        f.write(pla_content)
    print(f"  Wrote PLA to {pla_path}")

    # Try WSL espresso
    for cmd in ['espresso', 'wsl espresso']:
        try:
            result = subprocess.run(
                f'{cmd} {pla_path}', shell=True, capture_output=True, text=True, timeout=30
            )
            if result.returncode == 0:
                print(f"  espresso output:\n{result.stdout}")
                return
        except Exception:
            pass
    print("  espresso binary not found (need to install via WSL)")


def count_terms_from_pla(pla_output):
    """Count product terms from espresso binary output."""
    lines = [l for l in pla_output.splitlines()
             if l and not l.startswith('.') and not l.startswith('#')]
    return len(lines)


if __name__ == "__main__":
    mag_tt = build_mag_tt()
    esumdec_tt = build_esumdec_tt()

    # Multi-output Espresso via pyeda API
    run_multi_output_espresso(mag_tt, 6, 8, "magnitude")
    run_multi_output_espresso(esumdec_tt, 4, 7, "E-sum+decoder")

    # PLA-based Espresso (needs binary)
    run_pla_espresso(mag_tt, 6, 8, "mag_6in8out")
    run_pla_espresso(esumdec_tt, 4, 7, "esumdec_4in7out")
