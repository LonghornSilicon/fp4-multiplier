"""Verilog-based synthesis pipeline. Generates a behavioral Verilog file from
a `values` list (one float per 4-bit codepoint), runs yosys + ABC under our
contest.lib gate library, and returns the gate count + verified BLIF.

Why Verilog instead of PLA? Yosys's behavioral elaboration + ABC's optimizer
preserves arithmetic structure that the flat truth table (PLA) loses. Empirically,
default encoding via PLA -> ABC gives 390 gates (FAST), whereas via Verilog ->
yosys -> ABC it gives 222 gates with a similar-effort script.
"""
from __future__ import annotations
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from fp4_spec import DEFAULT_FP4_VALUES, qi9_encode

LIB_PATH = Path(__file__).resolve().parent / "contest.lib"


def emit_verilog(values: list[float]) -> str:
    """Build a behavioral Verilog of the FP4 multiplier with the given encoding.

    Each input value is multiplied by 4 in advance so we stay with integer
    arithmetic in the case-decoder. Output Y = (4·val_a) * (4·val_b) >>> 2.
    Result range fits in 9 bits signed (max |Y| = 144).
    """
    def fourx(v: float) -> int:
        i = int(round(4 * v))
        # Sanity: 4·val for val ∈ {0, ±0.5, ±1, ±1.5, ±2, ±3, ±4, ±6} gives
        # integers in {0, ±2, ±4, ±6, ±8, ±12, ±16, ±24} — fits 6-bit signed.
        assert -32 <= i <= 31, f"4·val={i} out of 6-bit signed range"
        return i

    cases_a = []
    cases_b = []
    for code in range(16):
        v4 = fourx(values[code])
        cases_a.append(f"            4'b{code:04b}: xa = 6'sd{v4 if v4 >= 0 else -v4}{'' if v4 >= 0 else ' * -1'};")
        cases_b.append(f"            4'b{code:04b}: xb = 6'sd{v4 if v4 >= 0 else -v4}{'' if v4 >= 0 else ' * -1'};")

    # Cleaner: emit signed decimal directly using `-6'sd<abs>` for negatives.
    def fmt(v4: int) -> str:
        if v4 >= 0:
            return f"6'sd{v4}"
        else:
            return f"-6'sd{-v4}"

    cases_a = "\n".join(
        f"            4'b{code:04b}: xa = {fmt(fourx(values[code]))};"
        for code in range(16)
    )
    cases_b = "\n".join(
        f"            4'b{code:04b}: xb = {fmt(fourx(values[code]))};"
        for code in range(16)
    )

    return f"""
module fp4_mul (
    input  wire [3:0] a,
    input  wire [3:0] b,
    output wire [8:0] y
);
    reg signed [5:0] xa, xb;
    always @* begin
        case (a)
{cases_a}
            default: xa = 6'sd0;
        endcase
        case (b)
{cases_b}
            default: xb = 6'sd0;
        endcase
    end
    wire signed [11:0] prod = xa * xb;
    wire signed [9:0]  shifted = prod >>> 2;
    assign y = shifted[8:0];
endmodule
"""


def emit_yosys_script(verilog_path: Path, blif_out: Path,
                      lib_path: Path, abc_script: str | None,
                      yosys_passes: str | None) -> str:
    if yosys_passes is None:
        # Convert case-statement-as-memory into pure combinational logic via
        # memory pass; then standard optimization. We want NO memories left
        # before BLIF backend.
        yosys_passes = (
            "proc; opt; "
            "memory; opt; "
            "flatten; opt -full; "
            "techmap; opt"
        )
    if abc_script is None:
        # Proven-working balanced script (from synth_baseline.ys).
        abc_script = (
            "strash; ifraig; scorr; dc2; dretime; strash; "
            "&get -n; &fraig -x; &put; "
            "scleanup; dch -f; map -a -B 0"
        )
    # Yosys script syntax: '+cmd1,arg1,...;,cmd2,...' (commas → spaces).
    # Note: yosys uses a single comma where ABC would use space; the leading
    # '+' tells yosys this is a literal command list (not a file path).
    yosys_abc_script = "+" + abc_script.strip().replace(" ", ",")
    abc_pass = f"abc -liberty {lib_path} -script {yosys_abc_script}"
    return f"""
read_verilog {verilog_path}
hierarchy -top fp4_mul
{yosys_passes}
{abc_pass}
write_blif {blif_out}
stat -liberty {lib_path}
"""


def synthesize_v(values: list[float], abc_script: str | None = None,
                 yosys_passes: str | None = None,
                 timeout: int = 90,
                 keep_dir: Path | None = None) -> dict:
    """Synthesize via Verilog -> yosys -> embedded ABC. Returns gate count and
    BLIF text."""
    with tempfile.TemporaryDirectory(prefix="fp4_v_", dir="/tmp") as td:
        td = Path(td)
        v_path = td / "fp4_mul.v"
        blif_out = td / "out.blif"
        lib_local = td / "contest.lib"
        rc_local = td / "abc.rc"
        v_path.write_text(emit_verilog(values))
        shutil.copy(LIB_PATH, lib_local)
        shutil.copy(Path(__file__).parent / "abc.rc", rc_local)

        ys_script = emit_yosys_script(v_path, blif_out, lib_local,
                                      abc_script, yosys_passes)
        ys_path = td / "synth.ys"
        ys_path.write_text(ys_script)

        result = subprocess.run(
            ["yosys", str(ys_path)],
            capture_output=True, text=True, timeout=timeout,
            cwd=str(td),
        )
        out = result.stdout + result.stderr
        gates = parse_yosys_stat(out)
        netlist = blif_out.read_text() if blif_out.exists() else ""

        if keep_dir is not None:
            keep_dir.mkdir(exist_ok=True)
            for f in td.iterdir():
                shutil.copy(f, keep_dir / f.name)

        return {
            "gates": gates,
            "log": out,
            "netlist": netlist,
            "verilog": v_path.read_text(),
        }


def parse_yosys_stat(s: str) -> int | None:
    """Parse yosys's `stat -liberty` output for total chip area = total gate count."""
    m = re.findall(r"Chip area for module '\\?fp4_mul':\s*([0-9.]+)", s)
    if m:
        return int(round(float(m[-1])))
    # Fallback: look for ABC's own line `area = ...`
    m2 = re.findall(r"area\s*=\s*([0-9.]+)", s)
    if m2:
        return int(round(float(m2[-1])))
    return None


def _self_test():
    from verify import verify_blif
    print("Synthesizing default encoding via Verilog ...", flush=True)
    r = synthesize_v(DEFAULT_FP4_VALUES, timeout=120,
                     keep_dir=Path(__file__).resolve().parent.parent / "synth_artifacts_v")
    print(f"  gates: {r['gates']}", flush=True)
    if r["netlist"]:
        # Re-parse the saved BLIF in the keep dir
        blif = Path(__file__).resolve().parent.parent / "synth_artifacts_v" / "out.blif"
        ok, mism = verify_blif(blif)
        print(f"  verify: {'OK' if ok else f'WRONG ({len(mism)} mismatches)'}", flush=True)
        if not ok:
            print("  first mismatches:", mism[:3])


if __name__ == "__main__":
    _self_test()
