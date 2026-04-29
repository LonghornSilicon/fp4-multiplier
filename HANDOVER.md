# HANDOVER — Lossless Resume Instructions

**Paste this into the new Claude Code session as your first message:**

---

> Read CONTEXT.md, PROGRESS.md, DECISIONS.md, and HANDOVER.md from
> /mnt/c/Users/themo/Desktop/Etched Multiplier Assignment top to bottom,
> then tell me where we left off and what you're about to do next.
> Don't start working until I confirm.

---

## CURRENT BEST: 63 gates ⭐

`multiplier_63.py` — verified 256/256 correct. Breakdown: 5 NOT1 + 24 AND2 + 12 OR2 + 22 XOR2 = 63.
Found by Exp D (size=10, seed=1024) on `fp4_64gate_5NOT_clean.blif`.
**This beats LonghornSilicon's published 64-gate result.**

## What's already done

- LonghornSilicon 64-gate solution verified locally.
- 5-NOT 64-gate BLIF found (`fp4_64gate_5NOT_clean.blif`, verified 256/256).
- Exp D large-window eSLIM (size=10, seed=1024 on 5-NOT BLIF) → **63-gate breakthrough**.
  - `fp4_63gate.blif` (with 4 BUF aliases), `fp4_63gate_nobuf.blif` (clean, for eSLIM pipeline).
  - `multiplier_63.py` created and verified.
- Exp E NOT-elimination → `fp4_64gate_4NOT.blif` (4-NOT 64-gate), `fp4_64gate_4NOT_nobuf.blif`.
- Two extra 5-NOT 64-gate variants from locs 12-15: `fp4_64gate_5NOT_loc12a_nobuf.blif`, `fp4_64gate_5NOT_loc12b_nobuf.blif`.
- BUF issue diagnosed: `parse_gate_blif` drops `.names X Y\n1 1` BUF entries → broken perturbed BLIFs.
  Fix: always use `_nobuf.blif` variants as canonical for any run that goes through parse→write→flatten.
- Exp D on 4-NOT BLIF in flight, getting 64-65 contest (no improvement over 64-gate baseline yet).

## What's running at handover — CHECK FIRST

```bash
ps aux | grep reduce.py | grep -v grep | wc -l
```

If ≥2, experiments are active. Expected active processes:

| Log | Script | Canonical | Workers | Status |
|-----|--------|-----------|---------|--------|
| `/tmp/exp_a_r2.log` | exp_a_parallel (Round 2) | fp4_64gate_5NOT_clean.blif | 4 (abhiclaude) | ~108/192 at context switch |
| `/tmp/exp_a_extra.log` | exp_a_locs_extra | fp4_64gate_5NOT_clean.blif | 2 | ~30/64 |
| `/tmp/exp_d_4not.log` | exp_d_large_window | fp4_64gate_4NOT.blif | 3 | ~9/24 |
| `/tmp/exp_a_r3.log` | exp_a_parallel (Round 3) | fp4_63gate_nobuf.blif | 2 | ~3/240, just launched |
| `/tmp/exp_e_4not.log` | exp_e_not_elim | fp4_64gate_4NOT_nobuf.blif | 2 | ~2/120, just launched |
| `/tmp/exp_d_63gate.log` | exp_d_large_window | fp4_63gate_nobuf.blif sizes=10,12,14 | 2 | 0/24, just launched |
| `/tmp/exp_h_63gate.log` | exp_h_double_xor | fp4_63gate_nobuf.blif | 2 | 0/256, just launched |
| `/tmp/exp_g_63gate.log` | exp_g_iterative | fp4_63gate_nobuf.blif | 2 | 0/8 chains, just launched |

**Total: ~19 eSLIM processes competing for 12 cores. All time-bounded.**

## Check for sub-63 results quickly

```bash
grep "contest=[0-5][0-9]\b\|contest=6[0-2]" /tmp/exp_a_r3.log /tmp/exp_d_63gate.log /tmp/exp_g_63gate.log /tmp/exp_h_63gate.log 2>/dev/null
```

Or scan ledgers:
```bash
awk -F'\t' '$7 < 63 && $7 != "?" {print FILENAME, $0}' experiments_eslim/exp_a_round3_ledger.tsv experiments_eslim/exp_d_63gate_ledger.tsv experiments_eslim/exp_g_63gate_ledger.tsv experiments_eslim/exp_h_63gate_ledger.tsv 2>/dev/null
```

## If sub-63 is found

1. Extract the BLIF from `/tmp/eslim_work2/` or `/tmp/eslim_work3/` — look for the file matching the winning variant/size/seed.
2. Translate to gates: `python3 experiments_eslim/blif_verify.py <blif>` or use `translate_to_gates` from exp_a_xor_reassoc.
3. Create `multiplier_62.py` (or whatever) following the pattern in `multiplier_63.py`.
4. Verify: `python3 eval_circuit.py multiplier_62.py` → must say CORRECT and N gates.
5. Update CONTEXT.md, PROGRESS.md, this HANDOVER.md.

## If experiments finish without sub-63

Next search directions (not yet launched):
- **Exp F**: large-window eSLIM on original 6-NOT 64-gate Longhorn canonical (never tried size=10/12 there).
  `python3 experiments_eslim/exp_f_canon_large.py --workers 3`
- **Round 4**: XOR perturbations of 4-NOT 64-gate nobuf BLIF.
  ```bash
  python3 experiments_eslim/exp_a_parallel.py \
    --canonical experiments_eslim/fp4_64gate_4NOT_nobuf.blif \
    --workdir /tmp/eslim_work3 --ledger experiments_eslim/exp_a_round4_ledger.tsv \
    --workers 3
  ```
- **Exp E on loc12a/b**: NOT elimination on the two extra 5-NOT 64-gate BLIFs.
  ```bash
  python3 experiments_eslim/exp_e_not_elim.py \
    --canonical experiments_eslim/fp4_64gate_5NOT_loc12a_nobuf.blif \
    --workers 2 --ledger-out experiments_eslim/exp_e_loc12a_ledger.tsv
  ```

## Critical architectural note: BUF issue

**NEVER pass a BLIF that contains BUF aliases through `parse_gate_blif` → `write_gate_blif`.**
BUF aliases are `.names X Y\n1 1` entries that parse_gate_blif silently drops.

Safe canonical BLIFs (no BUFs):
- `fp4_64gate_5NOT_clean.blif` — original 5-NOT (no BUFs, verified)
- `fp4_63gate_nobuf.blif` — 63-gate clean version
- `fp4_64gate_4NOT_nobuf.blif` — 4-NOT clean version
- `fp4_64gate_5NOT_loc12a_nobuf.blif`, `fp4_64gate_5NOT_loc12b_nobuf.blif`

Unsafe (have BUFs, only for exp_d which flattens directly):
- `fp4_63gate.blif` (4 BUFs)
- `fp4_64gate_4NOT.blif` (3 BUFs)
- `fp4_64gate_5NOT_loc12a.blif`, `fp4_64gate_5NOT_loc12b.blif`

## Key file paths

| File | Purpose |
|---|---|
| `multiplier_63.py` | **Primary submission — 63 gates, verified** |
| `autoresearch/multiplier.py` | 81-gate fallback — DON'T break |
| `experiments_eslim/fp4_63gate_nobuf.blif` | 63-gate BLIF (BUF-free, canonical for exp pipelines) |
| `experiments_eslim/fp4_64gate_5NOT_clean.blif` | 5-NOT 64-gate BLIF (original perturbation seed) |
| `experiments_eslim/fp4_64gate_4NOT_nobuf.blif` | 4-NOT 64-gate BLIF (alternate basin) |
| `experiments_eslim/exp_a_parallel.py` | XOR re-association perturbation + eSLIM sweep |
| `experiments_eslim/exp_d_large_window.py` | Direct eSLIM large window (no perturbation) |
| `experiments_eslim/exp_e_not_elim.py` | NOT-elimination rewrites |
| `experiments_eslim/exp_g_iterative.py` | Iterative eSLIM chains |
| `experiments_eslim/exp_h_double_xor.py` | Double XOR re-association |
| `experiments_eslim/exp_a_ledger.tsv` | Round 1 results |
| `experiments_eslim/exp_a_round2_ledger.tsv` | Round 2 results |
| `experiments_eslim/exp_a_round3_ledger.tsv` | Round 3 results (from 63-gate) |
| `experiments_eslim/exp_d_4not_ledger.tsv` | Exp D on 4-NOT BLIF |
| `experiments_eslim/exp_d_63gate_ledger.tsv` | Exp D large window on 63-gate |
| `experiments_eslim/exp_e_4not_ledger.tsv` | Exp E NOT-elim on 4-NOT BLIF |
| `experiments_eslim/exp_g_63gate_ledger.tsv` | Exp G iterative from 63-gate |
| `experiments_eslim/exp_h_63gate_ledger.tsv` | Exp H double XOR from 63-gate |
| `eval_circuit.py` | Frozen evaluation harness |
| `/tmp/eslim_work2/` | Scratch dir (tit user) |
| `/tmp/eslim_work3/` | Scratch dir (tit user, Round 3) |

## How to invoke eSLIM (reference)

```bash
PYTHONPATH=/tmp/eSLIM/src/bindings/build python3 /tmp/eSLIM/src/reduce.py \
  INPUT.blif OUTPUT.blif TIME_BUDGET_SEC \
  --syn-mode sat --size N --seed N
```

`--syn-mode sat` is REQUIRED (preserves XOR2 cost). Window sizes 6/8/10/12/14.

## Git state

Last commit: `c8c7edc` (Update HANDOVER: round 1 done, round 2 + exp_c in flight).
Need to commit: `multiplier_63.py`, all new BLIF files, all new experiment scripts, updated HANDOVER.md.
GitHub auth note: HTTPS not configured; use `git push git@github.com:...` via SSH.
