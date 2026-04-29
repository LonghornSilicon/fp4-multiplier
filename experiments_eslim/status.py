"""
Live status summary across all experiment ledgers.
Run: python3 experiments_eslim/status.py
"""
from __future__ import annotations
import sys
from pathlib import Path
from collections import Counter

REPO = Path(__file__).resolve().parent.parent

LEDGERS = [
    ("Round1",  REPO / "experiments_eslim/exp_a_ledger.tsv"),
    ("Round2",  REPO / "experiments_eslim/exp_a_round2_ledger.tsv"),
    ("Locs12+", REPO / "experiments_eslim/exp_a_locs_extra_ledger.tsv"),
    ("ExpD",    REPO / "experiments_eslim/exp_d_ledger.tsv"),
    ("ExpE",    REPO / "experiments_eslim/exp_e_ledger.tsv"),
    ("ExpF",    REPO / "experiments_eslim/exp_f_ledger.tsv"),
    ("ExpG",    REPO / "experiments_eslim/exp_g_ledger.tsv"),
]

BLIF_DIRS = [Path("/tmp/eslim_work"), Path("/tmp/eslim_work2")]


def parse_ledger(path: Path):
    if not path.exists():
        return []
    rows = []
    with open(path) as f:
        header = f.readline()
        for line in f:
            parts = line.strip().split("\t")
            rows.append(parts)
    return rows


def cell_breakdown(blif: Path):
    counts = Counter()
    with open(blif) as f:
        for ln in f:
            ln = ln.strip()
            if ln.startswith(".gate"):
                kind = ln.split()[1]
                counts[kind] += 1
    return counts


def find_low_not_blifs():
    """Find all translated BLIFs with fewer than 6 NOTs."""
    found = []
    for d in BLIF_DIRS:
        if not d.exists():
            continue
        for f in sorted(d.glob("*gates.blif")):
            try:
                c = cell_breakdown(f)
                total = sum(c.values())
                n_not = c.get("NOT1", 0)
                if n_not < 6 or total < 64:
                    found.append((total, n_not, f.name, dict(c)))
            except Exception:
                pass
    return sorted(found)


def main():
    print("=" * 65)
    print("EXPERIMENT STATUS SUMMARY")
    print("=" * 65)

    global_best = 999
    global_best_file = None

    for name, path in LEDGERS:
        rows = parse_ledger(path)
        if not rows:
            print(f"\n{name}: no data yet")
            continue
        # Find header cols
        header = None
        with open(path) as f:
            header = f.readline().strip().split("\t")
        try:
            ci = header.index("contest_cells")
            ok_i = header.index("ok")
        except ValueError:
            continue

        ok_rows = [r for r in rows if len(r) > ok_i and r[ok_i] == "OK"]
        cell_vals = []
        for r in ok_rows:
            try:
                v = int(r[ci])
                cell_vals.append(v)
            except (ValueError, IndexError):
                pass
        n_fail = len(rows) - len(ok_rows)
        best = min(cell_vals) if cell_vals else None
        dist = Counter(cell_vals)

        print(f"\n{name} ({path.name}):")
        print(f"  Rows: {len(rows)}  |  OK: {len(ok_rows)}  |  FAIL/timeout: {n_fail}")
        if cell_vals:
            print(f"  Best: {best}  |  Dist: {dict(sorted(dist.items()))}")
        if best is not None and best < global_best:
            global_best = best
            global_best_file = name

    print("\n" + "=" * 65)
    print(f"GLOBAL BEST: {global_best} contest cells  ({global_best_file})")
    print("=" * 65)

    print("\nLow-NOT translated BLIFs (< 6 NOTs or < 64 cells):")
    low = find_low_not_blifs()
    if not low:
        print("  None found yet.")
    for total, n_not, fname, c in low:
        marker = " *** SUB-64 ***" if total < 64 else ""
        print(f"  {fname}: total={total}, NOTs={n_not}, breakdown={c}{marker}")


if __name__ == "__main__":
    main()
