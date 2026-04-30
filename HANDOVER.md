# HANDOVER — Resume after `git pull`

**Status as of 2026-04-30:** project is at a natural stopping point.
The 63-gate result is verified, the paper is finalized, and both repos
(this one and the LonghornSilicon mirror branch) are pushed.

If you're a future Claude session reading this on a fresh clone: read
this file first, then `paper/paper.tex` (or `paper/paper.pdf`), then
the most recent dated entry in `PROGRESS.md`. That's enough to resume
without grepping chat history.

---

## TL;DR

- **Headline:** verified 63-gate FP4 E2M1 × FP4 → QI9 multiplier in
  `{AND2, OR2, XOR2, NOT1}`. Beats LonghornSilicon's published 64-gate
  result by one gate.
- **Primary artifact:** `multiplier_63.py` (Python body) +
  `netlists/fp4_multiplier_63gate.blif` (gate-level netlist), both
  verified 256/256 by `eval_circuit.py`.
- **Paper:** `paper/paper.tex` (15 pages), frames 63 as **empirical
  optimum** — *not* provably optimal.
- **K=62 SAT:** attempted, hit 24h timeout (`EXIT=124`) on
  2026-04-30 20:31 UTC without a verdict. Question of K=62 remains
  formally open.

## What's where

| File | Purpose |
|---|---|
| `multiplier_63.py` | **Primary submission body** — verified 256/256, 63 gates. |
| `netlists/fp4_multiplier_63gate.blif` | Gate-level netlist (BLIF) for the same circuit. |
| `eval_circuit.py` | Verification harness — runs all 256 input pairs. |
| `etched_take_home_multiplier_assignment.py` | Official assignment harness. |
| `paper/paper.tex` | The paper. Section 5 holds saturation evidence; Section 5.5 holds the K=62 SAT attempt. |
| `PROGRESS.md` | Append-only experiment log. Most recent entry is the K=62 SAT timeout. |
| `DECISIONS.md` | Architectural decisions ledger. |
| `CONTEXT.md` | Earlier-session handoff (mostly historical now; superseded by this file). |
| `analysis/sat_exact.py` | PySAT/CaDiCaL exact-synthesis encoder (used for the K=62 attempt). |
| `analysis/REPORT.md` | Lower-bound + algebraic-synthesis analyses. |
| `experiments_eslim/` | All eSLIM perturbation drivers and ledgers (the 280+ run saturation campaign). |
| `autoresearch/multiplier.py` | The 81-gate v4f safe-fallback submission — **don't break this**, it's the rollback point. |

## State of the repos

**This repo** (`themoddedcube/fp4-multiplier-minimization`):
- Latest master: `10dc40e` ("K=62 SAT: 24h timeout reached, no verdict — finalize paper outcome")
- Working tree is clean.

**LonghornSilicon mirror** (`LonghornSilicon/fp4-multiplier`):
- User has collaborator push access (set local git config to
  `themoddedcube` / `themoddedcube@gmail.com` on any fresh clone).
- Branch `63-gate-eslim-size10` (commit `9a160f7`) carries the
  gate-level artifacts only: `src/fp4_mul.blif`, `src/fp4_mul.py`,
  `submission/colab_paste.py`, with the 64-gate canonical preserved
  at `*.64gate_backup`. README documents the 64 → 63 step.

## What was tried, in order

1. **Manual structural decomposition** (288 → 82 gates). Log-domain
   factorization `|v| = 1.5^M · 2^E`. Bottomed out at 82 — every
   stage locally optimal but cross-stage sharing required SAT.
2. **eSLIM windowed SAT on Longhorn 64-gate canonical** (verified
   their result locally; saturated at 64 under Phase 0 depth-1
   substitution + DCE).
3. **XOR re-association sweep** (12 locations × 2 sizes × 6 seeds =
   144 runs, 8 workers). Found a **5-NOT 64-gate variant** —
   contradicting the prior "all 124 known 64-gate solutions have
   6 NOTs" empirical claim.
4. **eSLIM `--syn-mode sat --size 10 --seed 1024`** on the 5-NOT
   variant → **63-gate solution**.
5. **Saturation campaign at 63** (~280 runs across XOR re-association,
   large-window direct, NOT-elim, double-XOR, iterative chains;
   11 alternative σ remaps; ABC `deepsyn` re-synthesis). Zero sub-63.
6. **K=62 SAT exact synthesis** on a GCP `n2d-highmem-8` (62 GiB).
   PySAT/CaDiCaL on a 250M-clause / 21,524-var encoding. Hit the 24h
   timeout cap without a verdict.

## If you want to push further

The 63-gate result is the natural shipping point. If you want to
formally settle K=62 anyway, two open paths:

1. **Kissat + cube-and-conquer** on the existing encoding —
   different solver (often 2-5× faster on hard UNSAT), parallelize
   across the vCPUs.
2. **Knuth/Kullmann-style reformulation** with auxiliary
   `in0_val[g][m]`, `in1_val[g][m]` variables — collapses the
   per-tuple clause set to `O(K · M · (8+K))` scale (roughly 10×
   clause reduction), should fit on a smaller box.

Empirical evidence (saturation across all heuristic methods) leans
moderately toward UNSAT (~70-75% subjective), but this is conjecture
not proof.

## Conventions

- **Git attribution.** Set local config on every fresh clone:
  ```
  git config --local user.name "themoddedcube"
  git config --local user.email "themoddedcube@gmail.com"
  ```
  Even on the LonghornSilicon repo (collaborator access; `themoddedcube`
  is the right author there too).
- **Don't break `autoresearch/multiplier.py`** — that's the 81-gate
  v4f safe fallback.
- **Don't claim 63 is provably optimal** — the paper carefully
  says "empirical saturation at 63", not "proven optimal".
- **eSLIM tooling** (if you want to rerun any sweep): build at
  `/tmp/eSLIM` from `https://github.com/fxreichl/eSLIM`. Always
  use `--syn-mode sat`; AIG mode loses ~25 gates on this circuit
  because XOR2 expands to 3 ANDs.

## Toolchain rebuild (only needed for re-running experiments)

```bash
# Python deps
python3 -m pip install --user pybind11 bitarray
pip install python-sat[pblib,aiger]    # for analysis/sat_exact.py

# eSLIM (only needed to re-run sweeps)
mkdir -p /tmp && cd /tmp
git clone --depth 1 https://github.com/fxreichl/eSLIM.git
cd /tmp/eSLIM && git submodule update --init --recursive --depth 1
cd src/bindings
cmake -B build -Dpybind11_DIR=$(python3 -c "import pybind11; print(pybind11.get_cmake_dir())")
cmake --build build -j 4

# pdflatex (only needed to recompile the paper)
sudo apt-get install -y --no-install-recommends \
  texlive-latex-recommended texlive-pictures \
  texlive-fonts-recommended texlive-latex-extra
```

## Paper-writer downstream

PROGRESS.md / DECISIONS.md / paper notes are written with
https://github.com/K-Dense-AI/claude-scientific-writer in mind as the
eventual final destination. Preserve negative results, methodology
rationale, and search trajectory at enough detail to reconstruct
the story.
