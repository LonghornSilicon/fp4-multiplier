"""
Track A: Best remapping + exact (Petrick's method) QM set cover.

Runs all 8! = 40,320 magnitude permutations with exact minimum cover
instead of greedy. Reports best gate counts and generates circuit code.

Also tries both 2-stage (sign + magnitude + cond_neg) and direct 9-bit synthesis.
"""

import sys
import os
import itertools
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fp4_core import FP4_VALUES, MAGNITUDES, build_truth_table, tt_to_bit_functions
from fp4_synth_real import (
    build_magnitude_tt, mag_tt_to_funcs, qm_exact, greedy_cover,
    sop_gate_cost_6input, conditional_negation_cost
)


# ── Exact minimum cover via Petrick's method ──────────────────────────────────

def petrick_min_cover(ones_set: set, prime_implicants: list, n_vars: int = 6):
    """
    Exact minimum cover using Petrick's method.
    Returns the minimum-cost cover (list of prime implicants).
    """
    if not ones_set:
        return []
    if not prime_implicants:
        return []

    # Compute coverage for each PI
    def covered_by(mask, val):
        result = set()
        dontcare_bits = [b for b in range(n_vars) if not (mask >> b) & 1]
        for combo in range(1 << len(dontcare_bits)):
            m = val
            for k, bit in enumerate(dontcare_bits):
                if (combo >> k) & 1:
                    m |= (1 << bit)
            if m in ones_set:
                result.add(m)
        return result

    pi_list = list(prime_implicants)
    pi_cov = [covered_by(mask, val) for mask, val in pi_list]

    # Essential PIs
    essential = []
    covered = set()
    uncovered = set(ones_set)

    for minterm in list(uncovered):
        covering = [i for i, cov in enumerate(pi_cov) if minterm in cov]
        if len(covering) == 1:
            idx = covering[0]
            if pi_list[idx] not in essential:
                essential.append(pi_list[idx])
                covered |= pi_cov[idx]
    uncovered -= covered

    if not uncovered:
        return essential

    # Petrick's method on remaining
    # Build a list of "clauses": for each uncovered minterm, the set of PIs that cover it
    relevant_pis = [i for i, cov in enumerate(pi_cov) if cov & uncovered]
    pi_costs = [sop_gate_cost_6input([pi_list[i]], n_vars) for i in relevant_pis]

    # Build covering sets
    clauses = []
    for minterm in uncovered:
        clause = frozenset(i for i in relevant_pis if minterm in pi_cov[i])
        if not clause:
            return None  # uncoverable
        clauses.append(clause)

    # Convert to Petrick's product of sums → enumerate minimum covers
    # Use branch and bound with cost pruning
    best_cost = [float('inf')]
    best_cover = [None]

    def bnb(clause_idx, current_pis, current_cost, still_uncovered):
        if current_cost >= best_cost[0]:
            return
        if not still_uncovered:
            if current_cost < best_cost[0]:
                best_cost[0] = current_cost
                best_cover[0] = list(current_pis)
            return

        if clause_idx >= len(clauses):
            return

        # Skip already covered clauses
        while clause_idx < len(clauses):
            remaining_in_clause = clauses[clause_idx] & (set(relevant_pis) - current_pis)
            if clauses[clause_idx] & current_pis:
                clause_idx += 1  # already covered
            else:
                break
        else:
            if not still_uncovered:
                if current_cost < best_cost[0]:
                    best_cost[0] = current_cost
                    best_cover[0] = list(current_pis)
            return

        if clause_idx >= len(clauses):
            if not still_uncovered:
                if current_cost < best_cost[0]:
                    best_cost[0] = current_cost
                    best_cover[0] = list(current_pis)
            return

        # Try each PI in the first uncovered clause
        for pi_idx in sorted(clauses[clause_idx], key=lambda i: pi_costs[relevant_pis.index(i)] if i in relevant_pis else 0):
            if pi_idx not in relevant_pis:
                continue
            pi = pi_list[pi_idx]
            cost = sop_gate_cost_6input([pi], n_vars)
            new_uncovered = still_uncovered - pi_cov[pi_idx]
            bnb(clause_idx + 1, current_pis | {pi_idx}, current_cost + cost,
                new_uncovered)

    bnb(0, set(), 0, uncovered)

    if best_cover[0] is None:
        return essential + greedy_cover(uncovered, [pi_list[i] for i in relevant_pis], n_vars)

    extra = [pi_list[i] for i in best_cover[0]]
    return essential + extra


def synthesize_exact_cover(mag_perm: tuple, n_vars=6, verbose=False):
    """Like synthesize_with_remap but using exact (Petrick) cover."""
    mag_tt = build_magnitude_tt(mag_perm)
    funcs = mag_tt_to_funcs(mag_tt)

    total_mag_gates = 0
    per_bit = []

    for bit_idx, f in enumerate(funcs):
        ones = {i for i, v in enumerate(f) if v == 1}
        zeros = {i for i, v in enumerate(f) if v == 0}

        if not ones or not zeros:
            per_bit.append((bit_idx, 0, []))
            continue

        # SOP with exact cover
        pi_sop = qm_exact(ones, n_vars=n_vars)
        cover_sop = petrick_min_cover(ones, pi_sop, n_vars=n_vars)
        if cover_sop is None:
            cover_sop = greedy_cover(ones, pi_sop, n_vars=n_vars)
        cost_sop = sop_gate_cost_6input(cover_sop, n_vars=n_vars)

        # POS with exact cover
        pi_pos = qm_exact(zeros, n_vars=n_vars)
        cover_pos = petrick_min_cover(zeros, pi_pos, n_vars=n_vars)
        if cover_pos is None:
            cover_pos = greedy_cover(zeros, pi_pos, n_vars=n_vars)
        cost_pos = sop_gate_cost_6input(cover_pos, n_vars=n_vars) + 1

        cost = min(cost_sop, cost_pos)
        total_mag_gates += cost
        per_bit.append((bit_idx, cost, cover_sop if cost_sop <= cost_pos else cover_pos))

    sign_gate = 1
    cond_neg = conditional_negation_cost(8)
    total = sign_gate + total_mag_gates + cond_neg

    if verbose:
        print(f"  Sign: {sign_gate}, Magnitude: {total_mag_gates}, "
              f"CondNeg: {cond_neg}, Total: {total}")
    return total, total_mag_gates, per_bit


def search_all_exact(max_perms=None, verbose=True):
    """Search all (or max_perms) remappings with exact cover."""
    results = []
    best = float('inf')

    perms = list(itertools.permutations(range(8)))
    if max_perms:
        perms = perms[:max_perms]

    for i, perm in enumerate(perms):
        total, mag_gates, _ = synthesize_exact_cover(perm)
        results.append((total, mag_gates, perm))
        if total < best:
            best = total
            if verbose:
                print(f"  [{i}/{len(perms)}] New best: total={total} (mag={mag_gates}), perm={list(perm)}")
        elif verbose and i % 2000 == 0:
            print(f"  [{i}/{len(perms)}] best so far: {best}")

    results.sort()
    return results


# ── Shared subexpression analysis ─────────────────────────────────────────────

def analyze_sharing(mag_perm: tuple, n_vars=6):
    """Find how much gate sharing can reduce the total cost."""
    mag_tt = build_magnitude_tt(mag_perm)
    funcs = mag_tt_to_funcs(mag_tt)

    from collections import Counter
    all_implicants = []
    for bit_idx, f in enumerate(funcs):
        ones = {i for i, v in enumerate(f) if v == 1}
        if not ones or len(ones) == 64:
            continue
        pis = qm_exact(ones, n_vars=n_vars)
        cover = petrick_min_cover(ones, pis, n_vars=n_vars) or greedy_cover(ones, pis, n_vars)
        all_implicants.append((bit_idx, cover))

    usage = Counter()
    for _, cover in all_implicants:
        for imp in cover:
            usage[imp] += 1

    shared = [(cnt, imp) for imp, cnt in usage.items() if cnt > 1]
    shared.sort(reverse=True)
    saving = sum((cnt - 1) * sop_gate_cost_6input([imp], n_vars) for cnt, imp in shared)
    return shared, saving


# ── Generate Python circuit code for the best remapping ──────────────────────

def generate_circuit_code(mag_perm: tuple, n_vars=6):
    """
    Generate Python circuit code for the given magnitude remapping.
    Returns the code as a string.
    """
    mag_tt = build_magnitude_tt(mag_perm)
    funcs = mag_tt_to_funcs(mag_tt)

    lines = []
    lines.append("# Magnitude circuit (6 inputs: a1,a2,a3,b1,b2,b3 = magnitude bits)")
    lines.append("# Inputs after remapping with perm: " + str(list(mag_perm)))

    for bit_idx, f in enumerate(funcs):
        ones = {i for i, v in enumerate(f) if v == 1}
        zeros = {i for i, v in enumerate(f) if v == 0}

        if not ones:
            lines.append(f"m{7-bit_idx} = False  # constant 0")
            continue
        if not zeros:
            lines.append(f"m{7-bit_idx} = True   # constant 1")
            continue

        pi_sop = qm_exact(ones, n_vars=n_vars)
        cover = petrick_min_cover(ones, pi_sop, n_vars=n_vars) or greedy_cover(ones, pi_sop, n_vars)

        var_names = ['a1', 'a2', 'a3', 'b1', 'b2', 'b3']
        terms = []
        for mask, val in cover:
            lits = []
            for bit in range(n_vars):
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
                terms.append("AND(" * (len(lits)-1) + lits[0] + "".join(f", {l})" for l in lits[1:]))

        if len(terms) == 1:
            expr = terms[0]
        else:
            expr = "OR(" * (len(terms)-1) + terms[0] + "".join(f", {t})" for t in terms[1:])

        lines.append(f"m{7-bit_idx} = {expr}")

    return '\n'.join(lines)


# ── Main ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 70)
    print("Track A: Best remapping + exact QM cover")
    print("=" * 70)

    print("\nSearching all 8! = 40,320 remappings with exact cover...")
    results = search_all_exact(verbose=True)

    print(f"\nTop 10 remappings (exact cover):")
    for total, mag, perm in results[:10]:
        print(f"  total={total:4d} (mag={mag:3d}, cond_neg=23), perm={list(perm)}")

    best_perm = results[0][2]
    best_total = results[0][0]

    print(f"\n--- Sharing analysis for best perm {list(best_perm)} ---")
    shared, saving = analyze_sharing(best_perm)
    print(f"Shared terms: {len(shared)}, potential saving: {saving} gates")
    for cnt, (mask, val) in shared[:10]:
        print(f"  used {cnt}x: mask={mask:06b} val={val:06b} "
              f"cost={sop_gate_cost_6input([(mask,val)])}")

    effective_total = best_total - saving
    print(f"\nWith sharing: {best_total} - {saving} = {effective_total} gates (estimate)")

    print(f"\n--- Generated circuit for best perm ---")
    print(generate_circuit_code(best_perm))

    # Save results
    out = {
        "best_perm": list(best_perm),
        "best_total": best_total,
        "sharing_saving": saving,
        "effective_total": effective_total,
        "top_10": [{"total": t, "mag": m, "perm": list(p)} for t, m, p in results[:10]],
    }
    out_path = os.path.join(os.path.dirname(__file__), "..", "autoresearch", "data",
                            "track_a_results.json")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, 'w') as f:
        json.dump(out, f, indent=2)
    print(f"\nSaved results to {out_path}")
