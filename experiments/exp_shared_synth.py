"""
Track C: Direct 9-bit synthesis with gate sharing and XOR decomposition.

Approaches:
1. Check if each output bit decomposes as f(a_bits) XOR g(b_bits)
2. Build 9 independent QM minimizations (8-input), then find shared sub-expressions
3. Use a 2-level AND-OR forest and eliminate common AND terms

This directly attacks the full truth table without structural assumptions.
"""

import sys
import os
import itertools
from collections import Counter, defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fp4_core import build_truth_table, tt_to_bit_functions, MAGNITUDES, FP4_VALUES
from fp4_synth_real import qm_exact, greedy_cover, sop_gate_cost_6input


FP4_TABLE = [0.0, 0.5, 1.0, 1.5, 2.0, 3.0, 4.0, 6.0,
             0.0, -0.5, -1.0, -1.5, -2.0, -3.0, -4.0, -6.0]


# ── XOR decomposability check ─────────────────────────────────────────────────

def check_xor_decomposable(func, n_inputs=8):
    """
    Check if f(a,b) = g(a) XOR h(b) for some g,h.
    For an 8-input func indexed as (a_bits << 4) | b_bits.

    Condition: f(a1,b1) XOR f(a1,b2) XOR f(a2,b1) XOR f(a2,b2) = 0 for all a1,a2,b1,b2.
    """
    n_a = 4  # a has 4 bits
    n_b = 4  # b has 4 bits
    for a1 in range(16):
        for a2 in range(16):
            for b1 in range(16):
                for b2 in range(16):
                    val = (func[(a1 << 4) | b1] ^ func[(a1 << 4) | b2] ^
                           func[(a2 << 4) | b1] ^ func[(a2 << 4) | b2])
                    if val != 0:
                        return False, None, None
    # If decomposable, extract g and h
    # g(a) = f(a, 0)
    # h(b) = f(0, b)
    # Then f(a,b) = g(a) XOR h(b) XOR f(0,0)
    # If f(0,0) = 0: f = g XOR h
    # If f(0,0) = 1: f = g XOR NOT(h) = g XOR (h XOR 1)
    g = [func[(a << 4) | 0] for a in range(16)]
    h = [func[b] for b in range(16)]
    offset = func[0]  # f(0,0)
    # Verify
    for a in range(16):
        for b in range(16):
            expected = g[a] ^ h[b] ^ offset
            if func[(a << 4) | b] != expected:
                return False, None, None
    return True, g, h


def check_and_decomposable(func):
    """Check if f(a,b) = g(a) AND h(b)."""
    for a1 in range(16):
        for b1 in range(16):
            if func[(a1 << 4) | b1] == 0:
                continue
            for b2 in range(16):
                if func[(a1 << 4) | b2] == 1:
                    # a1 enables output for both b1 and b2 via some structure
                    pass
    # Simple check: f is 1 only when both g(a)=1 and h(b)=1
    # Find which a-values can produce 1 (for any b)
    active_a = {a for a in range(16) if any(func[(a << 4) | b] for b in range(16))}
    active_b = {b for b in range(16) if any(func[(a << 4) | b] for a in range(16))}
    # Check if f = g AND h where g(a)=1 iff a in active_a and h(b)=1 iff b in active_b
    for a in range(16):
        for b in range(16):
            expected = int((a in active_a) and (b in active_b))
            if func[(a << 4) | b] != expected:
                return False
    return True


# ── 8-input QM synthesis ───────────────────────────────────────────────────────

def qm_8input(ones_set, n_vars=8):
    """QM for 8-input functions."""
    return qm_exact(ones_set, n_vars=n_vars)


def sop_cost_8input(implicants, n_vars=8):
    """Gate cost for 8-input SOP."""
    return sop_gate_cost_6input(implicants, n_vars=n_vars)


def synthesize_bit_8input(func, prefer='sop'):
    """
    Synthesize a single output bit function (8 inputs, 256 entries).
    Returns (cost, implicants, is_pos).
    """
    ones = {i for i, v in enumerate(func) if v == 1}
    zeros = {i for i, v in enumerate(func) if v == 0}

    if not ones:
        return 0, [], False  # constant 0
    if not zeros:
        return 0, [], False  # constant 1

    # SOP
    pi_sop = qm_8input(ones, n_vars=8)
    cover_sop = greedy_cover(ones, pi_sop, n_vars=8)
    cost_sop = sop_cost_8input(cover_sop, n_vars=8)

    # POS
    pi_pos = qm_8input(zeros, n_vars=8)
    cover_pos = greedy_cover(zeros, pi_pos, n_vars=8)
    cost_pos = sop_cost_8input(cover_pos, n_vars=8) + 1  # +1 NOT

    if cost_sop <= cost_pos:
        return cost_sop, cover_sop, False
    else:
        return cost_pos, cover_pos, True


# ── Shared sub-expression analysis ───────────────────────────────────────────

def find_shared_subexprs(funcs_covers):
    """
    Given per-bit covers {bit_idx: [(mask,val), ...]}, find shared AND terms.
    Returns: list of ((mask,val), count) for terms appearing in 2+ outputs.
    """
    usage = Counter()
    for bit_idx, (cost, cover, is_pos) in funcs_covers.items():
        for imp in cover:
            usage[imp] += 1
    return [(imp, cnt) for imp, cnt in usage.items() if cnt > 1]


def compute_sharing_savings(shared_terms, n_vars=8):
    """Compute gate savings from CSE."""
    total_saving = 0
    for imp, cnt in shared_terms:
        # Cost of computing this implicant once
        cost = sop_cost_8input([imp], n_vars=n_vars)
        # Saving: compute once instead of cnt times
        total_saving += (cnt - 1) * cost
    return total_saving


# ── Main analysis ─────────────────────────────────────────────────────────────

def analyze_remap(mag_perm):
    """
    Full analysis for a given remapping: direct 9-bit synthesis with sharing.
    """
    from fp4_core import build_truth_table, tt_to_bit_functions

    tt = build_truth_table(mag_perm)
    funcs = tt_to_bit_functions(tt)  # list of 9 functions, each 256 entries

    print(f"\n--- Analyzing perm {list(mag_perm)} ---")

    total_no_share = 0
    xor_decomp_bits = []
    funcs_covers = {}

    for bit_idx, f in enumerate(funcs):
        ones = sum(f)
        zeros = 256 - ones

        # Check XOR decomposability
        is_xor, g, h = check_xor_decomposable(f)
        # Check AND decomposability
        is_and = check_and_decomposable(f)

        # QM synthesis
        cost, cover, is_pos = synthesize_bit_8input(f)
        funcs_covers[bit_idx] = (cost, cover, is_pos)
        total_no_share += cost

        xor_str = " [XOR-decomp]" if is_xor else ""
        and_str = " [AND-decomp]" if is_and else ""
        pos_str = " (POS)" if is_pos else ""
        print(f"  bit {bit_idx}: {ones:3d} ones, {zeros:3d} zeros | "
              f"cost={cost:3d}{pos_str}{xor_str}{and_str}")

        if is_xor:
            xor_decomp_bits.append((bit_idx, g, h, f[0]))

    print(f"Total without sharing: {total_no_share} gates")

    # Find shared terms
    shared = find_shared_subexprs(funcs_covers)
    savings = compute_sharing_savings(shared)
    print(f"Shared AND terms: {len(shared)}, gate savings: {savings}")
    print(f"Estimated with sharing: {total_no_share - savings} gates")

    # XOR decomposition savings
    if xor_decomp_bits:
        print(f"\nXOR-decomposable bits: {[b for b,_,_,_ in xor_decomp_bits]}")
        for bit_idx, g, h, offset in xor_decomp_bits:
            # Cost of g (4-input function)
            ones_g = {a for a in range(16) if g[a]}
            pi_g = qm_exact(ones_g, n_vars=4)
            cov_g = greedy_cover(ones_g, pi_g, n_vars=4)
            cost_g = sop_gate_cost_6input(cov_g, n_vars=4)

            ones_h = {b for b in range(16) if h[b] ^ offset}
            pi_h = qm_exact(ones_h, n_vars=4)
            cov_h = greedy_cover(ones_h, pi_h, n_vars=4)
            cost_h = sop_gate_cost_6input(cov_h, n_vars=4)

            xor_cost = cost_g + cost_h + 1  # +1 for XOR
            orig_cost = funcs_covers[bit_idx][0]
            print(f"  bit {bit_idx}: XOR(g,h) cost = {cost_g}+{cost_h}+1 = {xor_cost} "
                  f"vs original {orig_cost} gates {'[BETTER]' if xor_cost < orig_cost else ''}")

    return total_no_share, savings, xor_decomp_bits


# ── Main ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import json

    print("=" * 70)
    print("Track C: Direct 9-bit synthesis with gate sharing")
    print("=" * 70)

    # Test a handful of promising permutations
    # First the identity (default encoding)
    print("\n=== Default encoding ===")
    total_def, savings_def, _ = analyze_remap(tuple(range(8)))

    # Then try a few promising ones from the heuristic search
    # (would normally come from Track A results)
    test_perms = [
        (0, 1, 2, 3, 4, 5, 6, 7),  # identity
        (0, 2, 4, 6, 1, 3, 5, 7),  # interleaved
        (0, 4, 2, 6, 1, 5, 3, 7),  # another pattern
    ]

    results = []
    for perm in test_perms:
        total, savings, xor_bits = analyze_remap(perm)
        results.append({
            "perm": list(perm),
            "total_no_share": total,
            "savings": savings,
            "effective": total - savings,
            "xor_decomp_bits": [b for b, _, _, _ in xor_bits],
        })

    # Now do a targeted search over best QM remappings
    # Load from track A results if available
    track_a_path = os.path.join(os.path.dirname(__file__), "..", "autoresearch", "data",
                                "track_a_results.json")
    if os.path.exists(track_a_path):
        with open(track_a_path) as f:
            track_a = json.load(f)
        print(f"\nUsing Track A top remappings for Track C analysis...")
        for item in track_a.get("top_10", [])[:5]:
            perm = tuple(item["perm"])
            if list(perm) not in [r["perm"] for r in results]:
                total, savings, xor_bits = analyze_remap(perm)
                results.append({
                    "perm": list(perm),
                    "total_no_share": total,
                    "savings": savings,
                    "effective": total - savings,
                })

    results.sort(key=lambda x: x["effective"])
    print(f"\n=== Track C Summary ===")
    for r in results:
        print(f"  perm={r['perm']}: {r['total_no_share']} gates, "
              f"-{r['savings']} sharing = {r['effective']} effective")

    out_path = os.path.join(os.path.dirname(__file__), "..", "autoresearch", "data",
                            "track_c_results.json")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, 'w') as f:
        json.dump({"results": results}, f, indent=2)
    print(f"Saved to {out_path}")
