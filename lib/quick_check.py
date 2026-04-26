"""Run a fast synthesis on default encoding, verify against reference."""
from fp4_spec import DEFAULT_FP4_VALUES
from synth import synthesize
from verify import verify_blif
from pathlib import Path
import shutil


REPO = Path(__file__).resolve().parent.parent


def main():
    print("Synthesizing (fast resyn2 baseline)...", flush=True)
    r = synthesize(DEFAULT_FP4_VALUES, keep=True, timeout=60)
    print(f"  gates: {r['gates']}", flush=True)

    # synth.py saved artifacts to {REPO}/synth_artifacts/. Verify the BLIF.
    blif = REPO / "synth_artifacts" / "out.blif"
    print(f"  blif: {blif}", flush=True)
    ok, mism = verify_blif(blif)
    if ok:
        print("  CORRECT: all 256 input pairs match reference.")
    else:
        print(f"  WRONG: {len(mism)} mismatches.")
        for m in mism[:5]:
            print("   ", m)


if __name__ == "__main__":
    main()
