"""Generate all paper figures from ledger TSVs and progression history.

Outputs PDFs into ./paper/figs/ for inclusion via \\includegraphics.
Run from the repo root.
"""
import csv
import glob
from collections import Counter, defaultdict
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

plt.rcParams.update(
    {
        "font.family": "serif",
        "font.size": 10,
        "axes.titlesize": 11,
        "axes.labelsize": 10,
        "legend.fontsize": 9,
        "xtick.labelsize": 9,
        "ytick.labelsize": 9,
        "figure.dpi": 150,
        "savefig.bbox": "tight",
        "pdf.fonttype": 42,  # embed TrueType for camera-ready
    }
)

OUT = Path("paper/figs")
OUT.mkdir(parents=True, exist_ok=True)


def load_ledger(path):
    """Parse a ledger TSV; return list of dict rows (only ok=='OK', integer
    contest_cells)."""
    rows = []
    with open(path) as f:
        r = csv.DictReader(f, delimiter="\t")
        for row in r:
            if row.get("ok") != "OK":
                continue
            try:
                row["contest_cells"] = int(row["contest_cells"])
                row["init_internal"] = (
                    int(row["init_internal"])
                    if row.get("init_internal", "").isdigit()
                    else None
                )
                row["final_internal"] = (
                    int(row["final_internal"])
                    if row.get("final_internal", "").isdigit()
                    else None
                )
            except ValueError:
                continue
            rows.append(row)
    return rows


# ---------- Figure 1: Gate-count progression ----------
def fig_progression():
    # (label, gates, phase color group)
    history = [
        ("Naïve QM", 288, "manual"),
        ("v1: structural", 135, "manual"),
        ("v2: shared K×S", 126, "manual"),
        ("v3: direct formula", 101, "manual"),
        ("v4: zero=000", 89, "manual"),
        ("v4b: $\\text{sh}_6$", 88, "manual"),
        ("v4c: prefix-OR", 86, "manual"),
        ("v4d: $P_7=\\text{nz}$", 84, "manual"),
        ("v4e: SAT decoder", 82, "manual"),
        ("Independent search", 81, "manual"),
        ("Longhorn σ + eSLIM", 64, "auto"),
        ("eSLIM size-10 SAT\non 5-NOT seed", 63, "auto"),
    ]
    fig, ax = plt.subplots(figsize=(7.0, 3.4))
    xs = list(range(len(history)))
    ys = [h[1] for h in history]
    colors = ["#2b6cb0" if h[2] == "manual" else "#c05621" for h in history]
    ax.plot(xs, ys, "-", color="#888", lw=1, zorder=1)
    for x, y, c in zip(xs, ys, colors):
        ax.scatter(x, y, s=55, color=c, zorder=2, edgecolor="black", linewidth=0.5)
    for x, (lbl, y, _) in zip(xs, history):
        ax.annotate(
            f"{y}",
            (x, y),
            xytext=(0, 8),
            textcoords="offset points",
            ha="center",
            fontsize=8,
        )
    ax.set_xticks(xs)
    ax.set_xticklabels([h[0] for h in history], rotation=45, ha="right", fontsize=7.5)
    ax.set_ylabel("Gate count")
    ax.set_yscale("log")
    ax.set_yticks([60, 80, 100, 150, 200, 300])
    ax.get_yaxis().set_major_formatter(matplotlib.ticker.ScalarFormatter())
    ax.axhline(64, color="#c05621", lw=0.6, ls="--", alpha=0.6)
    ax.text(
        len(history) - 0.5,
        64,
        " Longhorn 64",
        color="#c05621",
        fontsize=8,
        va="center",
    )
    ax.set_title("Gate-count progression: structural decomposition $\\to$ SAT-based local search")
    # Manual legend
    from matplotlib.lines import Line2D

    legend_elems = [
        Line2D(
            [0],
            [0],
            marker="o",
            color="w",
            markerfacecolor="#2b6cb0",
            markeredgecolor="k",
            markersize=8,
            label="Manual / structural",
        ),
        Line2D(
            [0],
            [0],
            marker="o",
            color="w",
            markerfacecolor="#c05621",
            markeredgecolor="k",
            markersize=8,
            label="SAT-based (eSLIM)",
        ),
    ]
    ax.legend(handles=legend_elems, loc="upper right", frameon=True)
    ax.grid(True, axis="y", alpha=0.3)
    fig.tight_layout()
    fig.savefig(OUT / "fig_progression.pdf")
    plt.close(fig)


# ---------- Figure 2: Distribution of perturbation results ----------
def fig_perturbation_distribution():
    # Wave-1 ledgers (the post-resume runs that targeted the 63 + canonical 64)
    files = {
        "Exp A R3v2 (XOR re-assoc)": "experiments_eslim/exp_a_round3v2_ledger.tsv",
        "Exp D 63v2 (large window)": "experiments_eslim/exp_d_63v2_ledger.tsv",
        "Exp E 63 (NOT-elim)": "experiments_eslim/exp_e_63gate_ledger.tsv",
        "Exp F (canonical large)": "experiments_eslim/exp_f_ledger.tsv",
        "Exp H 63v2 (double-XOR)": "experiments_eslim/exp_h_63gate_v2_ledger.tsv",
    }
    all_counts = Counter()
    per_exp_counts = {}
    for name, path in files.items():
        rows = load_ledger(path)
        c = Counter(r["contest_cells"] for r in rows)
        per_exp_counts[name] = c
        all_counts.update(c)
    # Bins
    keys = sorted(set(all_counts.keys()))
    if not keys:
        return
    fig, ax = plt.subplots(figsize=(7.0, 3.2))
    bottom = np.zeros(len(keys))
    palette = ["#2b6cb0", "#dd6b20", "#319795", "#9f7aea", "#c53030"]
    for color, (name, c) in zip(palette, per_exp_counts.items()):
        ys = np.array([c.get(k, 0) for k in keys])
        ax.bar(keys, ys, bottom=bottom, color=color, edgecolor="black", linewidth=0.4, label=name)
        bottom += ys
    ax.axvline(63, color="#c05621", lw=1, ls="--")
    ax.text(63.05, max(bottom) * 0.95, "current best (63)", color="#c05621", fontsize=8, va="top")
    ax.set_xlabel("Contest gate count of resulting circuit")
    ax.set_ylabel("Number of eSLIM runs")
    ax.set_title("Distribution of contest-cell counts across wave-1 perturbation runs")
    ax.set_xticks(keys)
    ax.legend(loc="upper right", frameon=True, ncol=1, fontsize=8)
    ax.grid(True, axis="y", alpha=0.3)
    fig.tight_layout()
    fig.savefig(OUT / "fig_perturbation_dist.pdf")
    plt.close(fig)
    # Also dump the data summary for the table
    lines = ["Experiment\tRuns\tBest\tMedian\tCount@best"]
    for name, c in per_exp_counts.items():
        runs = sum(c.values())
        if runs == 0:
            continue
        vals = []
        for k, v in c.items():
            vals.extend([k] * v)
        vals.sort()
        best = vals[0]
        median = vals[len(vals) // 2]
        lines.append(f"{name}\t{runs}\t{best}\t{median}\t{c[best]}")
    (OUT / "perturbation_summary.tsv").write_text("\n".join(lines) + "\n")


# ---------- Figure 3: Exp G iterative chain divergence ----------
def fig_iterative_chains():
    rows = load_ledger("experiments_eslim/exp_g_63v2_ledger.tsv")
    # group by chain
    by_chain = defaultdict(list)
    for r in rows:
        by_chain[int(r["chain"])].append((int(r["step"]), r["contest_cells"]))
    fig, ax = plt.subplots(figsize=(6.2, 3.2))
    palette = ["#2b6cb0", "#dd6b20", "#319795", "#9f7aea"]
    for color, (chain, points) in zip(palette, sorted(by_chain.items())):
        points.sort()
        steps = [p[0] for p in points]
        cells = [p[1] for p in points]
        ax.plot(steps, cells, "-o", color=color, label=f"chain {chain}", lw=1.4, ms=5)
    ax.axhline(63, color="#c05621", lw=1, ls="--", label="seed = 63")
    ax.set_xlabel("Iteration step (eSLIM size=6 on prior output)")
    ax.set_ylabel("Contest gate count")
    ax.set_title("Iterative perturbation diverges from 63")
    ax.legend(loc="lower right", frameon=True, fontsize=8)
    ax.grid(True, alpha=0.3)
    ax.set_xticks(sorted({p[0] for ps in by_chain.values() for p in ps}))
    fig.tight_layout()
    fig.savefig(OUT / "fig_iterative_chains.pdf")
    plt.close(fig)


# ---------- Figure 4: Per-bit lower bound vs achieved cross-shared ----------
def fig_lower_bound():
    bits = [f"y{i}" for i in range(9)]
    mc_lb = [6, 6, 5, 5, 5, 5, 4, 4, 3]  # per-output ANF degree-1 LB
    monomials = [98, 102, 72, 97, 60, 54, 53, 20, 4]
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(7.0, 2.9))
    x = np.arange(len(bits))
    ax1.bar(x, mc_lb, color="#2b6cb0", edgecolor="black", linewidth=0.4)
    ax1.set_xticks(x)
    ax1.set_xticklabels(bits)
    ax1.set_ylabel("Per-output AND lower bound (deg − 1)")
    ax1.set_title("Per-output multiplicative complexity LB")
    ax1.axhline(sum(mc_lb), color="#c05621", lw=0.8, ls=":")
    ax1.text(8.2, sum(mc_lb), f" Σ = {sum(mc_lb)}", color="#c05621", fontsize=8, va="center")
    ax1.text(0.0, 25.5, "achieved (with cross-output sharing): 24", fontsize=8, color="#444")
    ax1.grid(True, axis="y", alpha=0.3)
    ax2.bar(x, monomials, color="#319795", edgecolor="black", linewidth=0.4)
    ax2.set_xticks(x)
    ax2.set_xticklabels(bits)
    ax2.set_ylabel("# distinct ANF monomials")
    ax2.set_title("ANF representation density")
    ax2.grid(True, axis="y", alpha=0.3)
    fig.tight_layout()
    fig.savefig(OUT / "fig_lower_bound.pdf")
    plt.close(fig)


# ---------- Figure 5: Cell-mix comparison 82 / 64 / 63 ----------
def fig_cell_mix():
    cats = ["AND2", "OR2", "XOR2", "NOT1"]
    versions = [
        ("Longhorn canonical (64)", [25, 12, 21, 6]),
        ("Ours (63)", [24, 12, 22, 5]),
    ]
    fig, ax = plt.subplots(figsize=(6.0, 3.0))
    x = np.arange(len(cats))
    width = 0.36
    palette = ["#dd6b20", "#319795"]
    offsets = [-width / 2, width / 2]
    for i, (name, vals) in enumerate(versions):
        ax.bar(
            x + offsets[i],
            vals,
            width,
            color=palette[i],
            edgecolor="black",
            linewidth=0.4,
            label=name,
        )
        for xi, v in zip(x + offsets[i], vals):
            ax.annotate(str(v), (xi, v), xytext=(0, 2), textcoords="offset points", ha="center", fontsize=7)
    ax.set_xticks(x)
    ax.set_xticklabels(cats)
    ax.set_ylabel("Gate count")
    ax.set_title("Cell-type mix: Longhorn 64 vs ours 63")
    ax.legend(loc="upper right", frameon=True, fontsize=8)
    ax.grid(True, axis="y", alpha=0.3)
    fig.tight_layout()
    fig.savefig(OUT / "fig_cell_mix.pdf")
    plt.close(fig)


if __name__ == "__main__":
    fig_progression()
    fig_perturbation_distribution()
    fig_iterative_chains()
    fig_lower_bound()
    fig_cell_mix()
    print("Wrote:", sorted(p.name for p in OUT.glob("*")))
