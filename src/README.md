# Canonical FP4 Multiplier — 64 Gates

Best verified FP4 multiplier netlist: **64 gates** over the contest gate library {AND2, OR2, XOR2, NOT1}, each = 1 unit. Verified correct on all 256 input pairs.

## Result

| Metric | Value |
|---|---|
| **Total gate count** | **64** |
| AND2 | 25 |
| OR2 | 12 |
| XOR2 | 21 |
| NOT1 | 6 |
| Verified on all 256 input pairs | OK |
| Synthesis flow | yosys → ABC `&deepsyn` (→ 74) → eSLIM `--syn-mode sat` (→ 70) → eSLIM `--syn-mode sat --size 8` (→ 65) → gate-neutral XOR re-association + eSLIM `seed=7777` (→ 64) → re-map to {AND2,OR2,XOR2,NOT1} |

## Trajectory

| Stage | Gates |
|---|---:|
| PLA + ABC FAST | 390 |
| Behavioral case-stmt Verilog | 222 |
| Structural Verilog (default encoding) + ABC | 86 |
| Best remap sigma + ABC `&deepsyn -T 3 -I 4` | 85 |
| Raw-bit `lb = a[1]\|a[2]` collapse | 81 |
| mut2 NAND-chain conditional negate | 75 |
| mut11 raw P_nonzero direct-route Y[8] | 74 |
| eSLIM SAT-based local improvement (size 6) | 70 |
| eSLIM SAT-based local improvement (size 8) on the 70-gate result | 65 |
| **Gate-neutral XOR re-association + eSLIM `--size 8 --seed 7777`** | **64** |

6.09× reduction from naive PLA baseline.

## Input Remap sigma = (0,1,2,3,6,7,4,5)

Sign-symmetric (sign at MSB), magnitude permutation:

| 4-bit code | value | | 4-bit code | value |
|:---:|:---:|---|:---:|:---:|
| 0000 | +0 | | 1000 | -0 |
| 0001 | +0.5 | | 1001 | -0.5 |
| 0010 | +1 | | 1010 | -1 |
| 0011 | +1.5 | | 1011 | -1.5 |
| 0100 | +4 | | 1100 | -4 |
| 0101 | +6 | | 1101 | -6 |
| 0110 | +2 | | 1110 | -2 |
| 0111 | +3 | | 1111 | -3 |

## How the 65→64 reduction was achieved

After 28+ eSLIM SAT configurations converged at 65 gates from the canonical 65-gate netlist, the unlock was **gate-neutrally perturbing the topology before the eSLIM call**. `workspace/eslim_runs/gen_variants.py` rewrites `XOR(XOR(a,b),c) → XOR(a,XOR(b,c))` at chosen wire locations — a gate-count-neutral move that hands eSLIM a structurally different starting AIG.

Re-running eSLIM (`--syn-mode sat --size 8 --seed 7777`, 900 s budget) on the `v2_assocA_w_75` variant converged to a **different 58-internal-gate solution** — one that uses only **6 distinct ANDN inverter sources** instead of the canonical 65's 7. Translation to contest cells: 58 internal + 6 shared NOTs = **64 total**.

Phase B saturation evidence: across 600+ eSLIM SAT configurations spanning 5 distinct gate-neutral starting variants, 5 sizes (6/8/10/12/14), and 5 seeds, **20+ distinct 64-gate solutions found, all with exactly 6 NOTs**. No 5-NOT solution found. 64 is the eSLIM-reachable floor under our contest cost metric.

## How the 70→65 reduction was achieved

Same eSLIM tool ([SAT 2024 paper](https://drops.dagstuhl.de/entities/document/10.4230/LIPIcs.SAT.2024.23) by Reichl/Slivovsky) that gave the 74→70 win, but with **larger SAT windows** (`--size 8` instead of the default `--size 6`). Larger windows find non-local restructurings that smaller windows can't see, at the cost of exponentially harder per-query time. With a 900-second budget, `--size 8` got through 1982 windows and converged on a 58-internal-gate solution that maps to 65 contest cells.

## Files

- `fp4_mul.v` — Verilog source (mut11 form, used as the input via ABC's deepsyn)
- `fp4_mul.blif` — final **64-gate** BLIF netlist (post-eSLIM + retranslation)
- `fp4_mul.blif.65gate_backup` — prior 65-gate canonical, preserved for reference
- `contest.lib` — Liberty: AND2/OR2/XOR2/NOT1 area=1 each
- `synth.ys` — yosys script that produced the intermediate 74-gate BLIF

## Reproduction

The 74-gate ABC-only result reproduces deterministically from `fp4_mul.v`:

```bash
cd src && yosys synth.ys  # produces 74-gate BLIF (deterministic)
```

The 70-gate result requires running eSLIM on the 74-gate flat BLIF (`--syn-mode sat`, default size 6, 240 s).
The 65-gate result requires eSLIM with `--size 8` on the 70-gate flat BLIF for 900 s.
The **64-gate** canonical: generate the `v2_assocA_w_75` gate-neutral variant via `workspace/eslim_runs/gen_variants.py`, then run eSLIM `--syn-mode sat --size 8 --seed 7777` for 900 s. See `experiments_external/eslim/README.md` for build and run instructions.
