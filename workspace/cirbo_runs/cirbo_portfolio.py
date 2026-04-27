"""Portfolio Cirbo SAT campaign: try multiple SAT solvers in parallel for the
same target G. First to return SAT/UNSAT wins; rest are killed.

Design rationale (Karpathy autoresearch):
  * Single scalar metric: Gate count G (we go down).
  * Frozen verifier: lib/verify.py + lib/fp4_spec.py.
  * Frozen evaluation: cirbo CircuitFinderSat. SAT outcome is "found <=G".
  * Multi-process portfolio over different SAT solvers — different solvers
    have radically different search heuristics; one will often crack a hard
    instance the others can't.
  * TSV ledger of all attempts so we can prove what was tried.

Each (G, solver) combination is one experiment. We run them in parallel
across cores. Time budget per experiment is fixed.
"""
from __future__ import annotations
import argparse
import csv
import multiprocessing as mp
import os
import signal
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO / "lib"))

# These imports happen inside subprocesses; avoid importing in the parent
# unless needed (cirbo state can pin shared memory).


SOLVERS = [
    "cadical195",   # SOTA modern CaDiCaL
    "cadical153",   # Older CaDiCaL — different bug profile
    "lingeling",    # Lingeling — known good on UNSAT instances
    "minisatgh",    # MiniSat-GH — classical baseline
    "glucose42",    # Glucose 4.2 — strong on industrial instances
    "maplecm",      # MapleCM — often fastest on SAT
    "mergesat3",    # MergeSat3 — strong portfolio member
]


def worker(G, solver_name, perm_str, time_budget, log_dir, q):
    """Run one Cirbo CircuitFinderSat at G with given solver."""
    try:
        from cirbo.core.truth_table import TruthTableModel
        from cirbo.synthesis.circuit_search import CircuitFinderSat, Operation
        from fp4_spec import per_output_bit_truth_tables
        from remap import encoding_from_magnitude_perm

        OUR_BASIS = [Operation.and_, Operation.or_, Operation.xor_, Operation.lnot_]
        perm = tuple(int(x) for x in perm_str.split(","))
        values = encoding_from_magnitude_perm(perm)
        table = [[bool((tt >> i) & 1) for i in range(256)]
                 for tt in per_output_bit_truth_tables(values)]
        model = TruthTableModel(table)

        t0 = time.time()
        finder = CircuitFinderSat(boolean_function_model=model,
                                  number_of_gates=G, basis=OUR_BASIS)
        try:
            circuit = finder.find_circuit(solver_name=solver_name,
                                          time_limit=time_budget)
            wall = time.time() - t0
            # Save the circuit so we can verify
            cir_path = log_dir / f"G{G}_{solver_name}_circuit.txt"
            try:
                with open(cir_path, "w") as f:
                    f.write(repr(circuit))
            except Exception:
                pass
            q.put(("SAT", G, solver_name, wall))
        except Exception as e:
            wall = time.time() - t0
            ename = type(e).__name__
            if "NoSolution" in ename:
                q.put(("UNSAT", G, solver_name, wall))
            elif "TimeOut" in ename or "Timeout" in ename:
                q.put(("TIMEOUT", G, solver_name, wall))
            else:
                q.put(("ERROR", G, solver_name, wall, ename, str(e)[:120]))
    except Exception as outer:
        q.put(("CRASH", G, solver_name, 0.0, type(outer).__name__, str(outer)[:120]))


def run_portfolio(G, perm_str, time_budget, log_dir, ledger_path, solvers=SOLVERS):
    """Run all solvers in parallel on same G; first verdict wins; kill rest."""
    log_dir.mkdir(parents=True, exist_ok=True)
    q = mp.Queue()
    procs = []
    for s in solvers:
        p = mp.Process(target=worker,
                       args=(G, s, perm_str, time_budget, log_dir, q))
        p.start()
        procs.append((s, p))

    print(f"[G={G}] launched {len(procs)} solvers in portfolio (budget {time_budget}s/each)", flush=True)
    finished = 0
    sat_seen = False
    unsat_seen = False
    first_verdict = None
    first_solver = None
    first_wall = None
    results = []
    deadline = time.time() + time_budget + 30
    while finished < len(procs) and time.time() < deadline:
        try:
            r = q.get(timeout=5)
        except Exception:
            # Periodic check — kill stuck procs once we have a definitive verdict
            if first_verdict in ("SAT", "UNSAT"):
                break
            continue
        finished += 1
        verdict = r[0]
        wall = r[3] if len(r) >= 4 else None
        results.append(r)
        print(f"  G={G} {r[2]:>12s}: {verdict:>8s} ({wall:.1f}s)" if wall else f"  G={G} {r[2]:>12s}: {verdict}", flush=True)
        if verdict == "SAT" and not sat_seen:
            sat_seen = True
            first_verdict = "SAT"
            first_solver = r[2]
            first_wall = wall
            break  # SAT proves <=G, stop the portfolio
        if verdict == "UNSAT" and not unsat_seen:
            unsat_seen = True
            if first_verdict is None:
                first_verdict = "UNSAT"
                first_solver = r[2]
                first_wall = wall

    # Terminate stragglers
    for s, p in procs:
        if p.is_alive():
            try:
                p.terminate()
                p.join(timeout=3)
                if p.is_alive():
                    p.kill()
                    p.join(timeout=3)
            except Exception:
                pass

    # Drain queue for any late results
    drained = 0
    while not q.empty() and drained < len(procs):
        try:
            r = q.get_nowait()
            results.append(r)
            drained += 1
        except Exception:
            break

    write_results(ledger_path, G, perm_str, time_budget, results, first_verdict,
                  first_solver, first_wall)
    return first_verdict, first_solver


def write_results(ledger_path, G, perm_str, budget, results, first_verdict,
                  first_solver, first_wall):
    new = not Path(ledger_path).exists()
    with open(ledger_path, "a", newline="") as f:
        w = csv.writer(f, delimiter="\t")
        if new:
            w.writerow(["ts", "G", "perm", "budget_s", "first_verdict",
                        "first_solver", "first_wall_s", "all_results"])
        all_str = ";".join(f"{r[2]}={r[0]}@{(r[3] if len(r)>3 else 0):.0f}s"
                           for r in results)
        w.writerow([int(time.time()), G, perm_str, budget,
                    first_verdict or "INDETERMINATE",
                    first_solver or "",
                    f"{first_wall:.1f}" if first_wall is not None else "",
                    all_str])


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--start-G", type=int, default=64)
    p.add_argument("--floor-G", type=int, default=58)
    p.add_argument("--budget", type=int, default=3600,
                   help="per-G budget across all solvers (seconds)")
    p.add_argument("--perm", type=str, default="0,1,2,3,6,7,4,5")
    p.add_argument("--solvers", type=str, default=",".join(SOLVERS))
    p.add_argument("--log-dir", type=str,
                   default="/home/shadeform/fp4-multiplier/workspace/cirbo_runs")
    p.add_argument("--ledger", type=str,
                   default="/home/shadeform/fp4-multiplier/workspace/cirbo_runs/cirbo_ledger.tsv")
    args = p.parse_args()
    log_dir = Path(args.log_dir)
    ledger = Path(args.ledger)
    solvers = [s.strip() for s in args.solvers.split(",") if s.strip()]

    G = args.start_G
    while G >= args.floor_G:
        verdict, solver = run_portfolio(G, args.perm, args.budget, log_dir,
                                         ledger, solvers=solvers)
        if verdict == "SAT":
            print(f"\n+++ FOUND CIRCUIT AT G={G} (solver={solver}) +++", flush=True)
            print("Decreasing G by 1, retrying portfolio.", flush=True)
            G -= 1
            continue
        if verdict == "UNSAT":
            print(f"\n*** PROVEN: minimum gate count >= {G+1} (solver={solver}) ***", flush=True)
            return
        # All TIMEOUT / INDETERMINATE
        print(f"\n[G={G}] indeterminate after portfolio; abandoning at this level.",
              flush=True)
        return


if __name__ == "__main__":
    main()
