"""Convert a JSON-saved netlist back into a Python multiplier function and
verify against eval_circuit.evaluate_fast."""

from __future__ import annotations
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from eval_circuit import FP4_TABLE, evaluate_fast

OP_NAMES = {0:"NOT", 1:"AND", 2:"OR", 3:"XOR", 4:"CONST0", 5:"CONST1", 6:"BUF"}
N_IN = 8

def netlist_to_multiplier(netlist_path):
    with open(netlist_path) as f:
        d = json.load(f)
    gates = d["gates"]
    outs = d["outs"]

    def multiplier(a0,a1,a2,a3,b0,b1,b2,b3, NOT, AND, OR, XOR):
        vals = [a0,a1,a2,a3,b0,b1,b2,b3] + [None]*len(gates)
        for gi, (op, i, j) in enumerate(gates):
            idx = N_IN + gi
            if op == 0:   vals[idx] = NOT(vals[i])
            elif op == 1: vals[idx] = AND(vals[i], vals[j])
            elif op == 2: vals[idx] = OR(vals[i], vals[j])
            elif op == 3: vals[idx] = XOR(vals[i], vals[j])
            elif op == 4: vals[idx] = 0
            elif op == 5: vals[idx] = 1
            elif op == 6: vals[idx] = vals[i]
        return tuple(vals[o] for o in outs)
    return multiplier, gates, outs

INPUT_REMAP = []
_mag_to_code = {0.0:0,1.5:1,3.0:2,6.0:3,0.5:4,1.0:5,2.0:6,4.0:7}
for v in FP4_TABLE:
    s = 1 if v < 0 else 0
    INPUT_REMAP.append((s<<3)|_mag_to_code[abs(v)])

if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else "resub_result_81gates.json"
    mult, gates, outs = netlist_to_multiplier(path)
    correct, gc, errs = evaluate_fast(mult, INPUT_REMAP)
    print(f"Path: {path}")
    print(f"Gates in netlist: {len(gates)}")
    print(f"Gate count (eval_circuit): {gc}")
    print(f"Correct: {correct}, Errors: {len(errs)}")
    if errs:
        print(f"First 5 errors: {errs[:5]}")
