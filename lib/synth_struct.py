"""Synthesize the structural Verilog (`fp4_mul_struct.v`) under various ABC
script variants and compare gate counts."""
from __future__ import annotations
import re
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

from verify import verify_blif

CODE = Path(__file__).resolve().parent
LIB = CODE / "contest.lib"
STRUCT_V = CODE / "fp4_mul_struct.v"


RESYN2 = "balance; rewrite; refactor; balance; rewrite; rewrite -z; balance; refactor -z; rewrite -z; balance"
RESYN3 = "balance; resub; resub -K 6; balance; resub -z; resub -z -K 6; balance; resub -z -K 5; balance"
COMPRESS2 = "balance -l; rewrite -l; refactor -l; balance -l; rewrite -l; rewrite -z -l; balance -l; refactor -z -l; rewrite -z -l; balance -l"

SCRIPTS = {
    "fast":               "strash; ifraig; scorr; dc2; strash; dch -f; map -a -B 0",
    "med":                f"strash; ifraig; scorr; dc2; strash; {RESYN2}; {RESYN2}; {RESYN2}; logic; mfs2; strash; dch -f; map -a -B 0",
    "med+resyn3":         f"strash; ifraig; scorr; dc2; strash; {RESYN2}; {RESYN3}; {RESYN2}; {RESYN3}; logic; mfs2; strash; dch -f; map -a -B 0",
    "compress2x3":        f"strash; ifraig; scorr; dc2; strash; {COMPRESS2}; {COMPRESS2}; {COMPRESS2}; logic; mfs2; strash; dch -f; map -a -B 0",
    "deepsyn-3s":         f"strash; ifraig; scorr; dc2; strash; {RESYN2}; &get -n; &deepsyn -T 3 -I 4; &put; logic; mfs2; strash; dch -f; map -a -B 0",
    "deepsyn-10s":        f"strash; ifraig; scorr; dc2; strash; {RESYN2}; &get -n; &deepsyn -T 10 -I 6; &put; logic; mfs2; strash; dch -f; map -a -B 0",
    "deepsyn-30s":        f"strash; ifraig; scorr; dc2; strash; {RESYN2}; &get -n; &deepsyn -T 30 -I 8; &put; logic; mfs2; strash; dch -f; map -a -B 0",
    "if-K6":              f"strash; ifraig; scorr; dc2; strash; {RESYN2}; if -K 6 -a; mfs2; strash; dch -f; map -a -B 0",
    "double-rs":          f"strash; ifraig; scorr; dc2; strash; {RESYN2}; {RESYN3}; mfs2 -W 4 -F 4; strash; {RESYN2}; {RESYN3}; mfs2 -W 4 -F 4; strash; dch -f; map -a -B 0",
}


def run_one(name: str, abc_script: str, src: Path = STRUCT_V, timeout: int = 90) -> dict:
    with tempfile.TemporaryDirectory(prefix="fp4s_", dir="/tmp") as td:
        td = Path(td)
        shutil.copy(src, td / "fp4_mul.v")
        shutil.copy(LIB, td / "contest.lib")
        yscr = "+" + abc_script.strip().replace(" ", ",")
        (td / "synth.ys").write_text(
            f"read_verilog {td}/fp4_mul.v\n"
            f"hierarchy -top fp4_mul\n"
            f"proc; opt; memory; opt; flatten; opt -full; techmap; opt\n"
            f"abc -liberty {td}/contest.lib -script {yscr}\n"
            f"write_blif {td}/out.blif\n"
            f"stat -liberty {td}/contest.lib\n"
        )
        t0 = time.time()
        try:
            r = subprocess.run(
                ["yosys", str(td / "synth.ys")],
                capture_output=True, text=True, cwd=str(td), timeout=timeout,
            )
        except subprocess.TimeoutExpired:
            return {"name": name, "gates": None, "verify": False, "wall": timeout, "error": "timeout"}
        wall = time.time() - t0
        m = re.findall(r"Chip area for module '\\?fp4_mul':\s*([0-9.]+)", r.stdout)
        gates = int(round(float(m[-1]))) if m else None
        blif = td / "out.blif"
        ok = False
        if blif.exists():
            ok, _ = verify_blif(blif)
        return {"name": name, "gates": gates, "verify": ok, "wall": wall}


def main():
    print(f"{'name':18s} {'gates':>6}  {'verify':>6}  {'wall':>6}")
    print("-" * 50)
    for name, scr in SCRIPTS.items():
        r = run_one(name, scr, timeout=120)
        v = "OK" if r["verify"] else "FAIL"
        g = r.get("gates", "—")
        print(f"{name:18s} {g!s:>6}  {v:>6}  {r['wall']:>6.1f}")


if __name__ == "__main__":
    main()
