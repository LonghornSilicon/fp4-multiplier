"""
Systematically search for more algebraic optimizations in the 84-gate circuit.

Checks:
1. Can any intermediate signal in the circuit be derived from another?
2. Are there OR gates in the magnitude assembly that can be simplified?
3. Can any AND-terms be shown to be always 0 (pruned)?
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from eval_circuit import FP4_TABLE
from itertools import product as iproduct

_mag_to_code = {0.0:0,1.5:1,3.0:2,6.0:3,0.5:4,1.0:5,2.0:6,4.0:7}
REMAP = [(1 if v < 0 else 0) << 3 | _mag_to_code[abs(v)] for v in FP4_TABLE]


def simulate_circuit(a0, a1, a2, a3, b0, b1, b2, b3):
    """Simulate the full circuit and return all intermediate signals as dict."""
    n = lambda x: 1-x
    AND = lambda x,y: x&y
    OR = lambda x,y: x|y
    XOR = lambda x,y: x^y

    sign = XOR(a0,b0)
    or_a23 = OR(a2,a3); nz_a = OR(a1,or_a23)
    or_b23 = OR(b2,b3); nz_b = OR(b1,or_b23)
    nz = AND(nz_a,nz_b)
    s0 = XOR(a3,b3); c0 = AND(a3,b3)
    s1x = XOR(a2,b2); s1 = XOR(s1x,c0)
    s2 = OR(AND(a2,b2), AND(s1x,c0))
    or_a1b1 = OR(a1,b1)
    k9_raw = n(or_a1b1)
    k3_raw = XOR(a1,b1)
    nmc = AND(or_a1b1,nz)
    k3  = AND(k3_raw,nz)
    k9  = AND(k9_raw,nz)
    ns0 = n(s0); ns1 = n(s1); ns2 = n(s2)
    u00 = AND(ns2,ns1); u01 = AND(ns2,s1)
    u10 = AND(s2,ns1);  u11 = AND(s2,s1)
    sh0 = AND(u00,ns0); sh1 = AND(u00,s0)
    sh2 = AND(u01,ns0); sh3 = AND(u01,s0)
    sh4 = AND(u10,ns0); sh5 = AND(u10,s0)
    nmc0=AND(nmc,sh0); nmc1=AND(nmc,sh1); nmc2=AND(nmc,sh2)
    nmc3=AND(nmc,sh3); nmc4=AND(nmc,sh4); nmc5=AND(nmc,sh5)
    nmc6=AND(nmc,u11)
    k3_1=AND(k3,sh1); k3_2=AND(k3,sh2); k3_3=AND(k3,sh3)
    k3_4=AND(k3,sh4); k3_5=AND(k3,sh5); k3_6=AND(k3,u11)
    k9_2=AND(k9,sh2); k9_3=AND(k9,sh3); k9_4=AND(k9,sh4)
    k9_5=AND(k9,sh5); k9_6=AND(k9,u11)
    m7=k9_6
    m6=OR(nmc6,k9_5)
    m5=OR(nmc5,OR(k3_6,k9_4))
    m4=OR(OR(nmc4,k3_5),OR(k9_6,k9_3))
    m3=OR(OR(nmc3,k3_4),OR(k9_5,k9_2))
    m2=OR(nmc2,OR(k3_3,k9_4))
    m1=OR(nmc1,OR(k3_2,k9_3))
    m0=OR(nmc0,OR(k3_1,k9_2))
    res0=AND(sign,nz)
    p2=OR(m0,m1); p3=OR(p2,m2); p4=OR(p3,m3)
    p5=OR(p4,m4); p6=OR(p5,m5)

    return {
        'a0':a0,'a1':a1,'a2':a2,'a3':a3,'b0':b0,'b1':b1,'b2':b2,'b3':b3,
        'sign':sign,'nz_a':nz_a,'nz_b':nz_b,'nz':nz,
        's0':s0,'s1':s1,'s2':s2,'c0':c0,
        'or_a1b1':or_a1b1,'k9_raw':k9_raw,'k3_raw':k3_raw,
        'nmc':nmc,'k3':k3,'k9':k9,
        'ns0':ns0,'ns1':ns1,'ns2':ns2,
        'u00':u00,'u01':u01,'u10':u10,'u11':u11,
        'sh0':sh0,'sh1':sh1,'sh2':sh2,'sh3':sh3,'sh4':sh4,'sh5':sh5,
        'nmc0':nmc0,'nmc1':nmc1,'nmc2':nmc2,'nmc3':nmc3,'nmc4':nmc4,'nmc5':nmc5,'nmc6':nmc6,
        'k3_1':k3_1,'k3_2':k3_2,'k3_3':k3_3,'k3_4':k3_4,'k3_5':k3_5,'k3_6':k3_6,
        'k9_2':k9_2,'k9_3':k9_3,'k9_4':k9_4,'k9_5':k9_5,'k9_6':k9_6,
        'm0':m0,'m1':m1,'m2':m2,'m3':m3,'m4':m4,'m5':m5,'m6':m6,'m7':m7,
        'res0':res0,'p2':p2,'p3':p3,'p4':p4,'p5':p5,'p6':p6,
    }


def check_always_zero():
    """Find any intermediate signal that is always 0."""
    print("=== Checking for always-zero signals ===")
    always_zero = set()
    first = True
    all_sigs = None

    for a in range(16):
        for b in range(16):
            a_code = REMAP[a]; b_code = REMAP[b]
            a0=(a_code>>3)&1; a1=(a_code>>2)&1; a2=(a_code>>1)&1; a3=a_code&1
            b0=(b_code>>3)&1; b1=(b_code>>2)&1; b2=(b_code>>1)&1; b3=b_code&1
            sigs = simulate_circuit(a0,a1,a2,a3,b0,b1,b2,b3)
            if first:
                all_sigs = {k: True for k in sigs}
                first = False
            for k,v in sigs.items():
                if v != 0:
                    all_sigs[k] = False

    always_0 = [k for k,v in all_sigs.items() if v]
    print(f"  Always-zero signals: {always_0}")


def check_signal_equivalences():
    """Check if any two signals are always equal."""
    print("\n=== Checking signal equivalences (always equal) ===")

    all_data = []
    for a in range(16):
        for b in range(16):
            a_code = REMAP[a]; b_code = REMAP[b]
            a0=(a_code>>3)&1; a1=(a_code>>2)&1; a2=(a_code>>1)&1; a3=a_code&1
            b0=(b_code>>3)&1; b1=(b_code>>2)&1; b2=(b_code>>1)&1; b3=b_code&1
            all_data.append(simulate_circuit(a0,a1,a2,a3,b0,b1,b2,b3))

    sig_names = list(all_data[0].keys())
    sig_vectors = {k: tuple(d[k] for d in all_data) for k in sig_names}

    # Group signals by their truth vector
    from collections import defaultdict
    groups = defaultdict(list)
    for k, v in sig_vectors.items():
        groups[v].append(k)

    equiv_groups = [(v, sigs) for v, sigs in groups.items() if len(sigs) > 1]
    print(f"  Found {len(equiv_groups)} equivalence groups with 2+ signals:")
    for v, sigs in sorted(equiv_groups, key=lambda x: -len(x[1])):
        # Filter out input signals
        non_inputs = [s for s in sigs if s not in ('a0','a1','a2','a3','b0','b1','b2','b3')]
        if len(non_inputs) >= 2:
            print(f"    {non_inputs} (all equal)")


def check_or_necessity():
    """Check if any OR gate input is always dominated by the other (A OR B where A implies B)."""
    print("\n=== Checking OR gate redundancy ===")

    all_data = []
    for a in range(16):
        for b in range(16):
            a_code = REMAP[a]; b_code = REMAP[b]
            a0=(a_code>>3)&1; a1=(a_code>>2)&1; a2=(a_code>>1)&1; a3=a_code&1
            b0=(b_code>>3)&1; b1=(b_code>>2)&1; b2=(b_code>>1)&1; b3=b_code&1
            all_data.append(simulate_circuit(a0,a1,a2,a3,b0,b1,b2,b3))

    def always_implies(a_name, b_name):
        """Check if a_name=1 implies b_name=1 for all achievable inputs."""
        for d in all_data:
            if d[a_name] == 1 and d[b_name] == 0:
                return False
        return True

    # Check OR gates in the circuit
    or_gates = [
        ('nz_a', ['a1', 'or_a23']), ('nz_b', ['b1', 'or_b23']),
        ('m6', ['nmc6', 'k9_5']), ('m5', ['nmc5', 'k9_4']),  # simplified
        ('p2', ['m0', 'm1']), ('p3', ['p2', 'm2']),
        ('p4', ['p3', 'm3']), ('p5', ['p4', 'm4']), ('p6', ['p5', 'm5']),
    ]

    for output, inputs in or_gates:
        a, b = inputs
        if always_implies(a, b):
            print(f"  OR({a},{b}) = {b} (since {a} => {b} always): can replace with just {b}!")
        elif always_implies(b, a):
            print(f"  OR({a},{b}) = {a} (since {b} => {a} always): can replace with just {a}!")
        else:
            pass  # OR is necessary


def analyze_m7_special():
    """m7 = k9_6 is just a wire (no gate). Verify and find similar cases."""
    print("\n=== Checking for wire assignments (0-gate computations) ===")
    all_data = []
    for a in range(16):
        for b in range(16):
            a_code = REMAP[a]; b_code = REMAP[b]
            a0=(a_code>>3)&1; a1=(a_code>>2)&1; a2=(a_code>>1)&1; a3=a_code&1
            b0=(b_code>>3)&1; b1=(b_code>>2)&1; b2=(b_code>>1)&1; b3=b_code&1
            all_data.append(simulate_circuit(a0,a1,a2,a3,b0,b1,b2,b3))

    sig_names = list(all_data[0].keys())
    sig_vectors = {k: tuple(d[k] for d in all_data) for k in sig_names}

    mag_sigs = ['m0','m1','m2','m3','m4','m5','m6','m7']
    and_sigs = ['nmc0','nmc1','nmc2','nmc3','nmc4','nmc5','nmc6',
                'k3_1','k3_2','k3_3','k3_4','k3_5','k3_6',
                'k9_2','k9_3','k9_4','k9_5','k9_6']

    print("  Magnitude bits that equal AND-terms (wire, no OR gate needed):")
    for m in mag_sigs:
        mv = sig_vectors[m]
        for at in and_sigs:
            if sig_vectors[at] == mv:
                print(f"    {m} == {at}")


if __name__ == "__main__":
    check_always_zero()
    check_signal_equivalences()
    check_or_necessity()
    analyze_m7_special()
