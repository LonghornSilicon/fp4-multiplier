"""End-to-end synthesis pipeline:
   (1) accept a remap (or default),
   (2) emit per-output truth table as a PLA / BLIF,
   (3) shell out to yosys-abc to run a strong logic-minimization script
       restricted to {AND2, OR2, XOR2, NOT1},
   (4) parse and return gate counts.

Used as the inner loop of the autoresearch search over remaps.
"""
from __future__ import annotations
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from fp4_spec import DEFAULT_FP4_VALUES, qi9_encode

REPO_ROOT = Path(__file__).resolve().parent.parent
LIB_PATH = Path(__file__).resolve().parent / "contest.lib"
INPUT_NAMES = ["a3", "a2", "a1", "a0", "b3", "b2", "b1", "b0"]
OUTPUT_NAMES = [f"y{k}" for k in range(9)]


def make_pla(values: list[float]) -> str:
    """Return a PLA-format string describing the multi-output truth table.

    Inputs (8): a3 a2 a1 a0 b3 b2 b1 b0  (a = a3a2a1a0, similarly for b)
    Outputs (9): y8 y7 ... y0
    """
    lines = []
    lines.append(f".i {len(INPUT_NAMES)}")
    lines.append(f".o {len(OUTPUT_NAMES)}")
    lines.append(".ilb " + " ".join(INPUT_NAMES))
    lines.append(".ob " + " ".join(reversed(OUTPUT_NAMES)))   # y8 first to match high-bit order
    for a in range(16):
        for b in range(16):
            inp = f"{a:04b}{b:04b}"
            y = qi9_encode(4.0 * values[a] * values[b])
            outbits = "".join(str((y >> k) & 1) for k in reversed(range(9)))  # y8 .. y0
            lines.append(f"{inp} {outbits}")
    lines.append(".e")
    return "\n".join(lines) + "\n"


def synthesize(values: list[float], abc_script: str | None = None,
               keep: bool = False, timeout: int = 60) -> dict:
    """Synthesize the multiplier specified by `values` (list[16] of floats).
    Returns a dict with gate counts and the netlist text.

    `abc_script`: ABC commands to run between read_pla and write_blif. If None,
    uses a fast default. Pass a stronger script for the 'final' candidate.
    """
    if abc_script is None:
        # Fast combinational minimizer + tech-map to {AND, OR, XOR, NOT}.
        # `resyn2` is ABC's classical iterated rewrite/refactor sequence.
        abc_script = (
            "strash; "
            "resyn2; resyn2; resyn2; "  # 3x classical resyn2
            "dch -f; "                  # convert to choice network
            "map -a -B 0"               # area-priority technology mapping
        )

    pla = make_pla(values)
    with tempfile.TemporaryDirectory(prefix="fp4_synth_", dir="/tmp") as td:
        td = Path(td)
        pla_path = td / "spec.pla"
        blif_out = td / "out.blif"
        lib_local = td / "contest.lib"
        rc_local = td / "abc.rc"
        pla_path.write_text(pla)
        # ABC tokenizes on whitespace -> copy lib to a path without spaces.
        shutil.copy(LIB_PATH, lib_local)
        # ABC reads aliases from `abc.rc` in the cwd; make it findable.
        shutil.copy(Path(__file__).parent / "abc.rc", rc_local)

        cmds = [
            f"read_pla {pla_path}",
            f"read_lib -w {lib_local}",
            abc_script,
            f"write_blif {blif_out}",
            "print_stats",
        ]
        script = "; ".join(cmds)
        # yosys ships abc as a sub-binary; locate it:
        yosys_bin = shutil.which("yosys")
        assert yosys_bin, "yosys not on PATH"
        abc_bin = Path(yosys_bin).parent / "yosys-abc"
        # Try the canonical location, else fall back to /opt/homebrew/Cellar/...
        if not abc_bin.exists():
            for cand in [
                Path("/opt/homebrew/Cellar/yosys").glob("*/libexec/yosys-abc"),
                Path("/usr/local/Cellar/yosys").glob("*/libexec/yosys-abc"),
            ]:
                hits = list(cand)
                if hits:
                    abc_bin = hits[0]
                    break
        assert abc_bin.exists(), f"yosys-abc not found, tried {abc_bin}"

        result = subprocess.run(
            [str(abc_bin), "-c", script],
            capture_output=True, text=True, timeout=timeout,
            cwd=str(td),  # so abc.rc in this dir is auto-loaded for aliases
        )
        out = result.stdout + result.stderr

        # Parse the print_stats line(s)
        stats = parse_abc_stats(out)
        netlist = blif_out.read_text() if blif_out.exists() else ""
        if keep:
            keepdir = REPO_ROOT / "synth_artifacts"
            keepdir.mkdir(exist_ok=True)
            for f in td.iterdir():
                shutil.copy(f, keepdir / f.name)

        return {
            "gates": stats.get("gates"),
            "by_type": stats.get("by_type", {}),
            "log": out,
            "netlist": netlist,
            "pla": pla,
        }


def parse_abc_stats(s: str) -> dict:
    """Parse `print_stats` output. Looks for lines like:
        spec : i/o = 8/9 nd = 47 edge = ... area = 47.00 ...
    where `nd` is the number of mapped cells (= total gate count) and
    `area` matches our unit-area liberty.
    """
    stats: dict = {}
    # Find last `area =` value.
    m_area = re.findall(r"area\s*=\s*([0-9.]+)", s)
    if m_area:
        stats["gates"] = int(round(float(m_area[-1])))
    m_nd = re.findall(r"nd\s*=\s*(\d+)", s)
    if m_nd:
        stats["nd"] = int(m_nd[-1])
    return stats


def _self_test() -> None:
    print("Synthesizing default encoding ...")
    r = synthesize(DEFAULT_FP4_VALUES, keep=False)
    print(f"  gates: {r['gates']}")
    print("---ABC log tail---")
    print("\n".join(r["log"].splitlines()[-30:]))


if __name__ == "__main__":
    _self_test()
