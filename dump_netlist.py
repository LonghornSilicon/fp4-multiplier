"""Pretty-print the 81-gate netlist for manual inspection."""
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sa_search import N_IN, NOT_OP, AND_OP, OR_OP, XOR_OP, CONST0, CONST1, BUF, simulate, ALL_ONE

OP_NAMES = {NOT_OP:"NOT", AND_OP:"AND", OR_OP:"OR", XOR_OP:"XOR",
            CONST0:"0",   CONST1:"1",   BUF:"BUF"}

def dump(path):
    with open(path) as f:
        d = json.load(f)
    gates = d["gates"]
    outs = d["outs"]

    in_names = ["a0","a1","a2","a3","b0","b1","b2","b3"]
    names = list(in_names) + [f"n{N_IN+i}" for i in range(len(gates))]
    fanout = [0] * (N_IN + len(gates))
    for op, i, j in gates:
        fanout[i] += 1
        if op in (AND_OP, OR_OP, XOR_OP):
            fanout[j] += 1
    for o in outs: fanout[o] += 1

    print(f"# {len(gates)} gates, outs={outs} ({[names[o] for o in outs]})")
    for gi, (op, i, j) in enumerate(gates):
        idx = N_IN + gi
        if op in (NOT_OP, BUF):
            expr = f"{OP_NAMES[op]}({names[i]})"
        elif op in (CONST0, CONST1):
            expr = OP_NAMES[op]
        else:
            expr = f"{OP_NAMES[op]}({names[i]}, {names[j]})"
        print(f"  {names[idx]:>5s} = {expr:<24s}  fanout={fanout[idx]}")

    # Also print bitvectors briefly
    base_vals = simulate(gates)
    print("\n# popcounts (number of 1s in care-set bitvector, out of 225):")
    for gi in range(len(gates)):
        idx = N_IN + gi
        bv = base_vals[idx]
        pop = bin(bv).count("1")
        print(f"  {names[idx]:>5s}: {pop}")

if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else "resub_result_81gates.json"
    dump(path)
