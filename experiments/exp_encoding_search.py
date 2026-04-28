"""
Encoding search harness for FP4×FP4 → QI9 multiplier.

Goal
----
Find *input encodings* (a bijection from the 16 FP4 values to 16 4-bit codes)
that make the overall 8→9 Boolean function easier to synthesize in the
{NOT, AND, OR, XOR} cost model (each costs 1 gate).

This script does NOT synthesize circuits by itself. It produces a ranked list
of encodings using fast, XOR-aware structural heuristics, intended to feed
downstream exact/heuristic synthesis (SAT/SMT or evolutionary search).

Run (WSL or Windows)
-------------------
  python experiments/exp_encoding_search.py --samples 20000 --keep 50 --seed 0

Key idea
--------
Given an encoding (remap list of 16 ints), we can build the full truth table
of the 8-bit *remapped* input (a_code||b_code) -> 9-bit QI9 output, then score:
  - ANF size per output bit (XOR-friendliness)
  - sharing of ANF monomials across outputs (multi-output XOR sharing potential)
  - cheap baseline stats (ones-count balance, etc.)
"""

from __future__ import annotations

import argparse
import heapq
import random
import sys
import os
from dataclasses import dataclass
from typing import Dict, Iterable, List, Tuple

# Make repo root importable when running from experiments/
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from eval_circuit import FP4_TABLE, build_expected_table


# ----------------------------- ANF utilities -----------------------------

def _mobius_anf_coeffs_256(tt_bits: List[int]) -> List[int]:
    """
    Compute ANF coefficients for an 8-input boolean function given as a length-256
    truth table (standard lexicographic order over 8-bit input index).

    Returns list 'a' length 256, where a[m]==1 means monomial for mask m appears.
    """
    a = tt_bits[:]  # in-place transform
    n = 8
    for i in range(n):
        step = 1 << i
        for base in range(0, 256, 2 * step):
            for k in range(step):
                a[base + k + step] ^= a[base + k]
    return a


def _anf_term_degree(mask: int) -> int:
    return mask.bit_count()


@dataclass(frozen=True)
class EncodingScore:
    # Primary
    anf_terms_total: int
    anf_terms_weighted: int
    shared_terms: int
    shared_term_savings_upper_bound: int

    # Secondary diagnostics
    max_terms_single_bit: int
    min_terms_single_bit: int

    def key(self) -> Tuple[int, int, int, int]:
        """
        Sorting key (smaller is better).
        - Weighted ANF term count is a proxy for AND-cost (higher-degree terms hurt).
        - Total terms is a proxy for XOR-cost.
        - Shared terms is a proxy for multi-output sharing opportunity (more is better),
          so we negate it in key.
        """
        return (
            self.anf_terms_weighted,
            self.anf_terms_total,
            -self.shared_terms,
            -self.shared_term_savings_upper_bound,
        )


def score_encoding(remap: List[int]) -> Tuple[EncodingScore, Dict[int, List[int]]]:
    """
    Compute a XOR-aware score for an encoding.

    Returns:
      (score, anf_by_outbit)
    where anf_by_outbit[bit] is a list of monomial masks present in that output.
    """
    # expected[(a_code, b_code)] = qi9_9bit_twos_complement (masked 0..511)
    expected = build_expected_table(remap)

    # Build per-bit truth tables over 8-bit remapped input index = (a_code<<4)|b_code
    bit_tts = [[0] * 256 for _ in range(9)]
    for a_code in range(16):
        for b_code in range(16):
            out = expected[(a_code, b_code)]
            idx = (a_code << 4) | b_code
            for bit in range(9):
                bit_tts[bit][idx] = (out >> (8 - bit)) & 1

    anf_by_bit: Dict[int, List[int]] = {}
    term_to_bits: Dict[int, int] = {}  # monomial mask -> bitmask of outputs using it

    terms_total = 0
    terms_weighted = 0
    max_terms = 0
    min_terms = 10**9

    for bit in range(9):
        coeffs = _mobius_anf_coeffs_256(bit_tts[bit])
        terms = [m for m, c in enumerate(coeffs) if c]
        anf_by_bit[bit] = terms

        n_terms = len(terms)
        terms_total += n_terms
        max_terms = max(max_terms, n_terms)
        min_terms = min(min_terms, n_terms)

        # degree-weighted cost proxy: each monomial of degree d costs (d-1) ANDs to build
        # (assuming full sharing of sub-ANDs, which is optimistic, but useful for ranking).
        for m in terms:
            d = _anf_term_degree(m)
            if d >= 2:
                terms_weighted += (d - 1)

            prev = term_to_bits.get(m, 0)
            term_to_bits[m] = prev | (1 << bit)

    # Sharing: monomials that appear in multiple outputs
    shared_terms = 0
    shared_savings_ub = 0
    for m, bits_mask in term_to_bits.items():
        k = bits_mask.bit_count()
        if k >= 2:
            shared_terms += 1
            # Upper bound: if a monomial is built once and XORed into k outputs,
            # vs built separately per output, potential savings is (k-1) * cost(term_build).
            d = _anf_term_degree(m)
            build_cost = max(0, d - 1)  # ANDs only; XOR-combine still needed
            shared_savings_ub += (k - 1) * build_cost

    score = EncodingScore(
        anf_terms_total=terms_total,
        anf_terms_weighted=terms_weighted,
        shared_terms=shared_terms,
        shared_term_savings_upper_bound=shared_savings_ub,
        max_terms_single_bit=max_terms,
        min_terms_single_bit=min_terms if min_terms != 10**9 else 0,
    )
    return score, anf_by_bit


# ----------------------------- encoding generation -----------------------------

def random_bijection_16(rng: random.Random) -> List[int]:
    """Uniform random permutation of 0..15: remap[orig_code] = new_code."""
    arr = list(range(16))
    rng.shuffle(arr)
    return arr


def mutate_swap(remap: List[int], rng: random.Random, swaps: int = 1) -> List[int]:
    """Return a new remap with a few random swaps (keeps bijection)."""
    out = remap[:]
    for _ in range(swaps):
        i, j = rng.randrange(16), rng.randrange(16)
        out[i], out[j] = out[j], out[i]
    return out


def remap_to_dict_for_display(remap: List[int]) -> Dict[float, int]:
    """
    Pretty mapping by FP4 value (float) -> new 4-bit code.
    Note: FP4_TABLE includes both +0 and -0; Python float prints both as 0.0.
    We disambiguate by original index.
    """
    d: Dict[float, int] = {}
    for orig_idx, new_code in enumerate(remap):
        d[(orig_idx, FP4_TABLE[orig_idx])] = new_code  # type: ignore[assignment]
    return d  # type: ignore[return-value]


# ----------------------------- main search loop -----------------------------

@dataclass
class Candidate:
    score: EncodingScore
    remap: List[int]

    def sort_key(self):
        return self.score.key()


def search(
    samples: int,
    keep: int,
    seed: int,
    mode: str,
    mutate_swaps: int,
) -> List[Candidate]:
    rng = random.Random(seed)

    # keep best-K candidates using a max-heap of size K (store negative ordering)
    heap: List[Tuple[Tuple[int, int, int, int], int, Candidate]] = []
    uniq = 0

    if mode == "random":
        current = None
    else:
        current = random_bijection_16(rng)

    for t in range(samples):
        if mode == "random" or current is None:
            remap = random_bijection_16(rng)
        else:
            # random-walk / hillclimb-ish: mutate around current
            remap = mutate_swap(current, rng, swaps=mutate_swaps)

        score, _ = score_encoding(remap)
        cand = Candidate(score=score, remap=remap)

        key = cand.sort_key()
        uniq += 1
        inv_key = tuple(-x for x in key)  # max-heap by inverted key

        if len(heap) < keep:
            heapq.heappush(heap, (inv_key, uniq, cand))
        else:
            worst_inv_key, _, _ = heap[0]
            if inv_key > worst_inv_key:
                heapq.heapreplace(heap, (inv_key, uniq, cand))

        # update current occasionally toward best seen (very light hillclimb)
        if mode != "random" and (t % 200 == 0) and heap:
            # pick best (smallest key) among heap
            best = min((h[2] for h in heap), key=lambda c: c.sort_key())
            current = best.remap

        if (t + 1) % max(1, samples // 10) == 0:
            best = min((h[2] for h in heap), key=lambda c: c.sort_key())
            print(
                f"[{t+1:>8d}/{samples}] best_key={best.sort_key()} "
                f"(weighted={best.score.anf_terms_weighted}, total={best.score.anf_terms_total}, shared={best.score.shared_terms})"
            )

    out = [h[2] for h in heap]
    out.sort(key=lambda c: c.sort_key())
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--samples", type=int, default=20000)
    ap.add_argument("--keep", type=int, default=50)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--mode", choices=["random", "walk"], default="walk")
    ap.add_argument("--mutate-swaps", type=int, default=2)
    args = ap.parse_args()

    best = search(
        samples=args.samples,
        keep=args.keep,
        seed=args.seed,
        mode=args.mode,
        mutate_swaps=args.mutate_swaps,
    )

    print("\n=== TOP CANDIDATES ===")
    for i, c in enumerate(best[: min(10, len(best))]):
        print(
            f"#{i:02d} key={c.sort_key()} "
            f"weighted={c.score.anf_terms_weighted} total={c.score.anf_terms_total} "
            f"shared={c.score.shared_terms} shareUB={c.score.shared_term_savings_upper_bound}"
        )
        print(f"  remap(list-of-16 orig->new): {c.remap}")
        # Show as (orig_idx,value)->code pairs (disambiguates ±0)
        pairs = [(orig_idx, FP4_TABLE[orig_idx], c.remap[orig_idx]) for orig_idx in range(16)]
        print(f"  mapping(orig_idx,val)->code: {pairs}")


if __name__ == "__main__":
    main()

