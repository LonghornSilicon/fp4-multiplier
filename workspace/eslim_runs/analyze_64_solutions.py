"""Compare the 19 distinct 64-gate solutions to find structural differences.

For each solution:
  1. Parse the netlist (gates, wires, inputs, outputs)
  2. Compute per-output cone size and per-cell-type distribution
  3. Identify which gates are PRIVATE to each output vs SHARED
  4. Find the "essential" core (gates in many cones)
  5. Look for solutions that differ structurally — these are crossover candidates

If two 64-gate solutions have SAME core but DIFFERENT private parts,
recombination might find a 63-gate hybrid.
"""
import sys
from collections import Counter, defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO / "lib"))
from verify import parse_blif, verify_blif
from remap import encoding_from_magnitude_perm

VALUES = encoding_from_magnitude_perm((0, 1, 2, 3, 6, 7, 4, 5))


def analyze(blif_path):
    p = parse_blif(blif_path)
    inputs = p["inputs"]
    outputs = p["outputs"]
    gates = list(p["gates"])

    out_to_idx = {g[0]: i for i, g in enumerate(gates)}
    fanin = {g[0]: g[2] for g in gates}

    # Per-output cone (gate names that drive each output)
    def cone(target):
        visited = set()
        stack = [target]
        while stack:
            n = stack.pop()
            if n in visited or n not in fanin:
                continue
            visited.add(n)
            for s in fanin[n]:
                stack.append(s)
        return visited

    output_cones = {op: cone(op) & set(fanin.keys()) for op in outputs}
    # Count gate types
    type_counts = Counter(g[1] for g in gates)

    # Find shared gates: those in multiple cones
    gate_in_cones = Counter()
    for op, c in output_cones.items():
        for g in c:
            gate_in_cones[g] += 1

    # Per-cone breakdown
    cone_compositions = {}
    for op, c in output_cones.items():
        cone_gates = [g for g in gates if g[0] in c]
        cone_compositions[op] = Counter(g[1] for g in cone_gates)

    return {
        'gates': gates,
        'n_gates': len(gates),
        'type_counts': type_counts,
        'cone_sizes': {op: len(c) for op, c in output_cones.items()},
        'cone_compositions': cone_compositions,
        'gate_fanout_to_outputs': dict(gate_in_cones),
    }


def main():
    runs_file = sys.argv[1] if len(sys.argv) > 1 else "/tmp/64gate_runs.txt"
    with open(runs_file) as f:
        runs = [ln.strip() for ln in f if ln.strip()]

    out_dir = REPO / "workspace" / "eslim_runs" / "outputs"
    print(f"Analyzing {len(runs)} 64-gate solutions...")
    print(f"{'Run':>50}  {'Gates':>5}  {'AND':>4} {'OR':>4} {'XOR':>4} {'NOT':>4}  {'Y[0]':>4} {'Y[7]':>4}")

    summaries = []
    for run in runs:
        legacy_path = out_dir / f"{run}_legacy.blif"
        if not legacy_path.exists():
            continue
        try:
            a = analyze(legacy_path)
            tc = a['type_counts']
            cone7 = a['cone_sizes'].get('y[7]', 0)
            cone0 = a['cone_sizes'].get('y[0]', 0)
            print(f"  {run:>50}  {a['n_gates']:>5}  {tc.get('AND',0):>4} {tc.get('OR',0):>4} {tc.get('XOR',0):>4} {tc.get('NOT',0):>4}  {cone0:>4} {cone7:>4}")
            summaries.append((run, a))
        except Exception as e:
            print(f"  {run}: ERROR {e}")

    # Find solutions where Y[7] cone differs (most signal of structural diversity)
    cone7s = [(s[1]['cone_sizes'].get('y[7]', 0), s[0]) for s in summaries]
    cone7s.sort()
    print("\nY[7] cone size distribution (smallest is most-shared):")
    for sz, name in cone7s[:5]:
        print(f"  {sz}  {name}")
    print(f"  ...")
    for sz, name in cone7s[-3:]:
        print(f"  {sz}  {name}")


if __name__ == "__main__":
    main()
