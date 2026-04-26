"""Wide sweep with mut11 form."""
import argparse, csv, time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
import re, shutil, subprocess, tempfile

from remap import sign_symmetric_remaps, encoding_from_magnitude_perm
from synth_struct import RESYN2
from gen_mut11 import emit_mut11_verilog
from verify import verify_blif

REPO = Path(__file__).resolve().parent.parent
LEDGER = REPO / "results_mut11.tsv"
LIB = Path(__file__).resolve().parent / "contest.lib"

FAST = "strash; ifraig; scorr; dc2; strash; dch -f; map -a -B 0"
DEEP = (f"strash; ifraig; scorr; dc2; strash; {RESYN2}; "
        f"&get -n; &deepsyn -T 3 -I 4; &put; "
        f"logic; mfs2; strash; dch -f; map -a -B 0")


def synth_one(perm, abc_script, timeout=30):
    values = encoding_from_magnitude_perm(perm)
    verilog = emit_mut11_verilog(values)
    with tempfile.TemporaryDirectory(prefix="s11_", dir="/tmp") as td:
        td = Path(td)
        (td / "fp4_mul.v").write_text(verilog)
        shutil.copy(LIB, td / "contest.lib")
        yscr = "+" + abc_script.strip().replace(" ", ",")
        (td / "synth.ys").write_text(f"read_verilog {td}/fp4_mul.v\nhierarchy -top fp4_mul\nproc; opt; flatten; opt -full; techmap; opt\nabc -liberty {td}/contest.lib -script {yscr}\nwrite_blif {td}/out.blif\nstat -liberty {td}/contest.lib\n")
        t0 = time.time()
        try:
            r = subprocess.run(["yosys", str(td / "synth.ys")],
                               capture_output=True, text=True, cwd=str(td),
                               timeout=timeout)
        except subprocess.TimeoutExpired:
            return None, False, timeout
        wall = time.time() - t0
        m = re.findall(r"Chip area for module '\\?fp4_mul':\s*([0-9.]+)", r.stdout)
        gates = int(round(float(m[-1]))) if m else None
        ok = False
        if (td / "out.blif").exists():
            ok, _ = verify_blif(td / "out.blif", values=values)
        return gates, ok, wall


def write_header():
    if not LEDGER.exists():
        with open(LEDGER, "w", newline="") as f:
            csv.writer(f, delimiter="\t").writerow(
                ["ts", "perm", "script", "gates", "verify", "wall_sec"])


def append_row(perm, sk, g, ok, wall):
    with open(LEDGER, "a", newline="") as f:
        csv.writer(f, delimiter="\t").writerow([
            time.strftime("%Y-%m-%dT%H:%M:%S"),
            ",".join(map(str, perm)), sk,
            g if g is not None else -1,
            "OK" if ok else "FAIL", f"{wall:.2f}"])


def worker(args):
    perm, sk, timeout = args
    script = FAST if sk == "fast" else DEEP
    g, ok, wall = synth_one(perm, script, timeout=timeout)
    return perm, sk, g, ok, wall


def run_pass(perms, sk, timeout, workers):
    args_list = [(p, sk, timeout) for p in perms]
    with ProcessPoolExecutor(max_workers=workers) as ex:
        futures = {ex.submit(worker, a): a[0] for a in args_list}
        for fut in as_completed(futures):
            try: yield fut.result()
            except Exception: yield (futures[fut], sk, None, False, 0.0)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--n", type=int, default=2000)
    p.add_argument("--top-k", type=int, default=50)
    p.add_argument("--workers", type=int, default=4)
    p.add_argument("--fast-timeout", type=int, default=10)
    p.add_argument("--deep-timeout", type=int, default=25)
    args = p.parse_args()
    write_header()
    print(f"=== FAST mut11-form over first {args.n} sign-sym remaps ===", flush=True)
    perms = []
    for i, (perm, _) in enumerate(sign_symmetric_remaps()):
        if i >= args.n: break
        perms.append(perm)
    fast_ok = []; failed = 0; t0 = time.time()
    for perm, sk, g, ok, wall in run_pass(perms, "fast", args.fast_timeout, args.workers):
        append_row(perm, sk, g, ok, wall)
        if ok and g is not None: fast_ok.append((perm, g))
        else: failed += 1
        if (len(fast_ok) + failed) % 100 == 0:
            best = min(fast_ok, key=lambda x: x[1]) if fast_ok else None
            print(f"  done={len(fast_ok)+failed}/{len(perms)} best={best[1] if best else '?'} ({time.time()-t0:.0f}s)", flush=True)
    fast_ok.sort(key=lambda x: x[1])
    print(f"\nStage 1 done. Top 30 by FAST:", flush=True)
    for p, g in fast_ok[:30]: print(f"  {g}: {p}")
    top = [p for p, _ in fast_ok[:args.top_k]]
    print(f"\n=== Stage 2: deepsyn-3s on top-{len(top)} ===", flush=True)
    deep = []
    for perm, sk, g, ok, wall in run_pass(top, "deep", args.deep_timeout, args.workers):
        append_row(perm, sk, g, ok, wall)
        if ok and g is not None:
            deep.append((perm, g))
            print(f"  {g}: {perm}  ({wall:.1f}s)", flush=True)
    deep.sort(key=lambda x: x[1])
    print(f"\nFinal Top 10:")
    for p, g in deep[:10]: print(f"  {g}: {p}")
    if deep:
        print(f"\nBest: {deep[0][1]} gates, perm={deep[0][0]}")


if __name__ == "__main__":
    main()
