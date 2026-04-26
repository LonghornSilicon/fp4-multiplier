"""Use sympy.logic.SOPform / simplify_logic to minimize each Y[k] truth table.
Outputs gate counts under {AND, OR, NOT} (2-level SOP). For comparison with
our 74-gate multi-level result. Likely worse — multi-level beats 2-level for
structured circuits — but quick sanity check on whether the 2-level SOP for
any specific Y[k] reveals a structural insight ABC missed."""
from __future__ import annotations
from sympy import symbols
from sympy.logic import SOPform, simplify_logic
from sympy.logic.boolalg import And, Or, Not, Xor, BooleanFunction

from fp4_spec import per_output_bit_truth_tables
from remap import encoding_from_magnitude_perm


def count_gates(expr) -> dict:
    """Count primitive gates in a sympy Boolean expression. Returns dict."""
    counts = {"AND": 0, "OR": 0, "NOT": 0, "XOR": 0, "atomic": 0, "const": 0}
    def _walk(e):
        if e is None:
            return
        from sympy import Symbol
        if isinstance(e, Symbol):
            counts["atomic"] += 1
            return
        if isinstance(e, bool) or e is True or e is False:
            counts["const"] += 1
            return
        # Operators
        op = type(e).__name__
        if op == "And":
            counts["AND"] += len(e.args) - 1
        elif op == "Or":
            counts["OR"] += len(e.args) - 1
        elif op == "Not":
            counts["NOT"] += 1
        elif op == "Xor":
            counts["XOR"] += len(e.args) - 1
        # Recurse
        for a in e.args:
            _walk(a)
    _walk(expr)
    return counts


def minimize_one(tt_int: int, var_names: list[str]):
    """Run SOPform on a 256-bit truth table (indexed by minterm number)."""
    syms = symbols(" ".join(var_names))
    minterms = [i for i in range(256) if (tt_int >> i) & 1]
    sop = SOPform(syms, minterms)
    # Then simplify (Quine-McCluskey-ish)
    simp = simplify_logic(sop, force=True)
    return sop, simp


def main():
    # Use the best remap σ=(0,1,2,3,6,7,4,5)
    values = encoding_from_magnitude_perm((0, 1, 2, 3, 6, 7, 4, 5))
    tts = per_output_bit_truth_tables(values)
    # var_names: minterm i = a*16+b, where a = bits 7..4, b = bits 3..0
    # So bit 7 = a[3] (MSB of a), bit 0 = b[0]
    var_names = ["a3", "a2", "a1", "a0", "b3", "b2", "b1", "b0"]
    print(f"{'Y':>3} {'ones':>4} {'SOP_terms':>10} {'simp_str_len':>12}", flush=True)
    print("-" * 50)
    total_atomic = 0
    total_or_and = 0
    for k in range(9):
        try:
            sop, simp = minimize_one(tts[k], var_names)
            counts = count_gates(simp)
            simp_str = str(simp)
            print(f"  Y[{k}] {bin(tts[k]).count('1'):>3}    "
                  f"AND={counts['AND']:2d} OR={counts['OR']:2d} "
                  f"XOR={counts['XOR']:2d} NOT={counts['NOT']:2d}", flush=True)
            print(f"       expr: {simp_str[:120]}", flush=True)
            total_atomic += counts["AND"] + counts["OR"] + counts["XOR"] + counts["NOT"]
        except Exception as e:
            print(f"  Y[{k}] error: {type(e).__name__}: {e}", flush=True)
    print(f"\nTotal SOP-form gates (no sharing across outputs): {total_atomic}")


if __name__ == "__main__":
    main()
