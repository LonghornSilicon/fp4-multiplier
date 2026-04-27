"""Single eSLIM experiment runner — Karpathy-autoresearch style.

Usage: sweep_run.py <ledger_tsv> <run_id> <start_blif> <size> <restarts>
                    <limit_inputs> <seed> <budget>

Procedure (frozen):
  1. Translate start_blif to flat .names form (input to eSLIM).
  2. Run eSLIM with the given parameters.
  3. Translate eSLIM internal output back to contest cells using both
     the legacy translator and the v2 translator; keep the better one.
  4. Verify the output passes verify_blif under sigma=(0,1,2,3,6,7,4,5).
  5. Append a row to ledger_tsv with timestamp, params, internal_count,
     contest_count, cell mix, verify status.

The verifier (lib/verify.py) and the spec (lib/fp4_spec.py) are FROZEN —
we never modify them. Any verify failure is a hard halt for that experiment.
"""
from __future__ import annotations
import csv
import os
import re
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
WORKSPACE = REPO / "workspace" / "eslim_runs"
sys.path.insert(0, str(REPO / "lib"))
from verify import verify_blif
from remap import encoding_from_magnitude_perm
import eslim_translator2

ESLIM_BINDINGS = "/home/shadeform/eslim/src/bindings/build"
ESLIM_REDUCE = "/home/shadeform/eslim/src/reduce.py"
LEGACY_TRANSLATOR = REPO / "experiments_external/eslim/scripts/eslim_to_gates.py"
BLIF_TO_AIG = REPO / "experiments_external/eslim/scripts/blif_to_aig.py"

VALUES = encoding_from_magnitude_perm((0, 1, 2, 3, 6, 7, 4, 5))
IN_NAMES = ['a[0]', 'a[1]', 'a[2]', 'a[3]', 'b[0]', 'b[1]', 'b[2]', 'b[3]']
OUT_NAMES = [f'y[{k}]' for k in range(9)]


def count_cells(blif_path: Path):
    counts = {'AND2': 0, 'OR2': 0, 'XOR2': 0, 'NOT1': 0}
    text = Path(blif_path).read_text()
    for line in text.splitlines():
        line = line.strip()
        for k in counts:
            if line.startswith(f'.gate {k} ') or line.startswith(f'.subckt {k} '):
                counts[k] += 1
                break
    return counts, sum(counts.values())


def main():
    if len(sys.argv) != 9:
        print("usage: sweep_run.py <ledger.tsv> <run_id> <start.blif> <size> <restarts> <limit_inputs|none> <seed> <budget_s>")
        sys.exit(1)
    ledger_path = Path(sys.argv[1])
    run_id = sys.argv[2]
    start_blif = Path(sys.argv[3])
    size = int(sys.argv[4])
    restarts = int(sys.argv[5])
    limit_inputs = sys.argv[6]
    seed = int(sys.argv[7])
    budget = int(sys.argv[8])

    out_dir = WORKSPACE / "outputs"
    out_dir.mkdir(parents=True, exist_ok=True)
    flat_blif = out_dir / f"{run_id}_flat.blif"
    eslim_out = out_dir / f"{run_id}_eslim.blif"
    contest_legacy = out_dir / f"{run_id}_legacy.blif"
    contest_v2 = out_dir / f"{run_id}_v2.blif"
    log_path = out_dir / f"{run_id}.log"

    t0 = time.time()
    status = "ok"
    note = ""

    # 1. Flatten input BLIF
    PY = "/home/shadeform/.venv-fp4/bin/python3"
    r = subprocess.run([PY, str(BLIF_TO_AIG), str(start_blif), str(flat_blif)],
                       capture_output=True, text=True)
    if r.returncode != 0:
        status = "flatten_fail"
        note = r.stderr[-200:].replace("\n", " ")
        write_row(ledger_path, run_id, start_blif.name, size, restarts,
                  limit_inputs, seed, budget, None, None, None, status, note,
                  time.time() - t0)
        return

    # 2. Run eSLIM (use venv python so bitarray etc. are available)
    PY = "/home/shadeform/.venv-fp4/bin/python3"
    cmd = [PY, str(ESLIM_REDUCE), str(flat_blif), str(eslim_out),
           str(budget), "--syn-mode", "sat", "--size", str(size)]
    if restarts > 0:
        cmd += ["--restarts", str(restarts)]
    if limit_inputs.lower() != "none":
        cmd += ["--limit-inputs", limit_inputs]
    if seed > 0:
        cmd += ["--seed", str(seed)]

    env = os.environ.copy()
    env["PYTHONPATH"] = ESLIM_BINDINGS
    with open(log_path, "wb") as logf:
        try:
            proc = subprocess.run(cmd, env=env, stdout=logf, stderr=subprocess.STDOUT,
                                  timeout=budget + 600)
        except subprocess.TimeoutExpired:
            status = "eslim_timeout"
            note = f"hard timeout at {budget+600}s"
            write_row(ledger_path, run_id, start_blif.name, size, restarts,
                      limit_inputs, seed, budget, None, None, None, status, note,
                      time.time() - t0)
            return
    if not eslim_out.exists():
        status = "eslim_no_output"
        write_row(ledger_path, run_id, start_blif.name, size, restarts,
                  limit_inputs, seed, budget, None, None, None, status, note,
                  time.time() - t0)
        return

    # Parse internal gate count
    log_txt = Path(log_path).read_text()
    m = re.search(r"Final #gates:\s*(\d+)", log_txt)
    internal = int(m.group(1)) if m else None

    # 3. Translate via both
    best_blif = None
    best_count = None
    best_mix = None
    best_translator = None

    for translator_name, blif_out in (("legacy", contest_legacy), ("v2", contest_v2)):
        try:
            if translator_name == "legacy":
                subprocess.run(["/home/shadeform/.venv-fp4/bin/python3", str(LEGACY_TRANSLATOR),
                                str(eslim_out), str(blif_out)],
                               capture_output=True, text=True, check=True)
            else:
                eslim_translator2.translate(str(eslim_out), str(blif_out),
                                            IN_NAMES, OUT_NAMES)
            counts, total = count_cells(blif_out)
            ok, _ = verify_blif(str(blif_out), values=VALUES)
            if not ok:
                continue
            if best_count is None or total < best_count:
                best_count = total
                best_blif = blif_out
                best_mix = counts
                best_translator = translator_name
        except Exception as e:
            continue

    if best_count is None:
        status = "translate_fail"
        write_row(ledger_path, run_id, start_blif.name, size, restarts,
                  limit_inputs, seed, budget, internal, None, None, status, note,
                  time.time() - t0)
        return

    note = f"translator={best_translator}"
    write_row(ledger_path, run_id, start_blif.name, size, restarts,
              limit_inputs, seed, budget, internal, best_count, best_mix,
              status, note, time.time() - t0)


def write_row(ledger_path, run_id, start, size, restarts, limit_inputs, seed,
              budget, internal, contest, mix, status, note, wall):
    new = not Path(ledger_path).exists()
    with open(ledger_path, "a", newline="") as f:
        w = csv.writer(f, delimiter="\t")
        if new:
            w.writerow(["ts", "run_id", "start", "size", "restarts",
                        "limit_inputs", "seed", "budget_s", "internal",
                        "contest", "and2", "or2", "xor2", "not1",
                        "status", "note", "wall_s"])
        and2 = mix.get('AND2', '') if mix else ''
        or2 = mix.get('OR2', '') if mix else ''
        xor2 = mix.get('XOR2', '') if mix else ''
        not1 = mix.get('NOT1', '') if mix else ''
        w.writerow([int(time.time()), run_id, start, size, restarts,
                    limit_inputs, seed, budget, internal or '',
                    contest or '', and2, or2, xor2, not1,
                    status, note, f"{wall:.1f}"])


if __name__ == "__main__":
    main()
