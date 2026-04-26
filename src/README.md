# Canonical FP4 Multiplier — 70 Gates

Best verified FP4 multiplier netlist: **70 gates** over the contest gate library {AND2, OR2, XOR2, NOT1}, each = 1 unit. Verified correct on all 256 input pairs.

## Result

| Metric | Value |
|---|---|
| **Total gate count** | **70** |
| AND2 | 30 |
| OR2 | 10 |
| XOR2 | 21 |
| NOT1 | 9 |
| Verified on all 256 input pairs | [OK] |
| Synthesis flow | yosys → ABC `&deepsyn` (→ 74) → eSLIM `--syn-mode sat` (→ 70) → re-map to {AND2,OR2,XOR2,NOT1} |

## Trajectory

| Stage | Gates |
|---|---:|
| PLA + ABC FAST | 390 |
| Behavioral case-stmt Verilog | 222 |
| Structural Verilog (default encoding) + ABC | 86 |
| Best remap σ + ABC `&deepsyn -T 3 -I 4` | 85 |
| Raw-bit `lb = a[1]\|a[2]` collapse | 81 |
| mut2 NAND-chain conditional negate | 75 |
| mut11 raw P_nonzero direct-route Y[8] | 74 |
| **eSLIM SAT-based local improvement** | **70** |

5.6× reduction from naive PLA baseline.

## Input Remap σ = (0,1,2,3,6,7,4,5)

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

## How the 74→70 reduction was achieved

eSLIM ([SAT 2024 paper](https://drops.dagstuhl.de/entities/document/10.4230/LIPIcs.SAT.2024.23) by Reichl/Slivovsky) is a SAT-based local-improvement tool. Critical configuration choice:

- `--syn-mode sat` (NOT `--aig`) — preserves XOR2 in the basis. The AIG mode forced our 11 XOR2 gates to expand into 3 ANDs each, which `dch -f` couldn't fully recover. The non-AIG SAT mode treats XOR2 as a primitive and finds local rewrites that share more cleverly.

eSLIM operated on the 74-gate netlist for 240 seconds, found a sequence of small SAT-proven local improvements (windowed sub-circuit replacements), and produced a 70-gate netlist over a richer basis of {AND2, OR2, XOR2, AND-with-one-negated-input}. The translator turned the AND-with-one-negated-input gates into shared NOT1 + AND2 pairs (9 distinct nets needed inversion → 9 NOT1 gates).

Net result: 30 AND2 + 10 OR2 + 21 XOR2 + 9 NOT1 = 70.

## Files

- `fp4_mul.v` — Verilog source (mut11 form, used as the input to eSLIM via ABC's deepsyn)
- `fp4_mul.blif` — final 70-gate BLIF netlist (post eSLIM + retranslation)
- `contest.lib` — Liberty: AND2/OR2/XOR2/NOT1 area=1 each
- `synth.ys` — yosys script that produced the 74-gate BLIF (intermediate; eSLIM took it from there)

## Reproduction

The 74-gate ABC-only result reproduces deterministically from `fp4_mul.v`:

```bash
cd src && yosys synth.ys # produces 74-gate BLIF (deterministic)
```

The 70-gate result requires running eSLIM on the 74-gate AIG. See `experiments_external/eslim/README.md` for the eSLIM build instructions and runtime.
