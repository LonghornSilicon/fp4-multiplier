"""Remap helpers — enumerate the bijective input remaps we want to search.

The full bijection space is 16!/2 ≈ 1.05e13 (the /2 because the two zeros are
indistinguishable). Most of that is wasted on equivalence-class duplicates.
Useful sub-spaces:

- `sign_symmetric_remaps()` :: 8! permutations of {0, 0.5, 1, 1.5, 2, 3, 4, 6}
  applied identically to s=0 and s=1 halves; 40320 candidates.
- `random_remaps(n, seed)` :: uniform-random bijections (used as a smoke test
  to check whether non-sign-symmetric remaps can ever beat sign-symmetric).

Each remap is represented as a `values` list: `values[i]` is the float that
the 4-bit code `i` decodes to under that remap.
"""
from __future__ import annotations
import itertools
import random
from typing import Iterator

from fp4_spec import DEFAULT_FP4_VALUES, qi9_encode

# 8 magnitudes, in default numeric order.
MAGNITUDES = [0.0, 0.5, 1.0, 1.5, 2.0, 3.0, 4.0, 6.0]


def encoding_from_magnitude_perm(perm: tuple[int, ...]) -> list[float]:
    """Build a 16-entry `values` list from an 8-perm of MAGNITUDES indices.

    Resulting bijection:
      code  s xxx (s = bit 3, xxx = 3-bit magnitude code) decodes to
      sign(s) * MAGNITUDES[perm[xxx]].

    `perm` is an 8-tuple, a permutation of (0,1,2,3,4,5,6,7).
    Both zeros (perm value 0 in s=0 and s=1) decode to 0.0 (handled by float
    arithmetic).
    """
    assert sorted(perm) == list(range(8)), f"not an 8-perm: {perm}"
    values: list[float] = [0.0] * 16
    for code in range(16):
        s = (code >> 3) & 1
        x = code & 0b111
        mag = MAGNITUDES[perm[x]]
        values[code] = -mag if s == 1 else mag
    return values


def sign_symmetric_remaps() -> Iterator[tuple[tuple[int, ...], list[float]]]:
    """Yield (perm, values) pairs for all 40320 sign-symmetric remaps."""
    for perm in itertools.permutations(range(8)):
        yield perm, encoding_from_magnitude_perm(perm)


def random_remaps(n: int, seed: int = 0) -> Iterator[tuple[list[int], list[float]]]:
    """Yield (perm, values) pairs for n uniformly-random bijections."""
    rng = random.Random(seed)
    for _ in range(n):
        codes = list(range(16))
        rng.shuffle(codes)
        # codes[i] = which default-encoding code position i represents.
        values = [DEFAULT_FP4_VALUES[codes[i]] for i in range(16)]
        yield codes, values


def canonical_id(perm: tuple[int, ...]) -> tuple[int, ...]:
    """Return a canonical form for a sign-symmetric remap. Two remaps that
    produce the same multiplier function (modulo internal labeling) should
    map to the same canonical id; we use this for de-duplication.

    Symmetries we quotient out:
      - swapping the two values that map to magnitude 0 within the s=0 / s=1
        regions is irrelevant (both decode to 0 — but in our `perm`, magnitude 0
        appears only once per region by construction).
      - **NOTE**: sign-symmetric remaps don't have intra-region zero swaps; the
        only symmetry left is the multiplier's (a,b) symmetry, which is global
        and already handled at synthesis time.
    """
    return perm


def _self_test() -> None:
    # Default remap reproduces DEFAULT_FP4_VALUES.
    default_perm = tuple(range(8))
    v = encoding_from_magnitude_perm(default_perm)
    assert v == DEFAULT_FP4_VALUES, (v, DEFAULT_FP4_VALUES)
    # Count of sign-symmetric remaps
    n = sum(1 for _ in sign_symmetric_remaps())
    assert n == 40320, n
    print(f"OK remap.py self-test ({n} sign-symmetric remaps)")


if __name__ == "__main__":
    _self_test()
