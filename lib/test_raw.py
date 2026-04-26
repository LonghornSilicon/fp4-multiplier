"""Test the raw-bit Verilog (assumes σ=(0,1,2,3,6,7,4,5) remap implicitly).
Verifies under that remap's value table."""
import re, shutil, subprocess, tempfile, time
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
    'deepsyn-10': f'strash; ifraig; scorr; dc2; strash; {RESYN2}; &get -n; &deepsyn -T 10 -I 8; &put; logic; mfs2; strash; dch -f; map -a -B 0',
}

src = CODE / 'fp4_mul_raw.v'
print(f"{'script':12s} {'gates':>6}  {'wall':>5}", flush=True)
for name, scr in scripts.items():
    with tempfile.TemporaryDirectory(prefix='raw_', dir='/tmp') as td:
        td = Path(td)
        shutil.copy(src, td / 'fp4_mul.v')
        shutil.copy(LIB, td / 'contest.lib')
        yscr = '+' + scr.replace(' ', ',')
        (td / 'synth.ys').write_text(
            f"read_verilog {td}/fp4_mul.v\n"
            f"hierarchy -top fp4_mul\n"
            f"proc; opt; flatten; opt -full; techmap; opt\n"
            f"abc -liberty {td}/contest.lib -script {yscr}\n"
            f"write_blif {td}/out.blif\n"
            f"stat -liberty {td}/contest.lib\n")
        t0 = time.time()
        try:
            r = subprocess.run(['yosys', str(td / 'synth.ys')],
                               capture_output=True, text=True,
                               cwd=str(td), timeout=60)
        except subprocess.TimeoutExpired:
            print(f"{name:12s} {'TO':>6}  {'60.0':>5}", flush=True)
            continue
        wall = time.time() - t0
        m = re.findall(r"Chip area for module '\\?fp4_mul':\s*([0-9.]+)", r.stdout)
        gates = int(round(float(m[-1]))) if m else None
        ok = False
        if (td / 'out.blif').exists():
            ok, mism = verify_blif(td / 'out.blif', values=values)
        print(f"{name:12s} {gates!s:>6}  {wall:>5.1f}  {'OK' if ok else 'FAIL'}", flush=True)
