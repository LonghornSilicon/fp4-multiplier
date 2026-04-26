# Canonical FP4 Multiplier — 65 Gates

Best verified FP4 multiplier netlist: **65 gates** over the contest gate library {AND2, OR2, XOR2, NOT1}, each = 1 unit. Verified correct on all 256 input pairs.

## Result

| Metric | Value |
|---|---|
| **Total gate count** | **65** |
| AND2 | 25 |
| OR2 | 12 |
| XOR2 | 21 |
| NOT1 | 7 |
| Verified on all 256 input pairs | OK |
| Synthesis flow | yosys → ABC `&deepsyn` (→ 74) → eSLIM `--syn-mode sat` (→ 70) → eSLIM `--syn-mode sat --size 8` (→ 65) → re-map to {AND2,OR2,XOR2,NOT1} |

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
| **eSLIM SAT-based local improvement (size 8) on the 70-gate result** | **65** |

6.0x reduction from naive PLA baseline.

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

## How the 70->65 reduction was achieved

Same eSLIM tool ([SAT 2024 paper](https://drops.dagstuhl.de/entities/document/10.4230/LIPIcs.SAT.2024.23) by Reichl/Slivovsky) that gave the 74->70 win, but with **larger SAT windows** (`--size 8` instead of the default `--size 6`).

Larger windows mean SAT considers more gates per local-replacement query — at the cost of much longer per-query time. The trade-off is: bigger windows find non-local restructurings that smaller windows can't see, but each query is exponentially harder. With a 900-second budget, `--size 8` got through 1982 windows and converged on a 58-internal-gate solution that maps to 65 contest cells.

Two independent runs (`--size 6 -T 1200` and `--size 8 -T 900` from the 70-gate input) both found 58-internal-gate solutions, and both translated to 65 contest cells with slightly different cell mixes (25 vs 26 AND, 11 vs 12 OR). Strong signal that 65 is a robust local optimum at this window size.

## Files

- `fp4_mul.v` — Verilog source (mut11 form, used as the input via ABC's deepsyn)
- `fp4_mul.blif` — final 65-gate BLIF netlist (post-eSLIM + retranslation)
- `contest.lib` — Liberty: AND2/OR2/XOR2/NOT1 area=1 each
- `synth.ys` — yosys script that produced the intermediate 74-gate BLIF

## Reproduction

The 74-gate ABC-only result reproduces deterministically from `fp4_mul.v`:

```bash
cd src && yosys synth.ys  # produces 74-gate BLIF (deterministic)
```

The 70-gate result requires running eSLIM on the 74-gate flat BLIF (`--syn-mode sat`, default size 6, 240s).

The 65-gate result requires running eSLIM again with `--size 8` on the 70-gate flat BLIF for 900s. See `experiments_external/eslim/README.md` for build and run instructions.
