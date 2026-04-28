"""
Verify our 88-gate multiplier against the official test harness logic.
This replicates the verification loop from etched_take_home_multiplier_assignment.py
without the Colab-specific !pip magic.
"""
import numpy as np
from ml_dtypes import uint4, float4_e2m1fn
from numpy import float32

from autoresearch.multiplier import write_your_multiplier_here, INPUT_REMAP

# Build ml_dtypes-compatible remap from our int list
# INPUT_REMAP is a list of 16 ints: FP4_TABLE[i] → new 4-bit code
# The test harness expects: INPUT_REMAP[float4_e2m1fn(x)] = uint4(code)
from eval_circuit import FP4_TABLE

remap_dict = {}
for i in range(16):
    fp4_val = uint4(i).view(float4_e2m1fn)
    new_code = INPUT_REMAP[i]
    remap_dict[fp4_val] = uint4(new_code)

# Global gate functions (test harness style)
NOT = lambda x: not x
AND = lambda x, y: x & y
OR  = lambda x, y: x | y
XOR = lambda x, y: x ^ y

def multiplier_wrapped(a0, a1, a2, a3, b0, b1, b2, b3):
    return write_your_multiplier_here(a0, a1, a2, a3, b0, b1, b2, b3,
                                      NOT=NOT, AND=AND, OR=OR, XOR=XOR)

def fp4_to_list_of_bits(fp4: float4_e2m1fn):
    uint_value = int(fp4.view(uint4))
    return [(uint_value >> i) & 1 for i in reversed(range(4))]

errors = 0
for a in range(16):
    for b in range(16):
        a_fp4 = uint4(a).view(float4_e2m1fn)
        b_fp4 = uint4(b).view(float4_e2m1fn)

        expected_fp32 = a_fp4.astype(float32) * b_fp4.astype(float32)
        expected_qi9 = np.int16(np.round(expected_fp32 * 4))

        a_bits = fp4_to_list_of_bits(remap_dict[a_fp4])
        b_bits = fp4_to_list_of_bits(remap_dict[b_fp4])
        actual_result_bits = multiplier_wrapped(*a_bits, *b_bits)

        actual_result_qi9 = np.uint16(sum(bit << (8 - i) for i, bit in enumerate(actual_result_bits)))
        if actual_result_bits[0]:
            actual_result_qi9 += np.uint16(0b1111111000000000)
        actual_result_qi9 = actual_result_qi9.view(np.int16)

        if expected_qi9 != actual_result_qi9:
            print(f"ERROR: {float(a_fp4)} × {float(b_fp4)}: expected {int(expected_qi9)}, got {int(actual_result_qi9)}")
            errors += 1

if errors == 0:
    print(f"ALL 256 TESTS PASSED — 88-gate circuit is correct!")
else:
    print(f"FAILED: {errors} errors out of 256 tests")
