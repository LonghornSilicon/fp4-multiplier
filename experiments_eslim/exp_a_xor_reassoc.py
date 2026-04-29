"""
Experiment A: Gate-neutral XOR re-association sweep on the canonical
LonghornSilicon 64-gate netlist, followed by eSLIM re-optimization.

The 65→64 win came from rewriting XOR(XOR(a,b),c) → XOR(a, XOR(b,c)) at
one specific wire (w_75) and then re-running eSLIM. Same gate count, same
function — but the AIG topology changes, and eSLIM's window-walking lands
in a different convergence basin. Longhorn never re-applied this technique
to the 64-gate netlist itself.

This driver:
  1. Parses /tmp/longhorn/fp4-multiplier/src/fp4_mul.blif into a gate list.
  2. Finds every XOR-of-XOR pattern (target XOR whose at least one input
     is also an XOR gate).
  3. For each, generates the rewritten netlist (algebraically equivalent).
  4. Flattens to .names BLIF via blif_to_aig.py.
  5. Runs eSLIM with 3 window sizes × 4 seeds.
  6. Translates output back to contest cells, counts gates.
  7. Reports any variant landing below 64 → WIN.

Run:
  python3 experiments_eslim/exp_a_xor_reassoc.py [--time-budget 300] [--max-variants 10]
"""
from __future__ import annotations
import argparse, subprocess, sys, os, time, json, shutil, traceback
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
LONGHORN = Path("/tmp/longhorn/fp4-multiplier")
ESLIM = Path("/tmp/eSLIM")
WORK = Path("/tmp/eslim_work")
WORK.mkdir(exist_ok=True)


# ─── BLIF parsing ──────────────────────────────────────────────────────────
def parse_gate_blif(path: Path):
    """Parse .gate-form BLIF. Returns (inputs, outputs, gates) where each
    gate is a dict {kind, ins, out}."""
    with open(path) as f:
        lines = f.read().splitlines()
    inputs, outputs, gates = [], [], []
    for ln in lines:
        ln = ln.strip()
        if not ln or ln.startswith("#"): continue
        if ln.startswith(".inputs"):
            inputs = ln.split()[1:]
        elif ln.startswith(".outputs"):
            outputs = ln.split()[1:]
        elif ln.startswith(".gate"):
            parts = ln.split()
            kind = parts[1]
            pinmap = {}
            for p in parts[2:]:
                k, v = p.split("=", 1)
                pinmap[k] = v
            if kind == "NOT1":
                gates.append({"kind": "NOT", "ins": [pinmap["A"]], "out": pinmap["Y"]})
            elif kind in ("AND2", "OR2", "XOR2"):
                gates.append({"kind": kind[:-1],
                              "ins": [pinmap["A"], pinmap["B"]],
                              "out": pinmap["Y"]})
            else:
                raise ValueError(f"unknown gate: {kind}")
    return inputs, outputs, gates


def write_gate_blif(path: Path, inputs, outputs, gates):
    """Write .gate-form BLIF in the contest format."""
    cell_map = {"NOT": "NOT1", "AND": "AND2", "OR": "OR2", "XOR": "XOR2"}
    with open(path, "w") as f:
        f.write(".model fp4_mul\n")
        f.write(".inputs " + " ".join(inputs) + "\n")
        f.write(".outputs " + " ".join(outputs) + "\n")
        for g in gates:
            cell = cell_map[g["kind"]]
            if g["kind"] == "NOT":
                f.write(f".gate {cell} A={g['ins'][0]} Y={g['out']}\n")
            else:
                f.write(f".gate {cell} A={g['ins'][0]} B={g['ins'][1]} Y={g['out']}\n")
        f.write(".end\n")


# ─── XOR-of-XOR enumeration ────────────────────────────────────────────────
def find_xor_xor_locations(gates):
    """Return list of (target_idx, xor_input_pos, parent_idx) where
    target_idx is the gate index of an XOR whose input at position
    xor_input_pos is the output of another XOR gate at parent_idx."""
    out_to_idx = {g["out"]: i for i, g in enumerate(gates)}
    locations = []
    for i, g in enumerate(gates):
        if g["kind"] != "XOR": continue
        for pos, inp in enumerate(g["ins"]):
            if inp in out_to_idx:
                p_idx = out_to_idx[inp]
                if gates[p_idx]["kind"] == "XOR":
                    locations.append((i, pos, p_idx))
    return locations


def reassoc_at(gates, target_idx, xor_input_pos, parent_idx):
    """Apply rewrite: target = XOR(parent_out, c) where parent = XOR(a, b)
    becomes target = XOR(a, NEW) where NEW = XOR(b, c).

    The parent gate is REPLACED by a new XOR(b, c) (renamed to a fresh
    wire 'reassoc_NN'), and the target gate is rewired to use (a, new_wire).
    If the parent has fanout > 1 (used elsewhere), we keep the original
    parent and add a new XOR gate.
    """
    g = gates[target_idx]
    parent = gates[parent_idx]
    # The "merged" XOR is g; parent's two inputs are a, b; g's "other" input
    # (not the parent.out reference) is c.
    other_pos = 1 - xor_input_pos
    a, b = parent["ins"]
    c = g["ins"][other_pos]

    # Check parent fanout
    fanout = sum(1 for gg in gates for ip in gg["ins"] if ip == parent["out"])
    # Also check primary outputs (not relevant here as parent is internal)

    new_gates = [dict(g_orig) for g_orig in gates]

    if fanout == 1:
        # In-place rewrite: parent gate now computes XOR(b, c) instead of XOR(a, b).
        new_wire = f"reassoc_{target_idx}_{parent_idx}"
        # Repurpose the parent gate
        new_gates[parent_idx] = {
            "kind": "XOR", "ins": [b, c], "out": new_wire
        }
        # Rewire the target gate
        new_gates[target_idx] = {
            "kind": "XOR", "ins": [a, new_wire], "out": g["out"]
        }
    else:
        # Parent is shared; introduce a new XOR for (b, c) and rewrite target only
        new_wire = f"reassoc_{target_idx}_{parent_idx}"
        new_gates.insert(target_idx, {
            "kind": "XOR", "ins": [b, c], "out": new_wire
        })
        # Rewire target (now at idx target_idx + 1)
        for i, gg in enumerate(new_gates):
            if gg["out"] == g["out"]:
                new_gates[i] = {
                    "kind": "XOR", "ins": [a, new_wire], "out": g["out"]
                }
                break

    return new_gates


# ─── eSLIM driver ──────────────────────────────────────────────────────────
def run_eslim(in_blif: Path, out_blif: Path, time_budget: int,
              size: int, seed: int) -> dict:
    """Run eSLIM on a flattened BLIF. Returns {gates_in, gates_out, ok, log}."""
    cmd = [
        sys.executable, str(ESLIM / "src/reduce.py"),
        str(in_blif), str(out_blif), str(time_budget),
        "--syn-mode", "sat",
        "--size", str(size),
        "--seed", str(seed),
    ]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ESLIM / "src/bindings/build")
    try:
        r = subprocess.run(cmd, env=env, capture_output=True, text=True,
                           timeout=time_budget + 30)
        log = (r.stderr or "") + (r.stdout or "")
    except subprocess.TimeoutExpired:
        return {"ok": False, "log": "subprocess timeout"}
    # Extract initial / final gate counts from stderr (eSLIM logs there)
    init_gates = final_gates = None
    for ln in log.splitlines():
        if "Initial #gates:" in ln and "Final #gates" in ln:
            # "INFO:root:Initial #gates: 64; Final #gates: 58"
            try:
                parts = ln.split("Initial #gates:")[1]
                init_gates = int(parts.split(";")[0].strip())
                final_gates = int(parts.split("Final #gates:")[1].strip())
            except Exception: pass
    return {
        "ok": r.returncode == 0 and final_gates is not None,
        "init_gates_internal": init_gates,
        "final_gates_internal": final_gates,
        "log_tail": log.splitlines()[-5:] if log else [],
    }


def flatten_blif(in_path: Path, out_path: Path):
    """Use Longhorn's blif_to_aig.py to flatten .gate BLIF to .names BLIF."""
    script = LONGHORN / "experiments_external/eslim/scripts/blif_to_aig.py"
    r = subprocess.run([sys.executable, str(script), str(in_path), str(out_path)],
                       capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"flatten failed: {r.stderr}")


def translate_to_gates(in_path: Path, out_path: Path,
                        in_names, out_names) -> int:
    """Use Longhorn's eslim_to_gates.py to translate .names back to .gate.
    Returns the contest cell count."""
    sys.path.insert(0, str(LONGHORN / "experiments_external/eslim/scripts"))
    try:
        # We import dynamically because the path is added at runtime
        from importlib import reload
        if "eslim_to_gates" in sys.modules:
            del sys.modules["eslim_to_gates"]
        import eslim_to_gates as m
        m.main(str(in_path), str(out_path), in_names, out_names)
    finally:
        if str(LONGHORN / "experiments_external/eslim/scripts") in sys.path:
            sys.path.remove(str(LONGHORN / "experiments_external/eslim/scripts"))
    # Count .gate lines
    n = 0
    with open(out_path) as f:
        for ln in f:
            if ln.strip().startswith(".gate"): n += 1
    return n


# ─── Main driver ──────────────────────────────────────────────────────────
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--time-budget", type=int, default=120,
                    help="Per-eSLIM-run time budget (seconds). Default 120.")
    ap.add_argument("--sizes", type=int, nargs="+", default=[6, 8])
    ap.add_argument("--seeds", type=int, nargs="+", default=[1, 42, 7777, 13371337])
    ap.add_argument("--max-variants", type=int, default=20,
                    help="Cap number of XOR-XOR variants to try.")
    ap.add_argument("--canonical", default=str(LONGHORN / "src/fp4_mul.blif"))
    ap.add_argument("--ledger", default=str(REPO / "experiments_eslim/exp_a_ledger.tsv"))
    args = ap.parse_args()

    print(f"Reading canonical: {args.canonical}")
    inputs, outputs, gates = parse_gate_blif(Path(args.canonical))
    base_count = len(gates)
    print(f"  inputs: {inputs}")
    print(f"  outputs: {outputs}")
    print(f"  gates: {base_count}")

    print()
    locs = find_xor_xor_locations(gates)
    print(f"XOR-of-XOR rewrite locations: {len(locs)}")
    for li, (t, p, par) in enumerate(locs[:30]):
        print(f"  loc#{li}: target {gates[t]['out']} XOR <- "
              f"({gates[t]['ins']}) parent {gates[par]['out']}")

    # Open ledger
    Path(args.ledger).parent.mkdir(parents=True, exist_ok=True)
    if not Path(args.ledger).exists():
        with open(args.ledger, "w") as f:
            f.write("\t".join([
                "ts","variant","size","seed","init_internal",
                "final_internal","contest_cells","ok"
            ]) + "\n")

    best = base_count
    best_variant = None
    t_start = time.time()
    n_runs = 0
    in_names = inputs[:]
    out_names = outputs[:]

    for li, (t, p, par) in enumerate(locs[:args.max_variants]):
        print(f"\n=== Variant {li+1}/{min(len(locs), args.max_variants)}: "
              f"reassoc at target={gates[t]['out']} parent={gates[par]['out']} ===")
        # Build perturbed BLIF
        try:
            perturbed = reassoc_at(gates, t, p, par)
        except Exception as e:
            print(f"  reassoc failed: {e}")
            continue

        var_blif = WORK / f"var_{li:03d}.blif"
        flat_blif = WORK / f"var_{li:03d}_flat.blif"
        write_gate_blif(var_blif, inputs, outputs, perturbed)
        try:
            flatten_blif(var_blif, flat_blif)
        except Exception as e:
            print(f"  flatten failed: {e}")
            continue

        for size in args.sizes:
            for seed in args.seeds:
                out_eslim = WORK / f"var_{li:03d}_s{size}_seed{seed}_out.blif"
                t0 = time.time()
                res = run_eslim(flat_blif, out_eslim, args.time_budget, size, seed)
                dt = time.time() - t0
                contest = None
                if res["ok"]:
                    try:
                        out_gate = WORK / f"var_{li:03d}_s{size}_seed{seed}_gates.blif"
                        contest = translate_to_gates(out_eslim, out_gate,
                                                      in_names, out_names)
                    except Exception as e:
                        print(f"  translate failed: {e}")

                row = [
                    time.strftime("%H:%M:%S"),
                    f"loc{li}",
                    str(size), str(seed),
                    str(res.get("init_gates_internal","?")),
                    str(res.get("final_gates_internal","?")),
                    str(contest if contest is not None else "?"),
                    "OK" if res["ok"] else "FAIL"
                ]
                with open(args.ledger, "a") as f:
                    f.write("\t".join(row) + "\n")

                marker = ""
                if contest is not None and contest < best:
                    best = contest
                    best_variant = (li, size, seed, str(out_gate))
                    marker = "  *** NEW BEST ***"
                print(f"  size={size} seed={seed}: "
                      f"internal {res.get('init_gates_internal','?')}->{res.get('final_gates_internal','?')}, "
                      f"contest={contest} ({dt:.1f}s){marker}", flush=True)
                n_runs += 1
                if best < base_count:
                    print(f"\nBREAKTHROUGH at run {n_runs}! contest={best}")
                    print(f"  variant: loc#{best_variant[0]}, size={best_variant[1]}, "
                          f"seed={best_variant[2]}")
                    print(f"  saved as: {best_variant[3]}")

    elapsed = time.time() - t_start
    print()
    print("=" * 60)
    print(f"Experiment A complete. Runs: {n_runs}, elapsed: {elapsed:.1f}s")
    print(f"Best contest cells: {best} (baseline {base_count})")
    if best < base_count:
        print(f"  *** SUB-{base_count} ACHIEVED ***")
        print(f"  variant: {best_variant}")
    else:
        print("  No sub-64 variant found in this sweep.")


if __name__ == "__main__":
    main()
