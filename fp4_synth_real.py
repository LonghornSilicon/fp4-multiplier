"""
Real circuit synthesis for FP4 multiplier.

Key insight from mathematical analysis:
  - All non-zero FP4 magnitudes = 1.5^M * 2^E, where M∈{0,1}, E∈{-1,0,1,2}
  - Product magnitude × 4 = 1.5^(Ma+Mb) * 2^(Ea+Eb+2)
  - This gives three "types": K∈{1,3,9} × shift k∈{0..6}
  - In binary: K=1 → single bit; K=3 → adjacent bits; K=9 → bits distance-3 apart

Strategy:
  1. Separate sign (1 gate: XOR) and magnitude (6 inputs)
  2. Minimize 6-input magnitude circuit (2^6=64 entries per bit → fast QM)
  3. Add conditional negation for two's complement (carry chain)
  4. Total = 1 + magnitude_gates + negation_gates

  Also search over input remappings to minimize magnitude circuit.
"""

import itertools
from fp4_core import FP4_VALUES, MAGNITUDES, build_truth_table, tt_to_bit_functions

# ─── Build magnitude-only truth table (6 inputs) ────────────────────────────

def build_magnitude_tt(mag_perm: tuple):
    """
    Build magnitude (unsigned) truth table: 6 inputs (3 per value) → 8 output bits.
    Returns: dict[(a_mag_code3, b_mag_code3)] -> list of 8 bits [MSB..LSB].

    This is the unsigned |4*a*b| for all pairs of magnitudes.
    The sign bit is handled separately.
    """
    table = {}
    for a_mag_idx in range(8):
        for b_mag_idx in range(8):
            a_mag = MAGNITUDES[a_mag_idx]
            b_mag = MAGNITUDES[b_mag_idx]
            val = round(a_mag * b_mag * 4)
            # 8-bit unsigned representation
            bits = [(val >> (7 - i)) & 1 for i in range(8)]

            a_code = mag_perm[a_mag_idx]
            b_code = mag_perm[b_mag_idx]
            table[(a_code, b_code)] = bits
    return table


def mag_tt_to_funcs(mag_tt: dict):
    """Convert magnitude truth table to 8 boolean functions (6-input, 64-entry each)."""
    funcs = [[0] * 64 for _ in range(8)]
    for (a, b), bits in mag_tt.items():
        idx = (a << 3) | b  # 6-bit index
        for i, bit in enumerate(bits):
            funcs[i][idx] = bit
    return funcs


# ─── Quine-McCluskey for 6 inputs ───────────────────────────────────────────

def qm_exact(ones_set: set, n_vars: int = 6):
    """
    Exact Quine-McCluskey prime implicant generation for n_vars inputs.
    ones_set: set of integers (minterms).
    Returns: list of (mask, val) tuples (prime implicants).
    mask bits: 1 = this bit is relevant, 0 = don't care
    val bits: value of relevant bits
    """
    if not ones_set:
        return []

    full_mask = (1 << n_vars) - 1

    # Group minterms by popcount
    from collections import defaultdict
    groups = defaultdict(set)
    for m in ones_set:
        groups[bin(m).count('1')].add((full_mask, m))

    prime_implicants = set()
    current_implicants = {(full_mask, m) for m in ones_set}

    while current_implicants:
        next_implicants = set()
        used = set()

        imps = list(current_implicants)
        for i in range(len(imps)):
            for j in range(i + 1, len(imps)):
                mask_i, val_i = imps[i]
                mask_j, val_j = imps[j]
                if mask_i != mask_j:
                    continue
                diff = val_i ^ val_j
                if diff == 0 or (diff & (diff - 1)) != 0:
                    continue  # must differ in exactly 1 relevant bit
                if not (diff & mask_i):
                    continue  # diff must be in relevant bits
                new_mask = mask_i & ~diff
                new_val = val_i & ~diff
                next_implicants.add((new_mask, new_val))
                used.add(imps[i])
                used.add(imps[j])

        for imp in current_implicants:
            if imp not in used:
                prime_implicants.add(imp)
        current_implicants = next_implicants

    return list(prime_implicants)


def greedy_cover(ones_set: set, prime_implicants: list, n_vars: int = 6):
    """Greedy minimum set cover of prime implicants."""
    if not ones_set:
        return []

    def covered(mask, val):
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

    pi_cov = {imp: covered(*imp) for imp in prime_implicants}
    uncovered = set(ones_set)
    cover = []

    # First: essential prime implicants
    for minterm in list(uncovered):
        covering_pis = [imp for imp in prime_implicants if minterm in pi_cov[imp]]
        if len(covering_pis) == 1:
            cover.append(covering_pis[0])
            uncovered -= pi_cov[covering_pis[0]]

    # Greedy rest
    while uncovered:
        best = max(prime_implicants, key=lambda p: len(pi_cov[p] & uncovered))
        if not pi_cov[best] & uncovered:
            break
        cover.append(best)
        uncovered -= pi_cov[best]

    return cover


def sop_gate_cost_6input(implicants, n_vars=6):
    """
    Gate cost for a SOP expression with the given implicants (6-input variant).
    Each AND term of k relevant literals: k-1 AND gates + NOT gates for negated literals.
    Final OR: len(implicants)-1 OR gates (or 0 if single term).
    """
    if not implicants:
        return 0
    total = 0
    for mask, val in implicants:
        relevant = bin(mask).count('1')
        n_negated = sum(1 for b in range(n_vars) if (mask >> b) & 1 and not (val >> b) & 1)
        if relevant == 0:
            term_cost = 0
        elif relevant == 1:
            term_cost = n_negated  # 0 or 1 NOT
        else:
            term_cost = (relevant - 1) + n_negated  # ANDs + NOTs
        total += term_cost
    if len(implicants) > 1:
        total += len(implicants) - 1  # OR gates
    return total


# ─── Conditional negation cost ────────────────────────────────────────────────

def conditional_negation_cost(n_bits=8):
    """
    Gate cost for conditional two's complement negation.
    result_i = XOR(M_i, S) XOR c_i
    c_{i+1} = AND(XOR(M_i, S), c_i), c_0 = S (free)

    For n_bits: n*XOR (for t_i=XOR(M_i,S)) + n*XOR (for XOR(t_i,c_i)) + (n-1)*AND
    But we can share: t_i is used in BOTH the result XOR and the carry AND.
    So: n XOR + n XOR + (n-1) AND = 3n-1 gates.
    But if t_0 is the carry chain start: c_0=S, no AND needed for first bit.
    Adjusted: n XOR (for t_i) + n XOR (for result) + (n-1) AND (for carry) = 3n-1 total.
    """
    return 3 * n_bits - 1


# ─── Full synthesis for a given remapping ────────────────────────────────────

def synthesize_with_remap(mag_perm: tuple, verbose=False):
    """
    Full synthesis estimate for a magnitude permutation.
    Returns: total_gate_count (estimated).
    """
    mag_tt = build_magnitude_tt(mag_perm)
    funcs = mag_tt_to_funcs(mag_tt)

    total_mag_gates = 0
    per_bit = []

    for bit_idx, f in enumerate(funcs):
        ones = {i for i, v in enumerate(f) if v == 1}
        zeros = {i for i, v in enumerate(f) if v == 0}

        if not ones:
            per_bit.append((bit_idx, 0, []))
            continue
        if not zeros:
            per_bit.append((bit_idx, 0, []))
            continue

        # Try SOP
        pi_sop = qm_exact(ones, n_vars=6)
        cover_sop = greedy_cover(ones, pi_sop, n_vars=6)
        cost_sop = sop_gate_cost_6input(cover_sop, n_vars=6)

        # Try POS (minimize zeros, negate result)
        pi_pos = qm_exact(zeros, n_vars=6)
        cover_pos = greedy_cover(zeros, pi_pos, n_vars=6)
        cost_pos = sop_gate_cost_6input(cover_pos, n_vars=6) + 1  # +1 for final NOT

        cost = min(cost_sop, cost_pos)
        total_mag_gates += cost
        per_bit.append((bit_idx, cost, cover_sop if cost_sop <= cost_pos else cover_pos))

    # Sign gate
    sign_gate = 1  # XOR(a0, b0)

    # Conditional negation
    cond_neg = conditional_negation_cost(8)

    total = sign_gate + total_mag_gates + cond_neg
    if verbose:
        print(f"  Sign gate: {sign_gate}")
        print(f"  Magnitude circuit: {total_mag_gates} gates")
        print(f"  Conditional negation: {cond_neg} gates")
        print(f"  Total: {total} gates")
        print(f"  Per-bit costs: {[c for _, c, _ in per_bit]}")
    return total, total_mag_gates, per_bit


def search_remappings_real(verbose=True):
    """Search all 8! remappings with real QM synthesis."""
    results = []
    best = float('inf')

    for i, perm in enumerate(itertools.permutations(range(8))):
        total, mag_gates, _ = synthesize_with_remap(perm)
        results.append((total, mag_gates, perm))
        if total < best:
            best = total
            print(f"  [{i}/40320] New best total={total} (mag={mag_gates}), perm={list(perm)}")
        elif verbose and i % 2000 == 0:
            print(f"  [{i}/40320] current best: {best}")

    results.sort()
    return results


# ─── Shared gate analysis ────────────────────────────────────────────────────

def find_shared_gates(mag_perm: tuple, n_vars=6):
    """Find common sub-expressions across output bits to reduce total gate count."""
    mag_tt = build_magnitude_tt(mag_perm)
    funcs = mag_tt_to_funcs(mag_tt)

    from collections import Counter
    all_covers = {}
    for bit_idx, f in enumerate(funcs):
        ones = {i for i, v in enumerate(f) if v == 1}
        if not ones or len(ones) == 64:
            continue
        pis = qm_exact(ones, n_vars=n_vars)
        cover = greedy_cover(ones, pis, n_vars=n_vars)
        all_covers[bit_idx] = set(cover)

    # Count implicant reuse
    usage = Counter()
    for covers in all_covers.values():
        for imp in covers:
            usage[imp] += 1

    shared = [(cnt, imp) for imp, cnt in usage.items() if cnt > 1]
    shared.sort(reverse=True)

    # Estimate savings from sharing
    saving = sum((cnt - 1) * sop_gate_cost_6input([imp]) for cnt, imp in shared)
    return shared, saving


# ─── Alternative: compute magnitude without conditional negation ─────────────

def synthesize_direct_9bit(mag_perm: tuple, verbose=False):
    """
    Directly synthesize all 9 output bits from 8 inputs (a0..a3, b0..b3).
    This avoids the conditional negation overhead by treating all bits jointly.
    """
    # Build full truth table
    tt = build_truth_table(mag_perm)
    funcs = tt_to_bit_functions(tt)

    total_gates = 0
    per_bit_cost = []

    for bit_idx, f in enumerate(funcs):
        ones = {i for i, v in enumerate(f) if v == 1}
        zeros = {i for i, v in enumerate(f) if v == 0}

        if not ones:
            per_bit_cost.append(0)
            continue
        if not zeros:
            per_bit_cost.append(0)
            continue

        # For 8 inputs (64..256 minterms), use QM
        pi_sop = qm_exact(ones, n_vars=8)
        cover_sop = greedy_cover(ones, pi_sop, n_vars=8)
        cost_sop = sop_gate_cost_6input(cover_sop, n_vars=8)

        pi_pos = qm_exact(zeros, n_vars=8)
        cover_pos = greedy_cover(zeros, pi_pos, n_vars=8)
        cost_pos = sop_gate_cost_6input(cover_pos, n_vars=8) + 1

        cost = min(cost_sop, cost_pos)
        per_bit_cost.append(cost)
        total_gates += cost

    if verbose:
        print(f"  Direct 9-bit synthesis (no sharing): {total_gates} gates")
        print(f"  Per-bit: {per_bit_cost}")
    return total_gates, per_bit_cost


if __name__ == "__main__":
    print("=" * 60)
    print("FP4 Multiplier - Real Gate Synthesis")
    print("=" * 60)

    # Analyze default encoding
    print("\n--- Default encoding (magnitude circuit, 6 inputs) ---")
    total, mag_gates, per_bit = synthesize_with_remap(tuple(range(8)), verbose=True)

    print("\n--- Default encoding (direct 9-bit, 8 inputs) ---")
    direct_total, direct_per_bit = synthesize_direct_9bit(tuple(range(8)), verbose=True)

    # Check sharing for default
    shared, saving = find_shared_gates(tuple(range(8)))
    print(f"\nShared terms in default encoding: {len(shared)} terms, potential saving: {saving} gates")
    for cnt, (mask, val) in shared[:5]:
        print(f"  used {cnt}x: mask={mask:06b} val={val:06b}")

    # Quick search over a subset of remappings
    print("\n--- Searching best remapping (all 8! = 40320) ---")
    results = search_remappings_real(verbose=True)

    print(f"\nTop 10:")
    for total, mag_gates, perm in results[:10]:
        print(f"  total={total:4d}, mag={mag_gates:3d}, perm={list(perm)}")

    print(f"\nBottom 5 (worst):")
    for total, mag_gates, perm in results[-5:]:
        print(f"  total={total:4d}, mag={mag_gates:3d}, perm={list(perm)}")

    # Detailed analysis of best remapping
    best_total, best_mag, best_perm = results[0]
    print(f"\n--- Best remapping detailed analysis ---")
    print(f"Perm: {list(best_perm)}")
    print(f"Encoding:")
    for i, mag in enumerate(MAGNITUDES):
        print(f"  {mag:4.1f} -> {best_perm[i]:03b}")
    synthesize_with_remap(best_perm, verbose=True)

    # Check if direct 9-bit synthesis beats the 2-stage approach
    print(f"\n--- Direct 9-bit synthesis of best remapping ---")
    d_total, d_per_bit = synthesize_direct_9bit(best_perm, verbose=True)
    print(f"2-stage: {best_total}, Direct: {d_total}")
    print(f"Winner: {'Direct' if d_total < best_total else '2-stage'}")
