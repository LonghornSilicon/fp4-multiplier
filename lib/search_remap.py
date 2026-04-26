"""Drive a remap-aware search over sign-symmetric magnitude permutations,
using `synth_remap.synthesize_remap` (structural Verilog + per-remap decoder).

Saves results to results.tsv. Two-stage: FAST script for the wide pass,
then deepsyn-3s on the top-K for refinement.
"""
from __future__ import annotations
import argparse
import csv
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

from fp4_spec import DEFAULT_FP4_VALUES
from remap import sign_symmetric_remaps, encoding_from_magnitude_perm
from synth_remap import synthesize_remap, RESYN2

REPO = Path(__file__).resolve().parent.parent
LEDGER = REPO / "results_remap.tsv"
ARTIFACT_DIR = REPO / "synth_remap_artifacts"


FAST_SCRIPT = (
    "strash; ifraig; scorr; dc2; strash; "
    "&get -n; &fraig -x; &put; "
    "scleanup; dch -f; map -a -B 0"
)

DEEP_SCRIPT = (
    f"strash; ifraig; scorr; dc2; strash; "
    f"{RESYN2}; "
    f"&get -n; &deepsyn -T 3 -I 4; &put; "
    f"logic; mfs2; strash; "
    f"dch -f; map -a -B 0"
)


def write_header():
    if not LEDGER.exists():
        with open(LEDGER, "w", newline="") as f:
            csv.writer(f, delimiter="\t").writerow(
                ["ts", "perm", "script", "gates", "verify", "wall_sec"]
            )


def append_row(perm: tuple[int, ...], script: str, gates: int | None,
               verify: bool, wall: float):
    with open(LEDGER, "a", newline="") as f:
        csv.writer(f, delimiter="\t").writerow([
            time.strftime("%Y-%m-%dT%H:%M:%S"),
            ",".join(map(str, perm)),
            script,
            gates if gates is not None else -1,
            "OK" if verify else "FAIL",
            f"{wall:.2f}",
        ])


def _worker(args):
    perm, script_kind, timeout = args
    script = FAST_SCRIPT if script_kind == "fast" else DEEP_SCRIPT
    values = encoding_from_magnitude_perm(perm)
    r = synthesize_remap(values, abc_script=script, timeout=timeout)
    return perm, script_kind, r["gates"], r["verify"], r["wall"]


def run_pass(perms, script_kind: str, timeout: int = 30, workers: int = 4):
    """Run a parallel synthesis pass. Yields (perm, gates, verify, wall) per
    completed job."""
    args_list = [(p, script_kind, timeout) for p in perms]
    with ProcessPoolExecutor(max_workers=workers) as ex:
        futures = {ex.submit(_worker, a): a[0] for a in args_list}
        for fut in as_completed(futures):
            try:
                perm, sk, gates, verify, wall = fut.result()
            except Exception as e:
                perm = futures[fut]
                yield perm, None, False, 0.0
                continue
            append_row(perm, sk, gates, verify, wall)
            yield perm, gates, verify, wall


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--n", type=int, default=200,
                   help="how many sign-symmetric remaps to sweep with FAST")
    p.add_argument("--top-k", type=int, default=20,
                   help="how many top FAST candidates to refine with deepsyn")
    p.add_argument("--workers", type=int, default=4)
    p.add_argument("--fast-timeout", type=int, default=10)
    p.add_argument("--deep-timeout", type=int, default=30)
    args = p.parse_args()

    write_header()

    # Stage 1: FAST sweep over first N sign-symmetric remaps.
    print(f"=== Stage 1: FAST sweep over {args.n} sign-symmetric remaps "
          f"({args.workers} workers) ===")
    perms = []
    for i, (perm, _) in enumerate(sign_symmetric_remaps()):
        if i >= args.n:
            break
        perms.append(perm)

    t0 = time.time()
    fast_results: list[tuple[tuple[int, ...], int]] = []
    failed = 0
    for perm, gates, verify, wall in run_pass(perms, "fast",
                                              timeout=args.fast_timeout,
                                              workers=args.workers):
        if verify and gates is not None:
            fast_results.append((perm, gates))
        else:
            failed += 1
        if (len(fast_results) + failed) % 25 == 0:
            best = min(fast_results, key=lambda x: x[1]) if fast_results else None
            print(f"  done={len(fast_results)+failed}/{len(perms)} "
                  f"best_so_far={best[1] if best else 'n/a'} "
                  f"({(time.time()-t0):.0f}s elapsed)", flush=True)

    fast_results.sort(key=lambda x: x[1])
    print(f"\nStage 1 complete: {len(fast_results)} OK / {failed} failed.")
    print("Top 20 by gates:")
    for perm, g in fast_results[:20]:
        print(f"  {g:4d}  {perm}")

    # Stage 2: deepsyn on top-K
    top_perms = [p for p, _ in fast_results[:args.top_k]]
    print(f"\n=== Stage 2: deepsyn-3s on top {len(top_perms)} candidates ===")
    deep_results: list[tuple[tuple[int, ...], int]] = []
    for perm, gates, verify, wall in run_pass(top_perms, "deep",
                                              timeout=args.deep_timeout,
                                              workers=args.workers):
        if verify and gates is not None:
            deep_results.append((perm, gates))
            print(f"  {gates:4d}  {perm}  ({wall:.1f}s)")

    deep_results.sort(key=lambda x: x[1])
    print(f"\nStage 2 complete. Top 5 by gates after deep refinement:")
    for perm, g in deep_results[:5]:
        print(f"  {g:4d}  {perm}")
    if deep_results:
        best_perm, best_gates = deep_results[0]
        print(f"\nBest overall: {best_gates} gates, perm={best_perm}")


if __name__ == "__main__":
    main()
