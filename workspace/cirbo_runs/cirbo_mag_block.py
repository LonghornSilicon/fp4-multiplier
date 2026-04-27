"""Cirbo SAT on the FULL magnitude sub-block (eh, el, m of both -> mag[7..0]).

This combines the 2x2 mul + K-compute + K-shift sub-blocks into one
sub-circuit with sharing allowed. Gives a sharing-aware lower bound.

Inputs (6): eh_a, el_a, m_a, eh_b, el_b, m_b
Outputs (8): mag[7..0] = (M_a * M_b) << K

where M_i = 2*(eh_i | el_i) + m_i, K = sa1 + sb1, sa1 = eh_a*(1+el_a),
sb1 = eh_b*(1+el_b).

For sigma=(0,1,2,3,6,7,4,5), the encoding-to-mag mapping uses raw bits:
  lb = a[1] | a[2] (= eh|el via the σ collapse)
  el = a[1] ^ a[2]
  eh = a[2]
  m  = a[0]

But for SAT-search purposes, we feed Cirbo the abstract (eh,el,m) interface
directly (6 inputs) since the σ remap is just a cosmetic bit-renaming.
"""
import sys, time
sys.path.insert(0, "/home/shadeform/fp4-multiplier/lib")
from cirbo.core.truth_table import TruthTableModel
from cirbo.synthesis.circuit_search import CircuitFinderSat, Operation

OUR_BASIS = [Operation.and_, Operation.or_, Operation.xor_, Operation.lnot_]


def build_mag_table():
    """6 inputs (eh_a, el_a, m_a, eh_b, el_b, m_b), 8 outputs (mag[7..0])."""
    out = [[False] * 64 for _ in range(8)]
    for idx in range(64):
        # idx bits: bit 0 = eh_a, bit 1 = el_a, bit 2 = m_a, bit 3 = eh_b, bit 4 = el_b, bit 5 = m_b
        eh_a = (idx >> 0) & 1
        el_a = (idx >> 1) & 1
        m_a  = (idx >> 2) & 1
        eh_b = (idx >> 3) & 1
        el_b = (idx >> 4) & 1
        m_b  = (idx >> 5) & 1
        # M_i = 2*(eh|el) + m  (note: not 2*eh, since lb = eh|el)
        Ma = 2 * (eh_a | el_a) + m_a
        Mb = 2 * (eh_b | el_b) + m_b
        # K = sa1 + sb1, sa1 = eh*(1+el)
        sa1 = eh_a * (1 + el_a)
        sb1 = eh_b * (1 + el_b)
        K = sa1 + sb1
        mag = (Ma * Mb) << K  # 8-bit shift
        mag &= 0xFF
        for k in range(8):
            out[k][idx] = bool((mag >> k) & 1)
    return out


def main():
    G_start = int(sys.argv[1]) if len(sys.argv) > 1 else 25
    G_max = int(sys.argv[2]) if len(sys.argv) > 2 else 50
    time_limit = int(sys.argv[3]) if len(sys.argv) > 3 else 1800
    solver = sys.argv[4] if len(sys.argv) > 4 else "cadical195"

    table = build_mag_table()
    model = TruthTableModel(table)
    print(f"Magnitude sub-block: 6 inputs, 8 outputs, 64 minterms",
          flush=True)
    print(f"Walking G {G_start}..{G_max} with {time_limit}s budget per step (solver={solver})",
          flush=True)
    last_unsat = None
    for G in range(G_start, G_max + 1):
        finder = CircuitFinderSat(boolean_function_model=model,
                                  number_of_gates=G, basis=OUR_BASIS)
        t0 = time.time()
        try:
            circuit = finder.find_circuit(solver_name=solver, time_limit=time_limit)
            wall = time.time() - t0
            print(f"  G={G}: SAT  ({wall:.1f}s)  -> magnitude sub-block min = {G} (>=  {(last_unsat or G_start - 1) + 1})",
                  flush=True)
            print(f"--- Circuit ---", flush=True)
            print(circuit.format_circuit(), flush=True)
            return
        except Exception as e:
            wall = time.time() - t0
            ename = type(e).__name__
            if "NoSolution" in ename:
                last_unsat = G
                print(f"  G={G}: UNSAT ({wall:.1f}s)", flush=True)
            elif "TimeOut" in ename or "Timeout" in ename:
                print(f"  G={G}: TIMEOUT ({wall:.1f}s)  -> magnitude sub-block >= {(last_unsat or G_start - 1) + 1}, indeterminate at {G}",
                      flush=True)
                return
            else:
                print(f"  G={G}: ERROR {ename}: {e}", flush=True)
                return


if __name__ == "__main__":
    main()
