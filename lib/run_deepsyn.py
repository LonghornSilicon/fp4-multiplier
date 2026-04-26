"""Run a slow, strong synthesis pass on the default encoding to get a true
   baseline gate count via ABC's `&deepsyn`. Saves netlist + log."""
from __future__ import annotations
import sys

from fp4_spec import DEFAULT_FP4_VALUES
from synth import synthesize


def main():
    # Strong: &deepsyn does iterated optimization. -I and -T cap inner-loop and time.
    abc = (
        "strash; "
        "&get -n; "
        "&deepsyn -I 12 -T 240; "  # up to 4 minutes inside &deepsyn
        "&put; "
        "logic; mfs2 -W 4 -F 4 -D 8 -L 200; "
        "strash; "
        "dch -f; "
        "map -a -B 0"
    )
    print("Running deepsyn baseline (default encoding) ...", flush=True)
    r = synthesize(DEFAULT_FP4_VALUES, abc_script=abc, keep=True, timeout=420)
    print(f"  gates: {r['gates']}", flush=True)
    print("---last 25 log lines---", flush=True)
    print("\n".join(r["log"].splitlines()[-25:]), flush=True)


if __name__ == "__main__":
    main()
