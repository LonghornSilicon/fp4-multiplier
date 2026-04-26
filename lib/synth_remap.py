"""Synthesize a structural FP4 multiplier under any input remap.

Given a `values` list[16], emits a structurally-decomposed Verilog with a
per-remap decoder + a fixed sign-magnitude multiplier core, then runs
yosys + ABC under the contest gate library.
"""
from __future__ import annotations
import re
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

from fp4_spec import DEFAULT_FP4_VALUES
from gen_struct import emit_struct_verilog_with_remap
from verify import verify_blif

CODE = Path(__file__).resolve().parent
LIB = CODE / "contest.lib"

RESYN2 = "balance; rewrite; refactor; balance; rewrite; rewrite -z; balance; refactor -z; rewrite -z; balance"


def synthesize_remap(values: list[float], abc_script: str | None = None,
                     timeout: int = 30,
                     keep_dir: Path | None = None) -> dict:
    if abc_script is None:
        abc_script = (
            f"strash; ifraig; scorr; dc2; strash; "
            f"{RESYN2}; "
            f"&get -n; &deepsyn -T 3 -I 4; &put; "
            f"logic; mfs2; strash; "
            f"dch -f; map -a -B 0"
        )

    verilog = emit_struct_verilog_with_remap(values)
    with tempfile.TemporaryDirectory(prefix="fp4_remap_", dir="/tmp") as td:
        td = Path(td)
        v_path = td / "fp4_mul.v"
        blif = td / "out.blif"
        v_path.write_text(verilog)
        shutil.copy(LIB, td / "contest.lib")
        yscr = "+" + abc_script.strip().replace(" ", ",")
        (td / "synth.ys").write_text(
            f"read_verilog {v_path}\n"
            f"hierarchy -top fp4_mul\n"
            f"proc; opt; flatten; opt -full; techmap; opt\n"
            f"abc -liberty {td}/contest.lib -script {yscr}\n"
            f"write_blif {blif}\n"
            f"stat -liberty {td}/contest.lib\n"
        )
        t0 = time.time()
        try:
            r = subprocess.run(
                ["yosys", str(td / "synth.ys")],
                capture_output=True, text=True, cwd=str(td), timeout=timeout,
            )
        except subprocess.TimeoutExpired:
            return {"gates": None, "wall": timeout, "verify": False, "verilog": verilog,
                    "log": "TIMEOUT"}
        wall = time.time() - t0
        m = re.findall(r"Chip area for module '\\?fp4_mul':\s*([0-9.]+)", r.stdout)
        gates = int(round(float(m[-1]))) if m else None
        ok = False
        if blif.exists():
            ok, _ = verify_blif(blif, values=values)
        if keep_dir is not None:
            keep_dir.mkdir(exist_ok=True)
            for f in td.iterdir():
                if f.is_file():
                    shutil.copy(f, keep_dir / f.name)
        return {"gates": gates, "wall": wall, "verify": ok,
                "verilog": verilog, "log": r.stdout + r.stderr,
                "blif_text": blif.read_text() if blif.exists() else None}


def _self_test():
    print("Sanity: default encoding via gen_struct (should match struct.v ≈ 86).")
    r = synthesize_remap(DEFAULT_FP4_VALUES, timeout=30)
    print(f"  gates={r['gates']}  verify={'OK' if r['verify'] else 'FAIL'}  ({r['wall']:.1f}s)")


if __name__ == "__main__":
    _self_test()
