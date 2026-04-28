"""
Generate a working Python multiplier circuit from QM synthesis.

Strategy:
1. Search all 8! remappings with perm[0]=0 (zero magnitude → code 000)
   This gives auto-zero: magnitude truth table outputs 0 for (000,anything)
2. Find best remapping by actual gate count estimation
3. Generate Python code for the actual circuit
4. Verify with eval_circuit

The 2-stage approach:
  - sign = XOR(a0, b0) : 1 gate
  - zero detect (auto from truth table, only sign needs masking): 5+1 = 6 gates
  - magnitude circuit (6 inputs → 8 outputs, QM-synthesized): N gates
  - conditional negation (8-bit carry chain): 23 gates
  Total: 30 + N gates
"""
import sys, os, itertools, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fp4_core import MAGNITUDES, FP4_VALUES
from fp4_synth_real import (build_magnitude_tt, mag_tt_to_funcs, qm_exact,
                             greedy_cover, sop_gate_cost_6input,
                             conditional_negation_cost)
from eval_circuit import evaluate_fast, FP4_TABLE, GateCounter


# ── Build remap list from magnitude permutation ──────────────────────────────

def make_remap_from_perm(mag_perm):
    """Build 16-int remap list from magnitude permutation."""
    remap = [0] * 16
    for orig_idx in range(16):
        val = FP4_VALUES[orig_idx]
        sign = 1 if val < 0 else 0
        mag_idx = MAGNITUDES.index(abs(val))
        new_code = (sign << 3) | mag_perm[mag_idx]
        remap[orig_idx] = new_code
    return remap


# ── QM synthesis with auto-zero property ─────────────────────────────────────

def synthesize_perm_zero000(mag_perm, n_vars=6):
    """
    Synthesize magnitude circuit for a permutation with perm[0]=0.
    Returns (total_gates, per_bit_costs, per_bit_covers).
    """
    assert mag_perm[0] == 0, "perm[0] must be 0 for zero=000"

    mag_tt = build_magnitude_tt(mag_perm)
    funcs = mag_tt_to_funcs(mag_tt)

    total = 0
    per_bit = []

    for bit_idx, f in enumerate(funcs):
        ones = {i for i, v in enumerate(f) if v == 1}
        zeros = {i for i, v in enumerate(f) if v == 0}

        if not ones:
            per_bit.append((bit_idx, 0, [], False))
            continue
        if not zeros:
            per_bit.append((bit_idx, 0, [], False))
            continue

        pi_sop = qm_exact(ones, n_vars=n_vars)
        cov_sop = greedy_cover(ones, pi_sop, n_vars=n_vars)
        cost_sop = sop_gate_cost_6input(cov_sop, n_vars=n_vars)

        pi_pos = qm_exact(zeros, n_vars=n_vars)
        cov_pos = greedy_cover(zeros, pi_pos, n_vars=n_vars)
        cost_pos = sop_gate_cost_6input(cov_pos, n_vars=n_vars) + 1

        if cost_sop <= cost_pos:
            per_bit.append((bit_idx, cost_sop, cov_sop, False))
            total += cost_sop
        else:
            per_bit.append((bit_idx, cost_pos, cov_pos, True))
            total += cost_pos

    return total, per_bit


def search_zero000_remappings(verbose=True):
    """Search all perms with perm[0]=0 (7!=5040 perms)."""
    results = []
    best = float('inf')
    # perm[0]=0 means MAGNITUDES[0]=0 gets code 0. Fix position 0, permute 1..7 among codes 1..7.
    for i, rest in enumerate(itertools.permutations(range(1, 8))):
        perm = (0,) + rest
        mag_gates, _ = synthesize_perm_zero000(perm)[:2], None
        mag_gates = synthesize_perm_zero000(perm)[0]
        total = 1 + mag_gates + conditional_negation_cost(8) + 6  # sign + mag + cond_neg + zero_overhead
        results.append((total, mag_gates, perm))
        if total < best:
            best = total
            if verbose:
                print(f"[{i:4d}/5040] New best: total={total} mag={mag_gates} perm={list(perm)}")
        elif verbose and i % 1000 == 0:
            print(f"[{i:4d}/5040] best so far: {best}")
    results.sort()
    return results


# ── Circuit code generation ───────────────────────────────────────────────────

def generate_multiplier_code(mag_perm, per_bit_data, var_names=None):
    """
    Generate Python code for write_your_multiplier_here.
    Produces a 2-stage circuit: sign + QM magnitude + cond_neg + zero mask.
    """
    if var_names is None:
        var_names = ['a1', 'a2', 'a3', 'b1', 'b2', 'b3']

    lines = []
    lines.append("def write_your_multiplier_here(a0, a1, a2, a3, b0, b1, b2, b3,")
    lines.append("                                NOT=None, AND=None, OR=None, XOR=None):")
    lines.append("    if NOT is None:")
    lines.append("        NOT=lambda x: not x; AND=lambda x,y: x&y; OR=lambda x,y: x|y; XOR=lambda x,y: x^y")
    lines.append(f"    # Remapping: perm={list(mag_perm)}")
    lines.append("    # Stage 1: sign")
    lines.append("    sign = XOR(a0, b0)")
    lines.append("    # Stage 2: zero detection (perm[0]=0, so (000,xxx) auto-outputs 0)")
    lines.append("    nza = OR(a1, OR(a2, a3))")
    lines.append("    nzb = OR(b1, OR(b2, b3))")
    lines.append("    nz  = AND(nza, nzb)   # not_zero")
    lines.append("    # Stage 3: magnitude circuit (6 inputs: a1 a2 a3 b1 b2 b3)")

    mag_bit_vars = []
    for bit_idx, cost, cover, is_pos in per_bit_data:
        out_name = f"m{7 - bit_idx}"
        mag_bit_vars.append(out_name)

        if not cover:
            if cost == 0:
                # Determine if it's constant 0 or 1
                mag_tt = build_magnitude_tt(mag_perm)
                funcs = mag_tt_to_funcs(mag_tt)
                ones = sum(funcs[bit_idx])
                lines.append(f"    {out_name} = {'True' if ones > 0 else 'False'}")
            else:
                lines.append(f"    {out_name} = False  # constant")
            continue

        terms = []
        for mask, val in cover:
            lits = []
            for bit in range(6):
                if (mask >> bit) & 1:
                    v = var_names[bit]
                    if not (val >> bit) & 1:
                        v = f"NOT({v})"
                    lits.append(v)
            if not lits:
                terms.append("True")
            elif len(lits) == 1:
                terms.append(lits[0])
            else:
                # Build nested AND
                expr = lits[0]
                for l in lits[1:]:
                    expr = f"AND({expr}, {l})"
                terms.append(expr)

        if not terms:
            expr = "False"
        elif len(terms) == 1:
            expr = terms[0]
        else:
            expr = terms[0]
            for t in terms[1:]:
                expr = f"OR({expr}, {t})"

        if is_pos:
            expr = f"NOT({expr})"
        lines.append(f"    {out_name} = {expr}")

    lines.append("    # Stage 4: conditional two's complement negation")
    lines.append("    # t_i = XOR(m_i, sign); r_i = XOR(t_i, carry); c_next = AND(t_i, carry); c0 = sign")
    bit_vars = list(reversed(mag_bit_vars))  # m0..m7 (LSB to MSB)
    carry = "sign"
    r_vars = []
    for i, mv in enumerate(bit_vars):
        t = f"t{i}"
        r = f"r{i}"
        lines.append(f"    {t} = XOR({mv}, sign)")
        lines.append(f"    {r} = XOR({t}, {carry})")
        if i < len(bit_vars) - 1:
            new_carry = f"c{i+1}"
            lines.append(f"    {new_carry} = AND({t}, {carry})")
            carry = new_carry
        r_vars.append(r)

    lines.append("    # Stage 5: zero masking (sign bit only; mag bits auto-zero)")
    lines.append("    res0 = AND(sign, nz)")
    # res1..res8: mag auto-outputs 0 for zero inputs, cond_neg preserves 0
    for i, rv in enumerate(r_vars):
        lines.append(f"    res{i+1} = {rv}")

    r_out = ", ".join(f"res{i}" for i in range(9))
    lines.append(f"    return {r_out}")

    return "\n".join(lines)


# ── Actual circuit execution for gate counting ────────────────────────────────

def build_multiplier_fn(mag_perm, per_bit_data, n_vars=6):
    """Build an actual Python function from QM synthesis results."""
    code = generate_multiplier_code(mag_perm, per_bit_data)
    namespace = {}
    exec(code, namespace)
    return namespace['write_your_multiplier_here']


# ── Main ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 70)
    print("QM synthesis with zero=000 constraint")
    print("=" * 70)

    print("\nSearching 7! = 5040 permutations with perm[0]=0...")
    results = search_zero000_remappings(verbose=True)

    print(f"\nTop 10:")
    for total, mag, perm in results[:10]:
        print(f"  total~{total:3d} (mag={mag:3d}), perm={list(perm)}")

    best_perm = results[0][2]
    est_total = results[0][0]

    print(f"\nBest perm: {list(best_perm)}, estimated total: {est_total}")

    # Generate actual circuit
    _, per_bit_data = synthesize_perm_zero000(best_perm)

    print("\nGenerating circuit code...")
    code = generate_multiplier_code(best_perm, per_bit_data)

    # Build and test the function
    fn = build_multiplier_fn(best_perm, per_bit_data)
    remap = make_remap_from_perm(best_perm)

    print("Testing...")
    correct, gc, errors = evaluate_fast(fn, remap, verbose=True)
    status = "CORRECT" if correct else f"WRONG ({len(errors)} errors)"
    print(f"\nResult: {status}")
    print(f"Gates:  {gc}")

    if errors:
        print(f"First 5 errors:")
        for a_i, b_i, exp, got in errors[:5]:
            print(f"  {FP4_TABLE[a_i]} × {FP4_TABLE[b_i]}: exp={exp} got={got}")

    # If correct and good gate count, save the circuit
    if correct:
        # Save the multiplier code
        out_dir = os.path.join(os.path.dirname(__file__), "..", "autoresearch")
        with open(os.path.join(out_dir, "multiplier_qm.py"), 'w') as f:
            f.write(f"# QM-synthesized multiplier, perm={list(best_perm)}, {gc} gates\n\n")
            f.write(f"INPUT_REMAP_INT = {remap}\n\n")
            f.write(code)
            f.write("\n\n# Gate count: " + str(gc))
        print(f"\nSaved to autoresearch/multiplier_qm.py")

        # Also save results
        out = {"perm": list(best_perm), "gate_count": gc, "correct": correct,
               "top10": [{"total": t, "mag": m, "perm": list(p)} for t, m, p in results[:10]]}
        with open(os.path.join(out_dir, "data", "qm_zero000_results.json"), 'w') as f:
            json.dump(out, f, indent=2)

    # Also try the top 5 remappings to find the actual best (QM estimate ≠ true gate count)
    print(f"\nTesting actual gate counts for top 10 permutations...")
    actual_results = []
    for est, mag, perm in results[:10]:
        _, per_bit = synthesize_perm_zero000(perm)
        fn = build_multiplier_fn(perm, per_bit)
        remap = make_remap_from_perm(perm)
        ok, gc_actual, errs = evaluate_fast(fn, remap)
        actual_results.append((gc_actual if ok else 9999, ok, gc_actual, perm))
        print(f"  perm={list(perm)}: est={est}, actual={'OK:'+str(gc_actual) if ok else 'WRONG:'+str(len(errs))}")

    actual_results.sort()
    best_actual = actual_results[0]
    print(f"\nBest actual: {best_actual[2]} gates, perm={list(best_actual[3])}, correct={best_actual[1]}")
