"""Synthesize and verify the AlphaEvolve-style mutations against the best remap."""
import re, shutil, subprocess, sys, tempfile, time
from pathlib import Path
from verify import verify_blif
from remap import encoding_from_magnitude_perm
from synth_struct import RESYN2

CODE = Path(__file__).resolve().parent
LIB = CODE / "contest.lib"
values = encoding_from_magnitude_perm((0, 1, 2, 3, 6, 7, 4, 5))

scripts = {
    'fast':       'strash; ifraig; scorr; dc2; strash; dch -f; map -a -B 0',
    'med':        f'strash; ifraig; scorr; dc2; strash; {RESYN2}; {RESYN2}; logic; mfs2; strash; dch -f; map -a -B 0',
    'deepsyn-3':  f'strash; ifraig; scorr; dc2; strash; {RESYN2}; &get -n; &deepsyn -T 3 -I 4; &put; logic; mfs2; strash; dch -f; map -a -B 0',
}

mutations = sys.argv[1:] if len(sys.argv) > 1 else [
    'fp4_mul_raw.v',     # 81-gate baseline
    'fp4_mul_mut1.v',
    'fp4_mul_mut2.v',
    'fp4_mul_mut3.v',
    'fp4_mul_mut4.v',
]

print(f"{'mutation':22s} {'script':12s} {'gates':>6}  {'wall':>5}  {'verify':>6}", flush=True)
print('-' * 60, flush=True)
for src_name in mutations:
    src = CODE / src_name
    if not src.exists():
        print(f"  {src_name:22s} (missing)")
        continue
    for sname, scr in scripts.items():
        with tempfile.TemporaryDirectory(prefix='mut_', dir='/tmp') as td:
            td = Path(td)
            shutil.copy(src, td / 'fp4_mul.v')
            shutil.copy(LIB, td / 'contest.lib')
            yscr = '+' + scr.replace(' ', ',')
            (td / 'synth.ys').write_text(
                f'read_verilog {td}/fp4_mul.v\n'
                f'hierarchy -top fp4_mul\n'
                f'proc; opt; flatten; opt -full; techmap; opt\n'
                f'abc -liberty {td}/contest.lib -script {yscr}\n'
                f'write_blif {td}/out.blif\n'
                f'stat -liberty {td}/contest.lib\n')
            t0 = time.time()
            try:
                r = subprocess.run(['yosys', str(td/'synth.ys')],
                                   capture_output=True, text=True, cwd=str(td),
                                   timeout=60)
            except subprocess.TimeoutExpired:
                print(f"  {src_name:22s} {sname:12s} {'TO':>6}  60.0  --", flush=True)
                continue
            wall = time.time() - t0
            m = re.findall(r"Chip area for module '\\?fp4_mul':\s*([0-9.]+)", r.stdout)
            gates = int(round(float(m[-1]))) if m else None
            ok = False
            if (td / 'out.blif').exists():
                ok, _ = verify_blif(td / 'out.blif', values=values)
            print(f"  {src_name:22s} {sname:12s} {gates!s:>6}  {wall:>5.1f}  {'OK' if ok else 'FAIL'}", flush=True)
