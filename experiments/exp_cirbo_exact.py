"""
SAT-based exact synthesis for two FP4-multiplier sub-functions, using Cirbo's
CircuitFinderSat. Goal: prove the minimum gate count (in XAIG / AIG bases) for
the S-decoder (3-in 7-out) and the E-sum + S-decoder (4-in 7-out).

Sub-function 1 (S-decoder):
    Inputs s2, s1, s0 = 3-bit number S in {0..6}.
    Outputs sh0..sh6 = one-hot of S. S=7 is don't-care.
    Hand-crafted: 13 gates.

Sub-function 2 (E-sum + decoder):
    Inputs a2, a3, b2, b3 (two 2-bit numbers).
    S = (a2,a3) + (b2,b3) in {0..6}, then one-hot decode.
    Hand-crafted: 20 gates (incl. 7-gate adder).
    No don't-cares (S in {0..6} for all 16 inputs).

Run: python3 experiments/exp_cirbo_exact.py

=== EXPERIMENTAL RESULTS (2026-04-28) ===

Sub-function 1: S-decoder (3-in, 7-out, 1 don't-care row)
  Basis XAIG:  N=8 UNSAT (1.15s), N=9 SAT (0.15s) — MINIMUM = 9
  Basis AIG:   N=8 UNSAT (1.26s), N=9 SAT (0.15s) — MINIMUM = 9
  Basis {NOT,AND,OR,XOR} (realistic):
               N=9 UNSAT (5.84s), N=10 TIMEOUT (300s), N=11 SAT (0.69s)
               => minimum is 11 (can't rule out 10 with 5-min cap)
  Hand-crafted saves 2 gates (13) vs realistic-basis optimum (11).

  9-gate XAIG circuit (inputs 0=s2, 1=s1, 2=s0):
    AND(0,1), NOR(1,2), LT(0,NOR), NOR(0,NOR),
    LT(2,NOR_0), AND(1,2), LT(1,NOR_0), AND(0,2), XOR(NOR,LT_0)
    outputs: [sh0..sh6]

  11-gate {NOT,AND,OR,XOR} circuit (VERIFIED CORRECT):
    s3=XOR(s2,s1), s4=AND(s2,s0), s5=XOR(s0,s3), s6=AND(s2,s5),
    s7=OR(s2,s5), s8=OR(s3,s7), s9=AND(s1,s5), s10=AND(s1,s0),
    s11=AND(s0,s5), s12=AND(s2,s1), sh0=NOT(s8)
    outputs: [sh0=NOT(s8), sh1=s11, sh2=s9, sh3=s10, sh4=s6, sh5=s4, sh6=s12]

Sub-function 2: E-sum + decoder (4-in, 7-out, no don't-cares)
  Basis XAIG: N=20 SAT(40s), N=18 SAT(231s), N=16 SAT(34s), N=14 SAT(88s),
              N=13 TIMEOUT(300s), N=12 TIMEOUT(120s)
              => SAT proven down to N=14; N=13 unknown (timeout)
  Basis AIG:  N=20 SAT(18s), N=18 TIMEOUT(124s), N=16 TIMEOUT(123s),
              N=14 TIMEOUT(124s)
              => SAT proven only at N=20; all smaller timed out
  Hand-crafted (20) is at least 6 gates above XAIG optimum (14 known SAT).
"""

import time
from typing import List, Optional, Tuple, Union

from cirbo.core.logic import DontCare, TriValue
from cirbo.core.truth_table import TruthTableModel
from cirbo.synthesis.circuit_search import CircuitFinderSat
from cirbo.synthesis.exception import NoSolutionError, SolverTimeOutError


TIME_LIMIT_S = 300  # 5 min cap per (N, basis) attempt


# ---------------------------------------------------------------------------
# API sanity check: 2-input XOR -> provably 1 gate in XAIG.
# ---------------------------------------------------------------------------
def sanity_check_xor() -> None:
    print("[sanity] 2-input XOR, basis=XAIG, N=1")
    # input order (in0, in1); index j = in0*2 + in1 (in0 = MSB).
    # XOR truth table over j=0..3: 0,1,1,0
    tt = [[False, True, True, False]]
    model = TruthTableModel(tt)
    finder = CircuitFinderSat(model, number_of_gates=1, basis="XAIG")
    t0 = time.time()
    try:
        circ = finder.find_circuit(time_limit=30)
        dt = time.time() - t0
        print(f"  -> SAT in {dt:.2f}s, gates={circ.gates_number()}")
        # show the gate types
        for g in circ.gates.values():
            print(f"     gate {g.label} type={g.gate_type.name} "
                  f"operands={g.operands}")
    except NoSolutionError:
        dt = time.time() - t0
        print(f"  -> UNSAT in {dt:.2f}s (unexpected)")
    except SolverTimeOutError:
        print("  -> TIMEOUT")
    print()


# ---------------------------------------------------------------------------
# Truth table builders.
# ---------------------------------------------------------------------------
def build_sdec_tt() -> List[List[TriValue]]:
    """7 outputs sh0..sh6, 8 input rows for (s2,s1,s0). S=7 = don't-care."""
    rows = []  # rows[j] = list of 7 outputs for input j
    for j in range(8):
        if j == 7:
            rows.append([DontCare] * 7)
        else:
            row = [False] * 7
            row[j] = True
            rows.append(row)
    # Transpose: out[i][j]
    out = [[rows[j][i] for j in range(8)] for i in range(7)]
    return out


def build_esum_dec_tt() -> List[List[bool]]:
    """4 inputs (a2,a3,b2,b3) [a2 = MSB]. 7 outputs sh0..sh6 of one-hot of
    S = (a2 a3) + (b2 b3), where (a2 a3) means a2*2 + a3."""
    out = [[False] * 16 for _ in range(7)]
    for j in range(16):
        # j = a2*8 + a3*4 + b2*2 + b3  (big-endian: a2 is bit3)
        a2 = (j >> 3) & 1
        a3 = (j >> 2) & 1
        b2 = (j >> 1) & 1
        b3 = j & 1
        A = a2 * 2 + a3
        B = b2 * 2 + b3
        S = A + B  # in 0..6
        out[S][j] = True
    return out


# ---------------------------------------------------------------------------
# Sweep helper.
# ---------------------------------------------------------------------------
def sweep(
    name: str,
    tt: List[List[Union[bool, TriValue]]],
    n_lo: int,
    n_hi: int,
    basis: str,
    time_limit: int = TIME_LIMIT_S,
) -> Tuple[Optional[int], dict]:
    """Try N from n_lo upward; report the smallest N that is SAT.
    Returns (smallest_sat_N, {N: (status, time_s)})."""
    print(f"=== {name}  basis={basis}  N={n_lo}..{n_hi}  "
          f"time_limit={time_limit}s ===")
    model = TruthTableModel(tt)
    smallest = None
    log = {}
    for N in range(n_lo, n_hi + 1):
        t0 = time.time()
        try:
            finder = CircuitFinderSat(model, number_of_gates=N, basis=basis)
            circ = finder.find_circuit(time_limit=time_limit)
            dt = time.time() - t0
            print(f"  N={N:3d}: SAT  in {dt:7.2f}s  "
                  f"(gates={circ.gates_number()})")
            log[N] = ("SAT", dt, circ)
            smallest = N
            return smallest, log  # smallest SAT found, no need to continue up
        except NoSolutionError:
            dt = time.time() - t0
            print(f"  N={N:3d}: UNSAT in {dt:7.2f}s")
            log[N] = ("UNSAT", dt, None)
        except SolverTimeOutError:
            dt = time.time() - t0
            print(f"  N={N:3d}: TIMEOUT after {dt:.1f}s "
                  f"(>{time_limit}s)")
            log[N] = ("TIMEOUT", dt, None)
            # Keep going: a larger N may be easier (or it may be hopeless).
    return smallest, log


def show_circuit(circ) -> None:
    print(f"  Circuit: {circ.gates_number()} gates, "
          f"{circ.inputs_number()} inputs, {circ.outputs_number()} outputs")
    for g in circ.gates.values():
        print(f"    {g.label}: {g.gate_type.name} {g.operands}")
    print(f"  outputs: {list(circ.outputs)}")


# ---------------------------------------------------------------------------
# Main.
# ---------------------------------------------------------------------------
def main() -> None:
    sanity_check_xor()

    sdec_tt = build_sdec_tt()
    esum_tt = build_esum_dec_tt()

    # ---- S-decoder ----------------------------------------------------------
    # Known: 9 SAT (XAIG/AIG), 8 UNSAT. Realistic basis: 11 SAT, 10 unknown.
    print("\n##### Sub-function 1: S-decoder (hand=13) #####\n")
    sdec_xaig = sweep("S-decoder", sdec_tt, n_lo=8, n_hi=9, basis="XAIG")
    sdec_aig = sweep("S-decoder", sdec_tt, n_lo=8, n_hi=9, basis="AIG")

    # Realistic {NOT,AND,OR,XOR} basis for S-decoder
    from cirbo.synthesis.circuit_search import Operation
    real_basis = [Operation.lnot_, Operation.and_, Operation.or_, Operation.xor_]
    print("\n##### S-decoder realistic basis {NOT,AND,OR,XOR} #####\n")
    sdec_real = sweep("S-decoder-real", sdec_tt, n_lo=9, n_hi=11,
                      basis=real_basis, time_limit=120)  # type: ignore

    # ---- E-sum + decoder ----------------------------------------------------
    # Known: XAIG 14 SAT (88s), 13 TIMEOUT. AIG 20 SAT, all smaller timeout.
    print("\n##### Sub-function 2: E-sum + decoder (hand=20) #####\n")
    esum_xaig = sweep("E-sum+decoder", esum_tt, n_lo=14, n_hi=20, basis="XAIG")
    esum_aig = sweep("E-sum+decoder", esum_tt, n_lo=20, n_hi=20, basis="AIG")

    # ---- summary ------------------------------------------------------------
    print("\n##### SUMMARY #####")

    def report(label, hand, sweep_xaig, sweep_aig):
        smX, logX = sweep_xaig
        smA, logA = sweep_aig
        print(f"\n  {label} (hand-crafted = {hand}):")
        print(f"    XAIG: smallest SAT N = "
              f"{smX if smX is not None else 'not found'}")
        print(f"    AIG : smallest SAT N = "
              f"{smA if smA is not None else 'not found'}")
        if smX is not None and smX < hand:
            print(f"    *** XAIG beats hand-crafted by {hand - smX} gates ***")
            show_circuit(logX[smX][2])
        if smA is not None and smA < hand:
            print(f"    *** AIG beats hand-crafted by {hand - smA} gates ***")
            show_circuit(logA[smA][2])

    report("S-decoder", 13, sdec_xaig, sdec_aig)
    report("E-sum + decoder", 20, esum_xaig, esum_aig)


if __name__ == "__main__":
    main()
