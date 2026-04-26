"""Run ABC `&exact` on each of the 9 output bits independently. Each is an
8-input single-output truth table. The reported AIG size = a lower bound on
the per-bit gate count under {AND, NOT} (which is a sub-library of ours,
since XOR can be 3 ANDs+1 NOT, OR = NAND of NOTs, etc.).

Sum of per-bit AIG sizes is therefore a (loose) upper bound for "what the
function would cost if we computed each output bit independently without
sharing." If the sum is similar to our current 85, sharing isn't the bottleneck.
"""
from __future__ import annotations
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from fp4_spec import DEFAULT_FP4_VALUES, per_output_bit_truth_tables

CODE = Path(__file__).resolve().parent
LIB = CODE / "contest.lib"


def truth_table_hex(tt_int: int, n_inputs: int = 8) -> str:
    """Return 2^n-bit truth table as a hex string for ABC's `read_truth`.

    ABC's hex form: the integer's hex representation, padded to n_bits/4 chars.
    """
    n_hex = (1 << n_inputs) // 4
    return f"{tt_int:0{n_hex}x}"


def synth_one_output(tt_int: int, abc_cmds: str, timeout: int = 60) -> dict:
    with tempfile.TemporaryDirectory(prefix="exact_", dir="/tmp") as td:
        td = Path(td)
        shutil.copy(LIB, td / "contest.lib")
        # abc.rc must be in cwd for aliases (resyn2 etc).
        shutil.copy(CODE / "abc.rc", td / "abc.rc")
        tt_hex = truth_table_hex(tt_int)
        # `read_truth` (no -x) takes a hex truth-table string directly.
        script = f"read_truth {tt_hex}; {abc_cmds}; print_stats"
        r = subprocess.run(
            ["yosys-abc", "-c", script],
            capture_output=True, text=True, timeout=timeout, cwd=str(td),
        )
        out = r.stdout + r.stderr
        # ABC `print_stats` line for a strashed AIG: "... and = N ..."
        # For mapped: "... nd = N edge = ... area = N.00 ..."
        m = re.findall(r"\band\s*=\s*(\d+)", out)
        if not m:
            m = re.findall(r"\bnd\s*=\s*(\d+)", out)
        nd = int(m[-1]) if m else None
        return {"nd": nd, "log": out}


def main():
    tts = per_output_bit_truth_tables(DEFAULT_FP4_VALUES)
    print("Per-output AIG-node counts via ABC '&deepsyn':\n")
    print(f"{'Y':>3} {'ones':>5} {'nd_fast':>9} {'nd_strong':>11}")

    total_fast = 0
    total_strong = 0
    for k, t in enumerate(tts):
        ones = bin(t).count("1")
        # fast
        rf = synth_one_output(t, "strash; resyn2; resyn2; resyn2", timeout=60)
        nd_fast = rf["nd"]
        # strong with &deepsyn
        rs = synth_one_output(t, "strash; resyn2; resyn2; resyn2; "
                                 "&get -n; &deepsyn -T 5 -I 6; &put; "
                                 "strash", timeout=120)
        nd_strong = rs["nd"]
        if nd_fast: total_fast += nd_fast
        if nd_strong: total_strong += nd_strong
        print(f"  Y[{k}]  {ones:>4}    {nd_fast!s:>5}      {nd_strong!s:>5}")
    print(f"\n  sum (no sharing) ≈ {total_fast} (fast) / {total_strong} (strong)")
    print("Note: 1 AIG AND ≈ 1 AND2 in our library; XOR2 = 3 AIG ANDs typically;")
    print("      so the AIG total is a rough proxy for gate count.")


if __name__ == "__main__":
    main()
