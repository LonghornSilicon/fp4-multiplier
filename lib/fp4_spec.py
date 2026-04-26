"""FP4 multiplier — specification, ground-truth function, truth-table enumeration.

Maps the Etched MX-FP4 (E2M1, no inf/NaN, signed-zero ignored, scale ignored)
take-home challenge into a single source of truth that downstream synthesis /
search code can import.
"""
from __future__ import annotations

from typing import Iterable

# Default FP4 encoding (4-bit code -> rational value).
# The spec lists 0000=0 and 1000=0; we keep both zeros so the enumeration
# covers all 16 codepoints.
DEFAULT_FP4_VALUES: list[float] = [
    0.0,    # 0000
    0.5,    # 0001
    1.0,    # 0010
    1.5,    # 0011
    2.0,    # 0100
    3.0,    # 0101
    4.0,    # 0110
    6.0,    # 0111
    0.0,    # 1000  (signed zero)
    -0.5,   # 1001
    -1.0,   # 1010
    -1.5,   # 1011
    -2.0,   # 1100
    -3.0,   # 1101
    -4.0,   # 1110
    -6.0,   # 1111
]

# The full multiset of values (with 0 appearing twice).
FP4_MULTISET: list[float] = list(DEFAULT_FP4_VALUES)


def qi9_encode(four_x_product: float) -> int:
    """Encode 4*val_a*val_b (must be an integer in [-256, 255]) as a 9-bit
    two's-complement bit pattern returned as an int in [0, 511]."""
    iv = int(four_x_product)
    assert iv == four_x_product, f"non-integer QI9 input {four_x_product}"
    assert -256 <= iv <= 255, f"QI9 overflow {iv}"
    return iv & 0x1FF


def reference_truth_table(values: list[float] = DEFAULT_FP4_VALUES) -> list[int]:
    """Return tt[a*16 + b] = 9-bit QI9 encoding of 4 * values[a] * values[b].

    `values` is the list of value at each 4-bit code. Default is the spec
    encoding; pass a permutation here to model an input remap.
    """
    tt = [0] * 256
    for a in range(16):
        for b in range(16):
            tt[a * 16 + b] = qi9_encode(4.0 * values[a] * values[b])
    return tt


def per_output_bit_truth_tables(values: list[float] = DEFAULT_FP4_VALUES) -> list[int]:
    """For each of the 9 output bits, return a 256-bit truth table packed as a
    Python int (bit i of the result corresponds to input pattern i = a*16+b).
    Returns a list of 9 ints.
    """
    tt = reference_truth_table(values)
    out = [0] * 9
    for i, y in enumerate(tt):
        for k in range(9):
            if (y >> k) & 1:
                out[k] |= (1 << i)
    return out


# --- Helper: derived per-bit decompositions (useful for analysis / reporting)


def y_bit_for_inputs(a_bits: int, b_bits: int, k: int,
                     values: list[float] = DEFAULT_FP4_VALUES) -> int:
    """Compute output bit Y_k for a specific 4-bit input pair (a_bits, b_bits)."""
    y = qi9_encode(4.0 * values[a_bits] * values[b_bits])
    return (y >> k) & 1


def is_remap(perm: Iterable[int]) -> bool:
    """A remap is any 16-permutation of the 4-bit codes -> codes; the values
    list passed downstream is values[i] = DEFAULT_FP4_VALUES[perm[i]]."""
    perm = list(perm)
    return len(perm) == 16 and sorted(perm) == list(range(16))


def remap_values(perm: list[int]) -> list[float]:
    """Apply a remap. After remap, the bit pattern `i` decodes to the value
    that the bit pattern `perm[i]` decodes to under the default encoding."""
    assert is_remap(perm), "perm must be a permutation of 0..15"
    return [DEFAULT_FP4_VALUES[perm[i]] for i in range(16)]


# --- Sanity checks ------------------------------------------------------------

def _self_test() -> None:
    # Spec example 1: 0001 (0.5) * 0001 (0.5) = 0.25; 4*0.25 = 1 -> 000000001
    assert qi9_encode(4 * 0.5 * 0.5) == 0b000000001 == 1

    # NOTE: Spec example 2 in the take-home doc has TWO typos.
    #   - "-3 represented in FP4 binary as 0001" — actually 0001 is +0.5; -3 is 1101.
    #   - "your circuit should output ... 110111000" for -3 * 1.5 = -4.5 ; 4*-4.5 = -18.
    # The 9-bit two's-complement of -18 is 111101110, not 110111000 (which is -72).
    # Sanity check: under any interpretation that gives -72 here, max(|output|) for
    # the FP4*FP4 grid = 16*36 = 576 > 255 = max 9-bit unsigned, so it cannot fit
    # in 9 bits. Therefore the integer interpretation MUST be int = 4*val_a*val_b,
    # and example 2 is a typo. We assert the correct value.
    assert qi9_encode(4 * -3.0 * 1.5) == 0b111101110, "QI9 encode wrong for -18"

    # Verify all 256 outputs fit in 9-bit signed integer range [-256, 255]
    for a in DEFAULT_FP4_VALUES:
        for b in DEFAULT_FP4_VALUES:
            v = 4 * a * b
            assert -256 <= int(v) <= 255 and int(v) == v

    # Output magnitudes set (non-negative integer outputs)
    mags = sorted({abs(int(4 * a * b)) for a in DEFAULT_FP4_VALUES for b in DEFAULT_FP4_VALUES})
    assert mags == [0, 1, 2, 3, 4, 6, 8, 9, 12, 16, 18, 24, 32, 36, 48, 64, 72, 96, 144]
    # Identity remap returns default
    assert remap_values(list(range(16))) == DEFAULT_FP4_VALUES
    print("OK fp4_spec self-test")


if __name__ == "__main__":
    _self_test()
    tts = per_output_bit_truth_tables()
    for k, t in enumerate(tts):
        ones = bin(t).count("1")
        print(f"Y[{k}]: {ones:3d} ones / 256")
