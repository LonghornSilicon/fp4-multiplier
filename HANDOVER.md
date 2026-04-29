# HANDOVER — Lossless Resume Instructions

**Paste this into the new Claude Code session as your first message:**

---

> Read CONTEXT.md, PROGRESS.md, DECISIONS.md, and HANDOVER.md from
> /mnt/c/Users/themo/Desktop/Etched Multiplier Assignment top to bottom,
> then tell me where we left off and what you're about to do next.
> Don't start working until I confirm.

---

## What's already done

- LonghornSilicon 64-gate solution verified locally (`longhorn_verify.py`).
- 81-gate independent line abandoned; pivoted to optimizing the 64-gate.
- Phase 0 triage (G1-G4): all NO HIT, gate-level moves exhausted.
- Phase 1 toolchain installed: `eSLIM` at `/tmp/eSLIM/src/bindings/build/`, `cirbo` via pip, `cmake`/`pybind11`/`bitarray` via pip --break-system-packages.
- Phase 4: `LONGHORN_DEEP_EXPLAINER.md` (~430 lines) written.
- Cirbo lower-bound runs (Experiment B): 6-NOT bundle from primary inputs is ≥10 gates.
- **🎯 VERIFIED 5-NOT 64-gate solution** at `experiments_eslim/fp4_64gate_5NOT.blif` — 256/256 correct, breakdown `5 NOT + 24 AND + 12 OR + 23 XOR = 64`. Contradicts Longhorn's "all 124 solutions have 6 NOTs" claim.

## What's running at handover (may still be alive — check first)

- **Round 1 ✅ FINISHED** (1365s wall): 144 jobs, 100 BLIFs translated, 20 64-cell variants found, 1 with 5 NOTs (the verified `fp4_64gate_5NOT_clean.blif`). No sub-64. Ledger: `experiments_eslim/exp_a_ledger.tsv`.
- **Round 2 in flight** seeded from `experiments_eslim/fp4_64gate_5NOT_clean.blif`: 192 jobs × 4 workers, ~70 min wall remaining at handover. Output: `/tmp/exp_a_r2.log`. Ledger: `experiments_eslim/exp_a_round2_ledger.tsv`. Currently at ~8/192.
- **Experiment C in flight** (Cirbo SAT on 9-in/8-out conditional negate at G=8..14): pushes the ≥11 lower bound that Longhorn timed out on. Output: `/tmp/exp_c.log`. Single-threaded.

To check: `ps aux | grep -E "exp_a_par|reduce.py|exp_c" | grep -v grep | wc -l` should be ≥ 5.

**Check status before doing anything:**
```bash
ps aux | grep -E "exp_a_par|reduce.py" | grep -v grep | wc -l
tail -10 /tmp/exp_a_par.log
```

If still running, let it finish (~10 more min). If dead, examine `experiments_eslim/exp_a_ledger.tsv` for results.

## EXACT next steps (priority order)

1. **DONE** ✅ — Fixed `blif_verify.py`, verified 5-NOT 64-gate BLIF passes 256/256. Pushed commit `0edda3d`.

2. **Round 2 perturbation seeded by the 5-NOT BLIF** (highest EV):
   - Add a `--canonical` argument support to `experiments_eslim/exp_a_parallel.py` (pretty sure it already accepts one, but verify).
   - Run with broader seed sweep starting from `experiments_eslim/fp4_64gate_5NOT.blif`:
     ```bash
     python3 experiments_eslim/exp_a_parallel.py \
       --canonical experiments_eslim/fp4_64gate_5NOT.blif \
       --time-budget 120 --sizes 6 8 10 \
       --seeds 1 42 7777 13371337 99 1024 31415 2718 \
       --max-variants 12 --workers 8 \
       --ledger experiments_eslim/exp_a_round2_ledger.tsv
     ```
   - Then run `python3 experiments_eslim/analyze_results.py` (modify it to scan `par2_*` or new pattern) to look for any 4-NOT or sub-64 BLIF.

3. **Experiment C** if no breakthrough: Cirbo SAT on the conditional-negate sub-block. Lower bound currently ≥11; if tightened to =11, locks down 64.

4. **Long-shot**: Modify eSLIM to ban the existing NOT signals as inputs to ANDs (force ANDN-via-XOR rewrite) and re-run on the canonical. May produce more 5-NOT or 4-NOT basins.

## Key file paths

| File | Purpose |
|---|---|
| `CONTEXT.md` | This session's resume-here doc (contains "EXACT next step") |
| `PROGRESS.md` | Append-only running log; latest entry 2026-04-28 |
| `DECISIONS.md` | Architecture choice ledger |
| `HANDOVER.md` | This file (lossless resume instructions) |
| `LONGHORN_STRATEGY.md` | High-level strategy explainer |
| `LONGHORN_DEEP_EXPLAINER.md` | Pedagogical line-by-line walk-through |
| `longhorn_verify.py` | Pasted 64-gate body wired to eval_circuit |
| `autoresearch/multiplier.py` | 81-gate v4f "safe" submission — DON'T break |
| `experiments_eslim/exp_a_parallel.py` | Currently-running parallel eSLIM sweep |
| `experiments_eslim/exp_a_ledger.tsv` | Sweep results (append-only) |
| `experiments_eslim/blif_verify.py` | BLIF→Python verifier (BROKEN on BUF lines) |
| `experiments_eslim/analyze_results.py` | Post-sweep analyzer (cell breakdown) |
| `experiments_eslim/exp_a2_pair_perturb.py` | Paired-perturbation driver (ready) |
| `experiments_eslim/exp_b_cirbo_cones.py` | Cirbo lower-bound runs |
| `triage/g*.py` | Phase 0 triage scripts |
| `eval_circuit.py` | Frozen evaluation harness |
| `etched_take_home_multiplier_assignment.py` | Official Etched harness |
| `/tmp/longhorn/fp4-multiplier/` | Longhorn reference repo (cloned, depth=1) |
| `/tmp/eSLIM/src/bindings/build/` | Compiled eSLIM bindings |
| `/tmp/eslim_work/` | Scratch dir for eSLIM I/O |
| `/home/abhiclaude/.claude/projects/-mnt-c-Users-themo-Desktop-Etched-Multiplier-Assignment/memory/` | Auto-loaded memory entries |
| `/home/abhiclaude/.claude/plans/ok-i-did-and-zesty-unicorn.md` | Approved plan (Phase 0-5) |

## Git state

Last pushed commit: `f8cda16` (parallel eSLIM sweep + Cirbo cone experiments + verifier + pair-perturb).

Anything uncommitted at handover (likely):
- Updated CONTEXT.md / PROGRESS.md / DECISIONS.md / HANDOVER.md.
- Updated experiments_eslim/exp_a_ledger.tsv (sweep adds rows live).
- experiments_eslim/analyze_results.py.

GitHub auth: `git config --global credential.helper store` — credentials cached in `~/.git-credentials` from this session. Push should work without re-prompt.

## Prerequisites already satisfied (don't re-do)

- pip packages: `pybind11`, `bitarray`, `cirbo`, `cmake` via `pip3 install --user --break-system-packages`.
- eSLIM cloned `git clone --recursive https://github.com/fxreichl/eSLIM.git /tmp/eSLIM`, built at `/tmp/eSLIM/src/bindings/build/` (3 .so files).
- Longhorn repo cloned at `/tmp/longhorn/fp4-multiplier/`.
- WSL dev tools: gcc, g++, make, git all installed (system).
- `yosys` NOT installed (skipped — eSLIM consumes BLIF directly; only needed for Phase 2 reproduction which we explicitly skipped).

## How to invoke eSLIM (reference)

```bash
PYTHONPATH=/tmp/eSLIM/src/bindings/build python3 /tmp/eSLIM/src/reduce.py \
  INPUT.blif OUTPUT.blif TIME_BUDGET_SEC \
  --syn-mode sat --size N --seed N
```

`--syn-mode sat` is REQUIRED (preserves XOR2 cost). Window sizes 6/8/10/12. Larger = slower but finds non-local replacements.

## How to translate eSLIM .names output to contest cells

```python
import sys
sys.path.insert(0, "/tmp/longhorn/fp4-multiplier/experiments_external/eslim/scripts")
from eslim_to_gates import main as e2g
in_names = ["a[0]","a[1]","a[2]","a[3]","b[0]","b[1]","b[2]","b[3]"]
out_names = [f"y[{i}]" for i in range(9)]
e2g("eslim_out.blif", "translated.blif", in_names, out_names)
# Then count: grep -c '^.gate' translated.blif
```

## Don't get distracted by

- Reproducing the 64-gate result via yosys+ABC. We skipped it intentionally; canonical BLIF is at `/tmp/longhorn/fp4-multiplier/src/fp4_mul.blif`.
- Working on the 81-gate netlist — that line is abandoned.
- Re-running Phase 0 triage; all four gates already returned NO HIT.
- Cirbo on small partial-reachability cones — don't-care issue makes UNSAT untrustworthy. B.4 (full-input cones, all minterms reachable) is fine.
