"""Strategy file — the autoresearch agent edits this to propose new candidate
   remaps and ABC scripts. Each call to `propose()` returns a list of
   (name, values, abc_script) tuples to evaluate.

   `values`: list[16] of float (one entry per 4-bit code, in 0..15 order).
   `abc_script`: a string of ABC commands; pass None to use the search-driver
                  default script.
"""
from __future__ import annotations
from typing import Iterable

from fp4_spec import DEFAULT_FP4_VALUES
from remap import encoding_from_magnitude_perm, MAGNITUDES


def propose() -> Iterable[tuple[str, list[float], str | None]]:
    out = []

    # 1. Default encoding (sign MSB, magnitudes in numeric order).
    out.append(("default", DEFAULT_FP4_VALUES, None))

    # 2. Magnitudes in REVERSE numeric order on the s=0 region (and same on s=1).
    rev_perm = (7, 6, 5, 4, 3, 2, 1, 0)
    out.append(("rev_magnitude", encoding_from_magnitude_perm(rev_perm), None))

    # 3. Gray-code-ish: 0, 0.5, 1.5, 1, 3, 2, 6, 4 — adjacent codes differ by
    #    a single magnitude "step" in the FP4 magnitude lattice. Hypothesis:
    #    consecutive Gray indices share more output bits, helping ABC.
    gray_perm = (0, 1, 3, 2, 6, 7, 5, 4)  # 8-element Gray code over magnitude indices
    out.append(("gray_magnitude",
                encoding_from_magnitude_perm(gray_perm), None))

    # 4. "Doubled" — encode as if the 3 magnitude bits are the 3 high bits of
    #    the magnitude × 2: 0/2, 1/2, 2/2, 3/2, 4/2, 6/2, 8/2, 12/2 are
    #    {0, 0.5, 1, 1.5, 2, 3, 4, 6} = MAGNITUDES — same as default, but the
    #    cross-product `4·a·b` lines up with the 3-bit-pair lookup. This is
    #    just default; included as sanity.

    # 5. "Half-int low" — put half-integers (0.5, 1.5, 3 = m=1 family ... wait
    #    3 is integer) at low indices, integers at high indices. The Y[0]=1
    #    case requires both inputs to be in {0.5, 1.5}; isolating this in low
    #    bits might let Y[0] become 1 AND.
    # Magnitudes that produce odd 4*a*b when multiplied: {0.5, 1.5}. Put them
    # at indices 1, 3 (so bit 0 = 1 means "in {0.5, 1.5}").
    #   index 0 -> 0
    #   index 1 -> 0.5
    #   index 2 -> 1
    #   index 3 -> 1.5
    #   index 4 -> 2
    #   index 5 -> 3
    #   index 6 -> 4
    #   index 7 -> 6
    # That's actually the default! Default already puts {0.5, 1.5} at odd
    # indices. So default is already optimal w.r.t. Y[0]=1 single-bit detection.

    # 6. Reorder so "magnitude is integer-power-of-2-times-1" (i.e., {1, 2, 4})
    #    is at the high index bits. Hypothesis: high-shift magnitudes are
    #    "left-shift this value" in the multiplier; clean separation can simplify.
    # Order:  0, 0.5, 1.5, 3, 1, 2, 4, 6 — half-ints first, then int-pow-of-2.
    # (Hand-picked exploratory.)
    perm6 = tuple(MAGNITUDES.index(x) for x in [0, 0.5, 1.5, 3, 1, 2, 4, 6])
    out.append(("halfints_then_pow2",
                encoding_from_magnitude_perm(perm6), None))

    return out
