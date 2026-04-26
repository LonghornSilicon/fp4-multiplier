"""Save the canonical 81-gate netlist with full provenance."""
import re, shutil, subprocess, tempfile, time
from pathlib import Path
from verify import verify_blif
from remap import encoding_from_magnitude_perm
from synth_struct import RESYN2

CODE = Path(__file__).resolve().parent
LIB = CODE / "contest.lib"

values = encoding_from_magnitude_perm((0, 1, 2, 3, 6, 7, 4, 5))
scr = (f"strash; ifraig; scorr; dc2; strash; "
       f"{RESYN2}; "
       f"&get -n; &deepsyn -T 3 -I 4; &put; "
       f"logic; mfs2; strash; "
       f"dch -f; map -a -B 0")

src = CODE / 'fp4_mul_raw.v'
out_dir = CODE.parent / 'current_best'
out_dir.mkdir(exist_ok=True)

with tempfile.TemporaryDirectory(prefix='best81_', dir='/tmp') as td:
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
    r = subprocess.run(['yosys', str(td / 'synth.ys')],
                       capture_output=True, text=True,
                       cwd=str(td), timeout=120)
    wall = time.time() - t0
    m = re.findall(r"Chip area for module '\\?fp4_mul':\s*([0-9.]+)", r.stdout)
    gates = int(round(float(m[-1]))) if m else None
    ok = False
    if (td / 'out.blif').exists():
        ok, _ = verify_blif(td / 'out.blif', values=values)
    print(f"gates={gates}  verify={'OK' if ok else 'FAIL'}  ({wall:.1f}s)")
    if ok and gates is not None:
        # Save artifacts to current_best/
        shutil.copy(td / 'out.blif', out_dir / 'fp4_mul.blif')
        shutil.copy(src, out_dir / 'fp4_mul.v')
        shutil.copy(td / 'synth.ys', out_dir / 'synth.ys')
        shutil.copy(td / 'contest.lib', out_dir / 'contest.lib')
        # Cell breakdown
        for celltype in ['AND2', 'NOT1', 'OR2', 'XOR2']:
            mm = re.findall(rf'{celltype}\s*cells:\s+(\d+)', r.stdout)
            if mm:
                print(f"  {celltype}: {mm[-1]}")
        print(f"\nSaved to {out_dir}")
