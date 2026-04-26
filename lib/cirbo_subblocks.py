"""Cirbo exact synthesis on isolated sub-blocks of the FP4 multiplier.

Sub-blocks (smaller = more tractable for SAT):
  (1) 2x2 unsigned multiplier: 4-input × 4-output (16 minterms)
  (2) K computation: 4-input × 3-output (16 minterms)
  (3) K-shift: 7-input × 8-output (128 minterms) — combines P (4-bit) and K (3-bit)
"""
from __future__ import annotations
import sys, time

from cirbo.core.truth_table import TruthTableModel
from cirbo.synthesis.circuit_search import CircuitFinderSat, Operation

OUR_BASIS = [Operation.and_, Operation.or_, Operation.xor_, Operation.lnot_]


def find_min(table: list[list[bool]], max_n: int = 30, time_budget: int = 60,
             label: str = ""):
    model = TruthTableModel(table)
    print(f"\n=== {label} ===", flush=True)
    print(f"Inputs: {len(table[0]).bit_length()-1}, outputs: {len(table)}", flush=True)
    print(f"{'G':>4}  {'result':>10}  {'wall':>6}", flush=True)
    last_unsat = None
    for n in range(0, max_n + 1):
        if n == 0:
            const_check = all(b == table[0][0] for row in table for b in row)
            if const_check: print(f"  G=0: const, exit"); return 0
            continue
        finder = CircuitFinderSat(boolean_function_model=model,
                                  number_of_gates=n, basis=OUR_BASIS)
        t0 = time.time()
        try:
            finder.find_circuit(time_limit=time_budget)
            wall = time.time() - t0
            print(f"  {n:>4}  {'SAT':>10}  {wall:>6.1f}s", flush=True)
            return n
        except Exception as e:
            wall = time.time() - t0
            ename = type(e).__name__
            if "NoSolution" in ename:
                print(f"  {n:>4}  {'UNSAT':>10}  {wall:>6.1f}s", flush=True)
                last_unsat = n
            elif "TimeOut" in ename or "Timeout" in ename:
                print(f"  {n:>4}  {'TIMEOUT':>10}  {wall:>6.1f}s", flush=True)
                return None
            else:
                print(f"  {n:>4}  ERROR {ename}: {e}", flush=True)
                return None


# ---- Sub-block 1: 2x2 multiplier ----
# Inputs: M_a[1] M_a[0] M_b[1] M_b[0]   (M ∈ {0..3})
# Outputs: P[3] P[2] P[1] P[0]           (P ∈ {0..9})
# Minterm indexing: idx = (M_a[1]<<3) | (M_a[0]<<2) | (M_b[1]<<1) | M_b[0]
def build_2x2_mul_table():
    out = [[False] * 16 for _ in range(4)]
    for ma1 in range(2):
        for ma0 in range(2):
            for mb1 in range(2):
                for mb0 in range(2):
                    Ma = ma1 * 2 + ma0
                    Mb = mb1 * 2 + mb0
                    P = Ma * Mb
                    idx = ma1 * 8 + ma0 * 4 + mb1 * 2 + mb0
                    for k in range(4):
                        out[k][idx] = bool((P >> k) & 1)
    return out


# ---- Sub-block 2: K computation ----
# Inputs: eh_a el_a eh_b el_b
# Outputs: K[2] K[1] K[0]    K ∈ {0..4}
# K = sa1 + sb1, sa1 = eh*(1+el)
def build_K_table():
    out = [[False] * 16 for _ in range(3)]
    for eh_a in range(2):
        for el_a in range(2):
            for eh_b in range(2):
                for el_b in range(2):
                    sa1 = eh_a * (1 + el_a)
                    sb1 = eh_b * (1 + el_b)
                    K = sa1 + sb1
                    idx = eh_a * 8 + el_a * 4 + eh_b * 2 + el_b
                    for k in range(3):
                        out[k][idx] = bool((K >> k) & 1)
    return out


# ---- Sub-block 3: K-shift ----
# Inputs: K[2] K[1] K[0] P[3] P[2] P[1] P[0]   (7 inputs)
# Outputs: mag[7..0]                              (8 outputs)
def build_Kshift_table():
    out = [[False] * 128 for _ in range(8)]
    for idx in range(128):
        K2 = (idx >> 6) & 1
        K1 = (idx >> 5) & 1
        K0 = (idx >> 4) & 1
        K = K2 * 4 + K1 * 2 + K0
        if K > 4:
            continue   # don't-care, but truth-table init = 0
        P = idx & 0xF
        mag = (P << K) & 0xFF
        for k in range(8):
            out[k][idx] = bool((mag >> k) & 1)
    return out


def main():
    block = sys.argv[1] if len(sys.argv) > 1 else "all"
    if block in ("2x2", "all"):
        find_min(build_2x2_mul_table(), max_n=15, time_budget=60,
                 label="2x2 unsigned multiplier (4 inputs, 4 outputs)")
    if block in ("k", "all"):
        find_min(build_K_table(), max_n=15, time_budget=60,
                 label="K = sa1 + sb1 (4 inputs, 3 outputs)")
    if block in ("shift", "all"):
        find_min(build_Kshift_table(), max_n=50, time_budget=120,
                 label="K-shift P<<K (7 inputs, 8 outputs)")


if __name__ == "__main__":
    main()
