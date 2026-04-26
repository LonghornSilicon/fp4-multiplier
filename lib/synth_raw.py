"""Synthesize a raw-bit Verilog (per-remap) via yosys + ABC."""
from __future__ import annotations
import re, shutil, subprocess, tempfile, time
from pathlib import Path
from gen_raw import emit_raw_verilog
from verify import verify_blif

CODE = Path(__file__).resolve().parent
LIB = CODE / "contest.lib"

RESYN2 = "balance; rewrite; refactor; balance; rewrite; rewrite -z; balance; refactor -z; rewrite -z; balance"


def synthesize_raw(values: list[float], abc_script: str | None = None,
                   timeout: int = 30) -> dict:
    if abc_script is None:
        abc_script = (f"strash; ifraig; scorr; dc2; strash; "
                      f"{RESYN2}; "
                      f"&get -n; &deepsyn -T 3 -I 4; &put; "
                      f"logic; mfs2; strash; "
                      f"dch -f; map -a -B 0")
    verilog = emit_raw_verilog(values)
    with tempfile.TemporaryDirectory(prefix="raw_", dir="/tmp") as td:
        td = Path(td)
        (td / "fp4_mul.v").write_text(verilog)
        shutil.copy(LIB, td / "contest.lib")
        yscr = "+" + abc_script.strip().replace(" ", ",")
        (td / "synth.ys").write_text(
            f"read_verilog {td}/fp4_mul.v\n"
            f"hierarchy -top fp4_mul\n"
            f"proc; opt; flatten; opt -full; techmap; opt\n"
            f"abc -liberty {td}/contest.lib -script {yscr}\n"
            f"write_blif {td}/out.blif\n"
            f"stat -liberty {td}/contest.lib\n"
        )
        t0 = time.time()
        try:
            r = subprocess.run(["yosys", str(td / "synth.ys")],
                               capture_output=True, text=True, cwd=str(td),
                               timeout=timeout)
        except subprocess.TimeoutExpired:
            return {"gates": None, "wall": timeout, "verify": False}
        wall = time.time() - t0
        m = re.findall(r"Chip area for module '\\?fp4_mul':\s*([0-9.]+)", r.stdout)
        gates = int(round(float(m[-1]))) if m else None
        blif = td / "out.blif"
        ok = False
        netlist_text = ""
        if blif.exists():
            ok, _ = verify_blif(blif, values=values)
            netlist_text = blif.read_text()
        return {"gates": gates, "wall": wall, "verify": ok,
                "verilog": verilog, "netlist": netlist_text,
                "log": r.stdout + r.stderr}


if __name__ == "__main__":
    from remap import encoding_from_magnitude_perm
    v = encoding_from_magnitude_perm((0,1,2,3,6,7,4,5))
    r = synthesize_raw(v)
    print(f"gates={r['gates']} verify={'OK' if r['verify'] else 'FAIL'}")
