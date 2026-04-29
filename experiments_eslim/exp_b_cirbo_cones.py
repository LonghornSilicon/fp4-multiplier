"""
Experiment B: Cirbo SAT exact synthesis on small sub-cones of the 64-gate
netlist.

Target sub-cones:
  B.1  not_65 cone:  {w_43, w_58, w_65} → {y0, w_69}, current 3 gates.
       Try G=2 (must be UNSAT — confirms 3 is exact).
       Try with EXTRA inputs (w_45, w_25, etc.) to see if richer input set
       enables a 2-gate realization that wasn't possible with just 3.
  B.2  K-flag NOT cone:  {w_45, w_55, w_65} → {not_45, not_55, not_65}.
       Currently 3 NOTs. SAT proves it's exactly 3 (you can't compute
       inversions of 3 distinct independent wires in fewer than 3 gates
       in the {AND,OR,XOR,NOT} basis, but worth the formal proof).
  B.3  output {y6, y7, y8} cone: small set of inputs from the back-end of
       the netlist. Look for shared structure.

Bit-parallel sim used to extract the 256-input truth tables for any wire
in the canonical netlist.
"""
from __future__ import annotations
import sys, os, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)) + "/..")

from triage.g1_g3_g4_64gate import simulate_64gate, ALL_ONE

try:
    from cirbo.core.truth_table import TruthTableModel
    from cirbo.synthesis.circuit_search import CircuitFinderSat, Operation
    HAS_CIRBO = True
    OUR_BASIS = [Operation.and_, Operation.or_, Operation.xor_, Operation.lnot_]
except ImportError as e:
    print(f"Warning: cirbo not available: {e}")
    HAS_CIRBO = False


def bv_to_truth_rows(input_bvs, target_bvs):
    """Convert (input_bvs, target_bvs) → row-major truth table for Cirbo.

    Cirbo's TruthTableModel expects a list-of-lists where row i corresponds
    to output bit i and each column is a minterm (input combination). Each
    row is length 2^n where n = number of inputs.

    We have 256-bit input/output bitvectors over the natural input pattern
    indexing (idx = a_orig * 16 + b_orig). With k input wires, the
    "minterm index" m for a row is the combined bits of the k inputs at
    pattern idx i. Multiple pattern-idx's that produce the same minterm
    must be consistent (otherwise the function isn't well-defined on the
    inputs alone — but we're checking that and treating duplicates as
    don't-cares aligned).
    """
    n = len(input_bvs)
    n_minterms = 1 << n
    # For each pattern (256 of them), compute minterm index m
    rows = [[None] * n_minterms for _ in target_bvs]
    seen_inputs = [None] * n_minterms
    for pat in range(256):
        m = 0
        for k in range(n):
            if (input_bvs[k] >> pat) & 1:
                m |= (1 << (n - 1 - k))
        for ti, tbv in enumerate(target_bvs):
            v = (tbv >> pat) & 1
            existing = rows[ti][m]
            if existing is None:
                rows[ti][m] = bool(v)
            elif existing != bool(v):
                # Inconsistent — function depends on inputs OUTSIDE this cone
                return None, f"target #{ti} differs at minterm {m}"
        # track which minterms we've seen (for don't-care handling)
        seen_inputs[m] = True
    # Fill don't-cares with False (Cirbo will accept a complete table)
    for r in rows:
        for m in range(n_minterms):
            if r[m] is None:
                r[m] = False
    return rows, None


def find_min(table, max_n=12, time_budget=60, label=""):
    if not HAS_CIRBO:
        print(f"  [{label}] cirbo unavailable, skip")
        return None
    print(f"\n=== {label} ===", flush=True)
    print(f"Inputs: {len(table[0]).bit_length()-1}, outputs: {len(table)}", flush=True)
    print(f"{'G':>4}  {'result':>10}  {'wall':>6}", flush=True)
    model = TruthTableModel(table)
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


def main():
    print("Building bitvector simulation of 64-gate netlist...")
    W, _ = simulate_64gate()
    n_internal = len(W) - 8
    print(f"  {n_internal} internal wires + 8 inputs.")

    # ── B.1: not_65 cone with original inputs ──
    print("\n" + "=" * 60)
    print("B.1: not_65 cone (original inputs {w_43, w_58, w_65})")
    print("=" * 60)
    inputs = [W["w_43"], W["w_58"], W["w_65"]]
    targets = [W["y0"], W["w_69"]]
    rows, err = bv_to_truth_rows(inputs, targets)
    if rows is None:
        print(f"  Cone is leaky: {err}")
    else:
        # Try Cirbo at G=2, G=3
        # Expected: G=2 UNSAT, G=3 SAT
        find_min(rows, max_n=4, time_budget=60, label="B.1 not_65 cone")

    # ── B.2: not_45 + not_55 + not_65 cone ──
    print("\n" + "=" * 60)
    print("B.2: 3-NOT cone {w_45, w_55, w_65} → {not_45, not_55, not_65}")
    print("=" * 60)
    inputs2 = [W["w_45"], W["w_55"], W["w_65"]]
    targets2 = [W["not_45"], W["not_55"], W["not_65"]]
    rows2, err2 = bv_to_truth_rows(inputs2, targets2)
    if rows2 is None:
        print(f"  Cone is leaky: {err2}")
    else:
        find_min(rows2, max_n=4, time_budget=60, label="B.2 3-NOT cone")

    # ── B.3: not_47 + not_58 + not_68 trio ──
    print("\n" + "=" * 60)
    print("B.3: other 3-NOT cone {w_47, w_58, w_68} → {not_47, not_58, not_68}")
    print("=" * 60)
    inputs3 = [W["w_47"], W["w_58"], W["w_68"]]
    targets3 = [W["not_47"], W["not_58"], W["not_68"]]
    rows3, err3 = bv_to_truth_rows(inputs3, targets3)
    if rows3 is None:
        print(f"  Cone is leaky: {err3}")
    else:
        find_min(rows3, max_n=4, time_budget=60, label="B.3 second 3-NOT cone")

    # ── B.4: combined NOTs across more inputs ──
    # The hypothesis: if multiple NOTs share a common ancestor, there might
    # be a smaller circuit producing all 6 NOTs from a wider input set.
    print("\n" + "=" * 60)
    print("B.4: All 6 NOTs from raw a, b inputs (8 inputs → 6 outputs)")
    print("=" * 60)
    inputs4 = [W["a0"], W["a1"], W["a2"], W["a3"],
               W["b0"], W["b1"], W["b2"], W["b3"]]
    targets4 = [W["not_45"], W["not_47"], W["not_55"],
                W["not_58"], W["not_65"], W["not_68"]]
    rows4, err4 = bv_to_truth_rows(inputs4, targets4)
    if rows4 is None:
        print(f"  Cone is leaky: {err4}")
    else:
        # 8 inputs × 6 outputs = 256 minterms × 6 rows. Cirbo at small G should
        # be tractable. Walk from G=6 (each NOT separately) downward to find min.
        # Start from G=6 (= current NOT count + 0 sharing) downward.
        find_min(rows4, max_n=12, time_budget=120, label="B.4 6-NOT bundle")


if __name__ == "__main__":
    main()
