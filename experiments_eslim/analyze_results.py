"""Post-sweep analyzer: walk all par_*_gates.blif files in /tmp/eslim_work/,
report per-file cell breakdown, count any with NOT count != 6, and flag
sub-64 results as breakthrough candidates."""
from __future__ import annotations
import os, re, sys
from pathlib import Path
from collections import Counter, defaultdict

WORK = Path("/tmp/eslim_work")


def cell_breakdown(blif: Path):
    counts = Counter()
    with open(blif) as f:
        for ln in f:
            ln = ln.strip()
            if ln.startswith(".gate"):
                kind = ln.split()[1]
                counts[kind] += 1
    return counts, sum(counts.values())


def main():
    files = sorted(WORK.glob("par*_gates.blif"))
    print(f"Scanning {len(files)} BLIFs in {WORK}...")
    by_total = defaultdict(list)
    by_nots = defaultdict(list)
    sub_64 = []
    for f in files:
        try:
            c, total = cell_breakdown(f)
        except Exception as e:
            print(f"  {f.name}: error {e}"); continue
        n_not = c.get("NOT1", 0)
        by_total[total].append((f.name, n_not, dict(c)))
        by_nots[n_not].append((f.name, total, dict(c)))
        if total < 64:
            sub_64.append((f.name, total, n_not, dict(c)))

    print()
    print("Total contest cells across all post-sweep BLIFs:")
    for k in sorted(by_total):
        print(f"  {k} cells: {len(by_total[k])} files")
    print()
    print("NOT count distribution:")
    for n in sorted(by_nots):
        print(f"  {n} NOTs: {len(by_nots[n])} files")

    print()
    if sub_64:
        print(f"*** {len(sub_64)} SUB-64 BLIF(s) FOUND ***")
        for name, total, n_not, c in sub_64:
            print(f"  {name}: total={total}, NOTs={n_not}, breakdown={c}")
    else:
        print("No sub-64 BLIFs found in any sweep.")

    # Highlight 64-cell BLIFs with FEWER than 6 NOTs (low-NOT basins)
    print()
    low_not_64 = [b for b in by_total[64] if b[1] < 6]
    if low_not_64:
        print(f"*** {len(low_not_64)} 64-cell BLIF(s) with <6 NOTs (round-2 seeds) ***")
        for name, n_not, c in low_not_64:
            print(f"  {name}: NOTs={n_not}, breakdown={c}")
    else:
        if 64 in by_total:
            print(f"All {len(by_total[64])} 64-cell BLIFs have 6 NOTs (matches Longhorn).")


if __name__ == "__main__":
    main()
