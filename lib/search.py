"""Drive the synthesis-over-remaps search. Single-process, sequential. Logs
   each experiment to results.tsv. Verifies every candidate with verify_blif.
"""
from __future__ import annotations
import argparse
import csv
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

from fp4_spec import DEFAULT_FP4_VALUES
from synth import synthesize as synthesize_pla
from synth_v import synthesize_v
from verify import verify_blif

REPO = Path(__file__).resolve().parent.parent
LEDGER = REPO / "results.tsv"
ARTIFACT_DIR = REPO / "synth_artifacts"


# yosys-abc uses its own tempdir and doesn't auto-load our abc.rc, so any
# ABC alias (resyn2, resyn3, …) must be inlined. The expansions below match
# upstream berkeley-abc/abc abc.rc.
RESYN2 = "balance; rewrite; refactor; balance; rewrite; rewrite -z; balance; refactor -z; rewrite -z; balance"

# Three preset ABC command sequences, ordered by effort. All use {AND, OR,
# XOR, NOT} mapping via `map -a -B 0` (area-priority, no buffer insertion).
FAST_SCRIPT = (
    "strash; ifraig; scorr; dc2; dretime; strash; "
    "&get -n; &fraig -x; &put; "
    "scleanup; dch -f; map -a -B 0"
)

MED_SCRIPT = (
    "strash; ifraig; scorr; dc2; dretime; strash; "
    f"{RESYN2}; {RESYN2}; {RESYN2}; "
    "&get -n; &deepsyn -T 20 -I 6; &put; "
    "logic; mfs2; strash; "
    "dch -f; map -a -B 0"
)

STRONG_SCRIPT = (
    "strash; ifraig; scorr; dc2; dretime; strash; "
    f"{RESYN2}; {RESYN2}; {RESYN2}; "
    "&get -n; &deepsyn -T 60 -I 12; &put; "
    "logic; mfs2 -W 4 -F 4; strash; "
    "dch -f; map -a -B 0"
)


def write_ledger_header():
    if LEDGER.exists():
        return
    with open(LEDGER, "w", newline="") as f:
        w = csv.writer(f, delimiter="\t")
        w.writerow([
            "ts", "name", "script", "perm",
            "status", "gates", "wall_sec", "blif_path", "notes",
        ])


def append_ledger(row):
    with open(LEDGER, "a", newline="") as f:
        w = csv.writer(f, delimiter="\t")
        w.writerow(row)


def run_one(name: str, values: list[float], script: str,
            perm_str: str, timeout: int = 90,
            backend: str = "verilog") -> dict:
    """Synthesize one candidate. backend='verilog' uses synth_v (recommended);
    backend='pla' uses synth (PLA -> ABC, more brittle)."""
    t0 = time.time()
    try:
        if backend == "verilog":
            r = synthesize_v(values, abc_script=script, timeout=timeout)
        else:
            r = synthesize_pla(values, abc_script=script, keep=False, timeout=timeout)
    except subprocess.TimeoutExpired:
        wall = time.time() - t0
        return {"name": name, "status": "timeout", "gates": -1,
                "wall_sec": wall, "notes": "synthesizer timeout"}
    wall = time.time() - t0

    if r["gates"] is None:
        return {"name": name, "status": "synth_failed", "gates": -1,
                "wall_sec": wall, "notes": "no gates parsed",
                "log_tail": "\n".join(r["log"].splitlines()[-15:])}

    # Verify by saving and re-reading the BLIF.
    blif_path = ARTIFACT_DIR / f"{name}.blif"
    ARTIFACT_DIR.mkdir(exist_ok=True)
    blif_path.write_text(r["netlist"])
    ok, mism = verify_blif(blif_path, values=values)
    if not ok:
        return {"name": name, "status": "verify_failed",
                "gates": r["gates"], "wall_sec": wall,
                "notes": f"{len(mism)} mismatches",
                "blif_path": str(blif_path)}
    return {"name": name, "status": "ok", "gates": r["gates"],
            "wall_sec": wall, "notes": "",
            "blif_path": str(blif_path)}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--candidates", default="from-strategy",
                   help="'from-strategy' (use code/strategy.py::propose) or "
                        "'sign-symmetric:N' to enumerate first N sign-symmetric "
                        "remaps with FAST_SCRIPT")
    p.add_argument("--script", default="fast",
                   choices=["fast", "med", "strong"],
                   help="ABC script preset")
    p.add_argument("--backend", default="verilog",
                   choices=["verilog", "pla"],
                   help="Synthesis input format")
    p.add_argument("--timeout", type=int, default=90)
    args = p.parse_args()

    write_ledger_header()

    if args.candidates == "from-strategy":
        sys.path.insert(0, str(Path(__file__).parent))
        from strategy import propose
        candidates = list(propose())
    elif args.candidates.startswith("sign-symmetric:"):
        from remap import sign_symmetric_remaps
        n = int(args.candidates.split(":")[1])
        candidates = []
        for i, (perm, values) in enumerate(sign_symmetric_remaps()):
            if i >= n:
                break
            candidates.append((f"ss_{perm}", values, None))
    else:
        raise SystemExit(f"Unknown --candidates: {args.candidates}")

    script_map = {"fast": FAST_SCRIPT, "med": MED_SCRIPT, "strong": STRONG_SCRIPT}
    default_script = script_map[args.script]

    best = None
    print(f"Running {len(candidates)} candidates with default script={args.script}")
    print(f"Logging to {LEDGER}")

    for name, values, script_override in candidates:
        script = script_override or default_script
        perm_str = ",".join(f"{v:g}" for v in values)
        r = run_one(name, values, script, perm_str, timeout=args.timeout,
                    backend=args.backend)
        ts = time.strftime("%Y-%m-%dT%H:%M:%S")
        append_ledger([
            ts, name, args.script, perm_str,
            r["status"], r.get("gates", -1), f"{r['wall_sec']:.1f}",
            r.get("blif_path", ""), r.get("notes", ""),
        ])
        gates = r.get("gates", -1)
        marker = ""
        if r["status"] == "ok" and (best is None or gates < best):
            best = gates
            marker = "  *NEW BEST*"
        print(f"  {name:30s}  status={r['status']:14s} gates={gates}  "
              f"({r['wall_sec']:.1f}s){marker}")

    if best is not None:
        print(f"\nBest gate count this run: {best}")
    else:
        print("\nNo successful candidate this run.")


if __name__ == "__main__":
    main()
