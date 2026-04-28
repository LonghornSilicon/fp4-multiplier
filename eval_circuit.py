"""
Standalone gate counter and verifier for FP4 multiplier circuits.

Usage:
    from eval_circuit import evaluate
    result = evaluate(write_your_multiplier_here, INPUT_REMAP)
    print(result)  # {'correct': True, 'gate_count': 42, 'errors': []}

Gate counting works by monkey-patching NOT/AND/OR/XOR to count calls.
The count is the TRUE gate count (each call = 1 gate regardless of sharing).

Note: Python short-circuit evaluation in 'and'/'or' doesn't apply here since
we use function calls. This gives an honest gate count.
"""

import numpy as np
from typing import Callable, Dict, Any

try:
    import ml_dtypes
    from ml_dtypes import uint4, float4_e2m1fn
    from numpy import float32
    HAS_MLDTYPES = True
except ImportError:
    HAS_MLDTYPES = False
    print("Warning: ml_dtypes not available. Install with: pip install ml-dtypes==0.5.1")

# ── Default FP4 encoding (identity remapping) ────────────────────────────────
DEFAULT_REMAP = None  # filled lazily after import check


def _make_default_remap():
    if not HAS_MLDTYPES:
        return {}
    return {
        float4_e2m1fn(0):    uint4(0b0000),
        float4_e2m1fn(0.5):  uint4(0b0001),
        float4_e2m1fn(1):    uint4(0b0010),
        float4_e2m1fn(1.5):  uint4(0b0011),
        float4_e2m1fn(2):    uint4(0b0100),
        float4_e2m1fn(3):    uint4(0b0101),
        float4_e2m1fn(4):    uint4(0b0110),
        float4_e2m1fn(6):    uint4(0b0111),
        float4_e2m1fn(-0.0): uint4(0b0000),
        float4_e2m1fn(-0.5): uint4(0b1001),
        float4_e2m1fn(-1):   uint4(0b1010),
        float4_e2m1fn(-1.5): uint4(0b1011),
        float4_e2m1fn(-2):   uint4(0b1100),
        float4_e2m1fn(-3):   uint4(0b1101),
        float4_e2m1fn(-4):   uint4(0b1110),
        float4_e2m1fn(-6):   uint4(0b1111),
    }


# ── Gate-counting context ─────────────────────────────────────────────────────

class GateCounter:
    """Context manager that injects gate-counting wrappers."""

    def __init__(self):
        self.count = 0

    def NOT(self, x):
        self.count += 1
        return not x

    def AND(self, x, y):
        self.count += 1
        return x & y

    def OR(self, x, y):
        self.count += 1
        return x | y

    def XOR(self, x, y):
        self.count += 1
        return x ^ y

    def reset(self):
        self.count = 0


# ── Core evaluator ────────────────────────────────────────────────────────────

def evaluate(multiplier_fn: Callable, input_remap: Dict = None,
             verbose: bool = False) -> Dict[str, Any]:
    """
    Evaluate a multiplier circuit on all 256 FP4×FP4 input pairs.

    Args:
        multiplier_fn: function(a0,a1,a2,a3, b0,b1,b2,b3) -> tuple of 9 bits
                       Should use GC.NOT/AND/OR/XOR passed as globals, OR
                       accept a gate_counter keyword argument.
        input_remap:   dict mapping float4_e2m1fn -> uint4 (default = identity)
        verbose:       print errors

    Returns:
        {
            'correct': bool,
            'gate_count': int,   # total gates over ALL 256 pairs (worst-case counting)
            'gate_count_single': int,  # gates for one typical (non-trivial) input pair
            'errors': list of (a_fp4, b_fp4, expected, actual)
        }

    Gate counting strategy:
        We count gates across all 256 evaluations then report the MAX per-pair count
        as the "single evaluation" cost (since all evaluations of the same circuit
        with different inputs hit the same structure - Python functions don't branch
        based on data, only on control flow).
    """
    if not HAS_MLDTYPES:
        raise RuntimeError("ml_dtypes required for evaluation")

    if input_remap is None:
        global DEFAULT_REMAP
        if DEFAULT_REMAP is None:
            DEFAULT_REMAP = _make_default_remap()
        input_remap = DEFAULT_REMAP

    gc = GateCounter()
    errors = []
    per_pair_counts = []

    for a_raw in range(16):
        for b_raw in range(16):
            a_fp4 = uint4(a_raw).view(float4_e2m1fn)
            b_fp4 = uint4(b_raw).view(float4_e2m1fn)

            # Expected result
            expected_fp32 = a_fp4.astype(float32) * b_fp4.astype(float32)
            expected_qi9 = np.int16(np.round(expected_fp32 * 4))

            # Remapped inputs
            a_remapped = int(input_remap[a_fp4].view(uint4))
            b_remapped = int(input_remap[b_fp4].view(uint4))
            a_bits = [(a_remapped >> (3 - i)) & 1 for i in range(4)]
            b_bits = [(b_remapped >> (3 - i)) & 1 for i in range(4)]

            # Run with gate counting
            gc.reset()
            result_bits = multiplier_fn(*a_bits, *b_bits,
                                        NOT=gc.NOT, AND=gc.AND,
                                        OR=gc.OR, XOR=gc.XOR)
            per_pair_counts.append(gc.count)

            # Decode result
            actual_uint = np.uint16(sum(int(bool(b)) << (8 - i)
                                        for i, b in enumerate(result_bits)))
            if result_bits[0]:
                actual_uint += np.uint16(0b1111111000000000)
            actual_qi9 = actual_uint.view(np.int16)

            if actual_qi9 != expected_qi9:
                errors.append((float(a_fp4), float(b_fp4), int(expected_qi9), int(actual_qi9)))
                if verbose:
                    print(f"  ERROR: {float(a_fp4)} × {float(b_fp4)} = "
                          f"expected {int(expected_qi9)}, got {int(actual_qi9)}")

    # Gate count: max over all pairs (the circuit's worst-case gate activation)
    # For a pure combinational circuit with no data-dependent branching, this
    # equals the true structural gate count.
    gate_count = max(per_pair_counts) if per_pair_counts else 0
    min_gates = min(per_pair_counts) if per_pair_counts else 0

    return {
        'correct': len(errors) == 0,
        'gate_count': gate_count,
        'gate_count_min': min_gates,
        'gate_count_total': sum(per_pair_counts),
        'errors': errors,
        'num_errors': len(errors),
    }


def evaluate_from_module(module_path: str, verbose: bool = True) -> Dict[str, Any]:
    """Load a multiplier module by path and evaluate it."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("multiplier_mod", module_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    fn = getattr(mod, 'write_your_multiplier_here')
    remap = getattr(mod, 'INPUT_REMAP', None)
    if isinstance(remap, (list, tuple)):
        correct, gc, errors = evaluate_fast(fn, remap, verbose=verbose)
        return {'correct': correct, 'gate_count': gc, 'gate_count_min': gc,
                'gate_count_total': gc * 256, 'errors': errors, 'num_errors': len(errors)}
    result = evaluate(fn, remap, verbose=verbose)
    return result


# ── Alternative: static gate count (no execution) ────────────────────────────

def count_gates_static(source_code: str) -> int:
    """
    Count gate function calls in source code via AST analysis.
    This gives the structural gate count (independent of input values).
    Does NOT verify correctness.
    """
    import ast

    class GateCallCounter(ast.NodeVisitor):
        def __init__(self):
            self.count = 0
        def visit_Call(self, node):
            if isinstance(node.func, ast.Name) and node.func.id in ('NOT', 'AND', 'OR', 'XOR'):
                self.count += 1
            self.generic_visit(node)

    tree = ast.parse(source_code)
    counter = GateCallCounter()
    counter.visit(tree)
    return counter.count


# ── Build int-based truth table (fast evaluation without ml_dtypes) ──────────

# FP4 value table: index 0..15 -> float
FP4_TABLE = [0.0, 0.5, 1.0, 1.5, 2.0, 3.0, 4.0, 6.0,
             0.0, -0.5, -1.0, -1.5, -2.0, -3.0, -4.0, -6.0]


def build_expected_table(input_remap_dict=None):
    """
    Build expected output table as dict: (remapped_a4bit, remapped_b4bit) -> qi9_int
    Uses raw integers (no ml_dtypes) for speed.

    input_remap_dict can be:
      - None: identity mapping
      - list of 16 ints: index -> new 4-bit code
      - dict mapping float4_e2m1fn -> uint4 (ml_dtypes format)
    """
    if input_remap_dict is None:
        remap = list(range(16))
    elif isinstance(input_remap_dict, (list, tuple)):
        remap = list(input_remap_dict)
    else:
        if HAS_MLDTYPES:
            remap = [0] * 16
            for fp4_val, uint4_code in input_remap_dict.items():
                orig_idx = int(fp4_val.view(uint4))
                remap[orig_idx] = int(uint4_code.view(uint4))
        else:
            remap = list(range(16))

    table = {}
    for a_orig in range(16):
        for b_orig in range(16):
            a_val = FP4_TABLE[a_orig]
            b_val = FP4_TABLE[b_orig]
            qi9 = int(round(a_val * b_val * 4))
            assert -256 <= qi9 <= 255
            qi9_masked = qi9 & 0x1FF  # 9-bit two's complement
            a_code = remap[a_orig]
            b_code = remap[b_orig]
            table[(a_code, b_code)] = qi9_masked
    return table


def evaluate_fast(multiplier_fn: Callable, input_remap_dict=None,
                  verbose: bool = False):
    """
    Fast integer-only evaluation. Returns (correct, gate_count_max).
    Uses Python int bits instead of ml_dtypes.
    """
    expected = build_expected_table(input_remap_dict)

    if input_remap_dict is None:
        remap = list(range(16))
    elif isinstance(input_remap_dict, (list, tuple)):
        remap = list(input_remap_dict)
    elif HAS_MLDTYPES:
        remap = [0] * 16
        for fp4_val, uint4_code in input_remap_dict.items():
            orig_idx = int(fp4_val.view(uint4))
            remap[orig_idx] = int(uint4_code.view(uint4))
    else:
        remap = list(range(16))

    gc = GateCounter()
    errors = []
    per_pair_counts = []

    for a_orig in range(16):
        for b_orig in range(16):
            a_code = remap[a_orig]
            b_code = remap[b_orig]
            a_bits = [(a_code >> (3 - i)) & 1 for i in range(4)]
            b_bits = [(b_code >> (3 - i)) & 1 for i in range(4)]

            gc.reset()
            result_bits = multiplier_fn(*a_bits, *b_bits,
                                        NOT=gc.NOT, AND=gc.AND,
                                        OR=gc.OR, XOR=gc.XOR)
            per_pair_counts.append(gc.count)

            # Decode 9-bit two's complement
            actual = sum(int(bool(b)) << (8 - i) for i, b in enumerate(result_bits))
            if result_bits[0]:  # sign extension
                actual = actual | 0xFFFFFE00
                actual = actual - 0x100000000  # to signed
            actual &= 0x1FF

            exp = expected[(a_code, b_code)]
            if actual != exp:
                errors.append((a_orig, b_orig, exp, actual))
                if verbose:
                    print(f"  ERROR: {FP4_TABLE[a_orig]}×{FP4_TABLE[b_orig]} "
                          f"expected={exp} got={actual}")

    return len(errors) == 0, max(per_pair_counts) if per_pair_counts else 0, errors


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python eval_circuit.py <multiplier_module.py>")
        print("       python eval_circuit.py --self-test")
        sys.exit(1)

    if sys.argv[1] == "--self-test":
        # Test with a trivially wrong circuit
        def dummy_multiplier(a0, a1, a2, a3, b0, b1, b2, b3,
                             NOT, AND, OR, XOR):
            s = XOR(a0, b0)
            return (s, False, False, False, False, False, False, False, False)

        correct, gc, errs = evaluate_fast(dummy_multiplier, verbose=False)
        print(f"Self-test dummy circuit: correct={correct}, gate_count={gc}, errors={len(errs)}")
        assert not correct, "Dummy circuit should be wrong"
        assert gc == 1, f"Dummy circuit should use 1 gate, got {gc}"
        print("Self-test passed.")
    else:
        result = evaluate_from_module(sys.argv[1], verbose=True)
        status = "CORRECT" if result['correct'] else f"WRONG ({result['num_errors']} errors)"
        print(f"\nResult: {status}")
        print(f"Gates:  {result['gate_count']} (max per pair)")
        if result['errors']:
            print("First 5 errors:")
            for err in result['errors'][:5]:
                print(f"  {err[0]} × {err[1]}: expected {err[2]}, got {err[3]}")
