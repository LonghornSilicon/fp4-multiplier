"""Verify every start BLIF passes the frozen verifier under sigma=(0,1,2,3,6,7,4,5)."""
import sys
from pathlib import Path
sys.path.insert(0, "/home/shadeform/fp4-multiplier/lib")
from verify import verify_blif
from remap import encoding_from_magnitude_perm

values = encoding_from_magnitude_perm((0, 1, 2, 3, 6, 7, 4, 5))
starts_dir = Path("/home/shadeform/fp4-multiplier/workspace/eslim_runs/starts")
ok_starts = []
bad = []
for f in sorted(starts_dir.glob("*.blif")):
    try:
        ok, mism = verify_blif(str(f), values=values)
        if ok:
            ok_starts.append(f.name)
        else:
            bad.append((f.name, len(mism)))
    except Exception as e:
        bad.append((f.name, f"err:{e}"))
print(f"OK: {len(ok_starts)}, BAD: {len(bad)}")
for f in ok_starts:
    print("  OK", f)
for n, m in bad:
    print("  BAD", n, m)
