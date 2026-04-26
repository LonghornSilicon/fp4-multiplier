"""Sweep sign-symmetric remaps using the raw-form Verilog. Two-stage:
   FAST script over many; deepsyn-3s on top-K."""
from __future__ import annotations
import argparse, csv, time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

from remap import sign_symmetric_remaps, encoding_from_magnitude_perm
from synth_raw import synthesize_raw, RESYN2

REPO = Path(__file__).resolve().parent.parent
LEDGER = REPO / "results_raw.tsv"


FAST_SCRIPT = "strash; ifraig; scorr; dc2; strash; &get -n; &fraig -x; &put; scleanup; dch -f; map -a -B 0"
DEEP_SCRIPT = (f"strash; ifraig; scorr; dc2; strash; "
               f"{RESYN2}; "
               f"&get -n; &deepsyn -T 3 -I 4; &put; "
               f"logic; mfs2; strash; "
               f"dch -f; map -a -B 0")


def write_header():
    if not LEDGER.exists():
        with open(LEDGER, "w", newline="") as f:
            csv.writer(f, delimiter="\t").writerow(
                ["ts", "perm", "script", "gates", "verify", "wall_sec"])


def append_row(perm, script_kind, gates, ok, wall):
    with open(LEDGER, "a", newline="") as f:
        csv.writer(f, delimiter="\t").writerow([
            time.strftime("%Y-%m-%dT%H:%M:%S"),
            ",".join(map(str, perm)), script_kind,
            gates if gates is not None else -1,
            "OK" if ok else "FAIL", f"{wall:.2f}"])


def _worker(args):
    perm, script_kind, timeout = args
    script = FAST_SCRIPT if script_kind == "fast" else DEEP_SCRIPT
    values = encoding_from_magnitude_perm(perm)
    r = synthesize_raw(values, abc_script=script, timeout=timeout)
    return perm, script_kind, r["gates"], r["verify"], r["wall"]


def run_pass(perms, script_kind, timeout, workers):
    args_list = [(p, script_kind, timeout) for p in perms]
    with ProcessPoolExecutor(max_workers=workers) as ex:
        futures = {ex.submit(_worker, a): a[0] for a in args_list}
        for fut in as_completed(futures):
            try:
                yield fut.result()
            except Exception:
                yield (futures[fut], script_kind, None, False, 0.0)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--n", type=int, default=500)
    p.add_argument("--top-k", type=int, default=30)
    p.add_argument("--workers", type=int, default=4)
    p.add_argument("--fast-timeout", type=int, default=10)
    p.add_argument("--deep-timeout", type=int, default=30)
    args = p.parse_args()
    write_header()
    print(f"=== Stage 1: FAST raw-form over first {args.n} sign-sym remaps ===", flush=True)
    perms = []
    for i, (perm, _) in enumerate(sign_symmetric_remaps()):
        if i >= args.n: break
        perms.append(perm)
    fast_ok = []
    failed = 0
    t0 = time.time()
    for perm, sk, g, ok, wall in run_pass(perms, "fast", args.fast_timeout, args.workers):
        append_row(perm, sk, g, ok, wall)
        if ok and g is not None: fast_ok.append((perm, g))
        else: failed += 1
        if (len(fast_ok) + failed) % 50 == 0:
            best = min(fast_ok, key=lambda x: x[1]) if fast_ok else None
            print(f"  done={len(fast_ok)+failed}/{len(perms)} best={best[1] if best else 'n/a'} ({time.time()-t0:.0f}s)", flush=True)
    fast_ok.sort(key=lambda x: x[1])
    print(f"\nStage 1 done. {len(fast_ok)} OK / {failed} fail. Top 20:", flush=True)
    for perm, g in fast_ok[:20]:
        print(f"  {g:4d}  {perm}")
    top = [p for p, _ in fast_ok[:args.top_k]]
    print(f"\n=== Stage 2: deepsyn-3s on top-{len(top)} ===", flush=True)
    deep_ok = []
    for perm, sk, g, ok, wall in run_pass(top, "deep", args.deep_timeout, args.workers):
        append_row(perm, sk, g, ok, wall)
        if ok and g is not None:
            deep_ok.append((perm, g))
            print(f"  {g:4d}  {perm}  ({wall:.1f}s)", flush=True)
    deep_ok.sort(key=lambda x: x[1])
    print(f"\nFinal Top 5:")
    for perm, g in deep_ok[:5]:
        print(f"  {g:4d}  {perm}")
    if deep_ok:
        print(f"\nBest: {deep_ok[0][1]} gates, perm={deep_ok[0][0]}")


if __name__ == "__main__":
    main()
