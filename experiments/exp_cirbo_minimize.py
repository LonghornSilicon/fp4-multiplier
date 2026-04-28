"""
Cirbo subcircuit minimization on the 84-gate v4d circuit.

Strategy: build the structural circuit as a Cirbo Circuit, then run
`minimize_subcircuits` (SAT-based windowed replacement) to find any
small subcircuits that can be replaced with smaller equivalents.

Run: python3 experiments/exp_cirbo_minimize.py
"""

from cirbo.core import Circuit
from cirbo.core.circuit.gate import Gate, AND, OR, NOT, XOR, INPUT
from cirbo.minimization import minimize_subcircuits


def build_v4d_circuit() -> Circuit:
    c = Circuit()
    inputs = ["a0", "a1", "a2", "a3", "b0", "b1", "b2", "b3"]
    for i in inputs:
        c.add_gate(Gate(i, INPUT))

    def a(label, op, l, r):
        c.add_gate(Gate(label, op, (l, r)))
    def n(label, x):
        c.add_gate(Gate(label, NOT, (x,)))

    # sign
    a("sign", XOR, "a0", "b0")

    # nz
    a("or_a23", OR, "a2", "a3");   a("nz_a", OR, "a1", "or_a23")
    a("or_b23", OR, "b2", "b3");   a("nz_b", OR, "b1", "or_b23")
    a("nz", AND, "nz_a", "nz_b")

    # E-sum: 7 gates
    a("s0", XOR, "a3", "b3");      a("c0", AND, "a3", "b3")
    a("s1x", XOR, "a2", "b2");     a("s1", XOR, "s1x", "c0")
    a("a2b2", AND, "a2", "b2");    a("s1xc0", AND, "s1x", "c0")
    a("s2", OR, "a2b2", "s1xc0")

    # K-flags
    a("or_a1b1", OR, "a1", "b1")
    n("k9_raw", "or_a1b1")
    a("k3_raw", XOR, "a1", "b1")

    # Mask
    a("nmc", AND, "or_a1b1", "nz")
    a("k3", AND, "k3_raw", "nz")
    a("k9", AND, "k9_raw", "nz")

    # S decoder
    n("ns0", "s0"); n("ns1", "s1"); n("ns2", "s2")
    a("u00", AND, "ns2", "ns1");   a("u01", AND, "ns2", "s1")
    a("u10", AND, "s2", "ns1");    a("u11", AND, "s2", "s1")
    a("sh0", AND, "u00", "ns0");   a("sh1", AND, "u00", "s0")
    a("sh2", AND, "u01", "ns0");   a("sh3", AND, "u01", "s0")
    a("sh4", AND, "u10", "ns0");   a("sh5", AND, "u10", "s0")
    # sh6 = u11

    # AND-terms
    a("nmc0", AND, "nmc", "sh0"); a("nmc1", AND, "nmc", "sh1")
    a("nmc2", AND, "nmc", "sh2"); a("nmc3", AND, "nmc", "sh3")
    a("nmc4", AND, "nmc", "sh4"); a("nmc5", AND, "nmc", "sh5")
    a("nmc6", AND, "nmc", "u11")

    a("k3_1", AND, "k3", "sh1"); a("k3_2", AND, "k3", "sh2")
    a("k3_3", AND, "k3", "sh3"); a("k3_4", AND, "k3", "sh4")
    a("k3_5", AND, "k3", "sh5"); a("k3_6", AND, "k3", "u11")

    a("k9_2", AND, "k9", "sh2"); a("k9_3", AND, "k9", "sh3")
    a("k9_4", AND, "k9", "sh4"); a("k9_5", AND, "k9", "sh5")
    a("k9_6", AND, "k9", "u11")

    # Magnitude bits
    # m7 = k9_6  -> aliased
    # m6 = nmc6 | k9_5
    a("m6", OR, "nmc6", "k9_5")
    # m5 = nmc5 | k3_6 | k9_4
    a("m5_a", OR, "k3_6", "k9_4");  a("m5", OR, "nmc5", "m5_a")
    # m4 = nmc4 | k3_5 | k9_6 | k9_3
    a("m4_a", OR, "nmc4", "k3_5");  a("m4_b", OR, "k9_6", "k9_3");  a("m4", OR, "m4_a", "m4_b")
    # m3 = nmc3 | k3_4 | k9_5 | k9_2
    a("m3_a", OR, "nmc3", "k3_4");  a("m3_b", OR, "k9_5", "k9_2");  a("m3", OR, "m3_a", "m3_b")
    # m2 = nmc2 | k3_3 | k9_4
    a("m2_a", OR, "k3_3", "k9_4");  a("m2", OR, "nmc2", "m2_a")
    # m1 = nmc1 | k3_2 | k9_3
    a("m1_a", OR, "k3_2", "k9_3");  a("m1", OR, "nmc1", "m1_a")
    # m0 = nmc0 | k3_1 | k9_2
    a("m0_a", OR, "k3_1", "k9_2");  a("m0", OR, "nmc0", "m0_a")

    # res0 = AND(sign, nz)
    a("res0", AND, "sign", "nz")

    # Prefix-OR (5 gates)
    a("p2", OR, "m0", "m1");  a("p3", OR, "p2", "m2");  a("p4", OR, "p3", "m3")
    a("p5", OR, "p4", "m4");  a("p6", OR, "p5", "m5")

    # AND with sign (6 gates)
    a("sp1", AND, "sign", "m0");  a("sp2", AND, "sign", "p2"); a("sp3", AND, "sign", "p3")
    a("sp4", AND, "sign", "p4");  a("sp5", AND, "sign", "p5"); a("sp6", AND, "sign", "p6")
    # sp7 = res0

    # XOR with magnitude (7 gates)
    a("r7", XOR, "m1", "sp1"); a("r6", XOR, "m2", "sp2"); a("r5", XOR, "m3", "sp3")
    a("r4", XOR, "m4", "sp4"); a("r3", XOR, "m5", "sp5"); a("r2", XOR, "m6", "sp6")
    a("r1", XOR, "k9_6", "res0")  # m7 = k9_6, sp7 = res0

    # Mark outputs (res0, r1..r7, r8=m0)
    c.set_outputs(["res0", "r1", "r2", "r3", "r4", "r5", "r6", "r7", "m0"])
    return c


def count_non_input_gates(circuit: Circuit) -> int:
    n = 0
    for label in circuit.gates:
        g = circuit.get_gate(label)
        if g.gate_type != INPUT:
            n += 1
    return n


def main():
    c = build_v4d_circuit()
    n0 = count_non_input_gates(c)
    print(f"Initial circuit: {n0} non-input gates (expected 84)")

    # Run subcircuit minimization
    print("Running minimize_subcircuits with XAIG basis...")
    out = minimize_subcircuits(c, basis="XAIG", max_subcircuit_size=7,
                                solver_time_limit_sec=30,
                                enable_validation=True)
    n1 = count_non_input_gates(out)
    print(f"After minimization: {n1} gates (delta = {n1 - n0})")

    # Save the result
    bench = out.into_bench()
    with open("experiments/data/v4d_min.bench", "w") as f:
        f.write(str(bench))
    print("Saved experiments/data/v4d_min.bench")


if __name__ == "__main__":
    main()
