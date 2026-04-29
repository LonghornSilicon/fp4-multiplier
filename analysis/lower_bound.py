"""
Theoretical lower bounds on the FP4xFP4 multiplier gate count
==============================================================

For each of the 9 output bits f_i : {0,1}^8 -> {0,1}, computes:
  1. Algebraic Normal Form (ANF / Reed-Muller) over GF(2).
  2. Polynomial degree deg(f_i).
  3. Number of monomials m_i in the ANF.
  4. Multiplicative complexity lower bound c(f_i):
       The minimum number of AND2 gates needed to compute f_i over the
       basis {AND2, XOR2, NOT1}. We use the standard "deg-1" lower bound:
       c(f) >= deg(f) - 1 for non-constant non-affine f.
       (Tighter bounds exist but require more compute; this is a baseline.)

Then aggregates across all 9 outputs to give:
  - total deg-based AND lower bound (no sharing)
  - total monomial count (counts shared monomials only once)
  - lower bound on total gate count assuming maximum sharing

Outputs a Markdown report to stdout.

Uses Longhorn's sigma input remap (the same one our 63-gate solution uses).
"""
from __future__ import annotations
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from collections import Counter
from itertools import combinations, product
from fp4_core import FP4_VALUES, fp4_product_qi9, qi9_to_bits


SIGMA = {
    0.0: 0b0000, 0.5: 0b0001, 1.0: 0b0010, 1.5: 0b0011,
    2.0: 0b0110, 3.0: 0b0111, 4.0: 0b0100, 6.0: 0b0101,
}


def build_funcs_under_sigma():
    """Build truth table for the 9 outputs over the 8-bit input space
    (a3 a2 a1 a0 b3 b2 b1 b0), under Longhorn's sigma remapping."""
    funcs = [[0] * 256 for _ in range(9)]
    for a_orig in range(16):
        for b_orig in range(16):
            a_val = FP4_VALUES[a_orig]
            b_val = FP4_VALUES[b_orig]
            a_sign = 1 if a_val < 0 else 0
            b_sign = 1 if b_val < 0 else 0
            a_code = (a_sign << 3) | SIGMA[abs(a_val)]
            b_code = (b_sign << 3) | SIGMA[abs(b_val)]
            qi9 = fp4_product_qi9(a_val, b_val)
            bits = qi9_to_bits(qi9)
            idx = (a_code << 4) | b_code
            for i in range(9):
                funcs[i][idx] = bits[i]
    return funcs


def compute_anf(f):
    """Compute the algebraic normal form of f : {0,1}^8 -> {0,1}.
    Returns the set of monomials (each monomial is a frozenset of var indices,
    where vars 0..7 correspond to bits a0,a1,a2,a3,b0,b1,b2,b3 within the
    8-bit input index)."""
    n = 8
    N = 1 << n  # 256
    coeffs = list(f)  # mutable copy
    # Mobius transform: c'_S = XOR_{T subset of S} c_T
    for i in range(n):
        for j in range(N):
            if j & (1 << i):
                coeffs[j] ^= coeffs[j ^ (1 << i)]
    monomials = set()
    for mask in range(N):
        if coeffs[mask]:
            mono = frozenset(i for i in range(n) if mask & (1 << i))
            monomials.add(mono)
    return monomials


def degree(monomials):
    if not monomials:
        return -1
    return max(len(m) for m in monomials)


def multiplicative_complexity_lb(monomials):
    """Lower bound: deg(f) - 1 for f not constant or affine.
    For affine f (deg <= 1), c(f) = 0."""
    d = degree(monomials)
    return max(0, d - 1)


def main():
    funcs = build_funcs_under_sigma()
    anfs = [compute_anf(f) for f in funcs]

    print("# Lower-bound report: FP4xFP4 -> 9-bit multiplier (Longhorn sigma)\n")
    print("## Per-output statistics\n")
    print("| bit | ones | degree | #monomials | mc-lb (=deg-1) |")
    print("|----:|----:|-------:|-----------:|---------------:|")
    deg_lb_total = 0
    mono_union = set()
    for i, (f, mono) in enumerate(zip(funcs, anfs)):
        d = degree(mono)
        nm = len(mono)
        mc = multiplicative_complexity_lb(mono)
        deg_lb_total += mc
        mono_union |= mono
        print(f"|  y{i} | {sum(f)} | {d} | {nm} | {mc} |")

    print()
    print(f"**Sum of per-bit AND lower bounds (no sharing):** {deg_lb_total}")
    print(f"**Distinct monomials across all 9 outputs (max sharing):** {len(mono_union)}")
    print()

    # Count monomials by degree across all outputs
    deg_dist = Counter()
    for mono in mono_union:
        deg_dist[len(mono)] += 1
    print("**Distinct-monomial degree distribution (union over outputs):**\n")
    for d in sorted(deg_dist):
        print(f"- degree {d}: {deg_dist[d]} distinct monomials")
    print()

    # AND-gate lower bound from monomial structure
    # A monomial of degree d requires d-1 AND gates to evaluate (for d>=1).
    # If we share completely: total ANDs >= sum_{m in union} max(0, |m|-1)
    and_lb_shared = sum(max(0, len(m) - 1) for m in mono_union)
    # XOR lower bound: each output is a XOR over its monomials.
    # f_i has m_i monomials -> needs m_i - 1 XORs (for m_i >= 1).
    xor_lb = sum(max(0, len(mono) - 1) for mono in anfs)
    print(f"**AND-gate lower bound assuming *maximum* product sharing:** {and_lb_shared}")
    print(f"**XOR-gate lower bound (each output = XOR of its monomials):** {xor_lb}")
    print()
    print(f"**Naive total lower bound (AND_shared + XOR + outputs):** {and_lb_shared + xor_lb}")
    print()
    print("## Comparison to current best\n")
    print("- Our 63-gate solution: 24 AND2 + 12 OR2 + 22 XOR2 + 5 NOT1.")
    print(f"- AND2 count vs lower bound (max sharing): 24 vs {and_lb_shared}.")
    print(f"- XOR2 count vs per-output lower bound:    22 vs {xor_lb}.")
    print()
    print("These bounds assume the basis {AND, XOR, NOT}. OR2 in our basis is")
    print("equivalent to XOR + AND + XOR or NOT(AND(NOT,NOT)) - i.e., OR adds")
    print("no logical primitive. So an AND-XOR-NOT lower bound is also a")
    print("lower bound for our basis {AND2, OR2, XOR2, NOT1}.")
    print()
    print("Note: monomial-sharing lower bound is the *naive* one. Tighter")
    print("multiplicative-complexity bounds (Boyar/Peralta gate elimination,")
    print("communication-complexity-based) may move the bound higher.")


if __name__ == "__main__":
    main()
