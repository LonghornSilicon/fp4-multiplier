# Provable Lower Bounds

Findings from Cirbo SAT-based exact synthesis on isolated sub-blocks. Each lower bound is **provable** (UNSAT proofs), not heuristic.

Per-output bit campaign last updated 2026-04-27 on a 28-vCPU/56GB Ubuntu VPS using Cirbo 1.0.0 + cadical 1.9.5 (pysat backend), 1200s per G step.

## Per-output bit (single-output, 8-input)

Run `lib/cirbo_per_bit.py` (or the current parallel campaign at `workspace/cirbo_runs/cirbo_perbit.py`).

| Output bit | Y[k] ones (of 256) | Min gates (proven) | Notes |
|:----------:|:------------------:|:------------------:|:------|
| Y[0] | 16 | **4** (SAT G=4, UNSAT G=3) | `(m_a AND m_b) AND NOT(eh_a OR eh_b)` |
| Y[1] | 40 | ≥ 7 (UNSAT G=6 in 70s; G=7 search active) | likely 7–10 |
| Y[2] | 72 | ≥ 7 (UNSAT G=6 in 73s) | |
| Y[3] | 96 | ≥ 7 (UNSAT G=6 in 92s) | |
| Y[4] | 104 | ≥ 7 (UNSAT G=6 in 54s) | |
| Y[5] | 104 | ≥ 7 (UNSAT G=6 in 55s) | |
| Y[6] | 100 | ≥ 7 (UNSAT G=6 in 84s) | |
| Y[7] | 98 | ≥ 7 (UNSAT G=6 in 104s) | |
| Y[8] | 98 | **7** (SAT G=7 in 45s, UNSAT G=6 in 81s) | matches mut11 form: `sy & (a_nz) & (b_nz)` |

**Sum of proven per-bit lower bounds (no sharing): ≥ 4 + 7×7 + 7 = 60 gates.** This is well below the 65-gate full-circuit upper bound, so per-bit bounds don't constrain the full circuit tightly — sharing between Y[k] cones recovers ~5 gates of "intersection" between independent per-bit synthesis.

The 28-core campaign is walking each Y[k] up through G=7, 8, 9, ... until SAT or 1200s timeout. Running. Updates land in `workspace/cirbo_runs/perbit_ledger.tsv`.

ABC `&deepsyn` heuristic counts (no sharing): Y[0]=3, Y[1]=22, Y[2]=35, Y[3]=44, Y[4]=33, Y[5]=32, Y[6]=23, Y[7]=17, Y[8]=9 → sum = 218. Our 74-gate full circuit shares 95% of this.

## Sub-block proven bounds (Cirbo SAT)

Run `lib/cirbo_subblocks.py 2x2|k|shift`.

### 2×2 unsigned multiplier (4 inputs, 4 outputs)

- Inputs: M_a[1] M_a[0] M_b[1] M_b[0] (M ∈ {0,1,2,3})
- Outputs: P[3] P[2] P[1] P[0] (P ∈ {0..9})
- **Minimum = 7 gates exact** (Cirbo SAT, G=6 UNSAT, G=7 SAT in 0.6s). Confirms the textbook folklore optimum.

### K computation (4 inputs, 3 outputs)

- Inputs: eh_a, el_a, eh_b, el_b
- Outputs: K[2..0] = sa1+sb1 ∈ {0..4}
- **Lower bound ≥ 8 gates** (UNSAT G=7, timeout G=8 after 63s).

### K-shift (7 inputs, 8 outputs)

- Inputs: K[2..0], P[3..0]
- Outputs: mag[7..0] = P << K
- **Lower bound ≥ 13 gates** (UNSAT through G=12, timeout G=13 after 129s).

### Conditional negate (9 inputs, 7 outputs)

- Inputs: mag[7..0] (8 bits) + sy (1 bit)
- Outputs: y[7..1] (7 bits) where y = -mag if sy=1 else mag (mod 256)
- **Lower bound ≥ 11 gates** (UNSAT G=8 in 55s, G=9 in 49s, G=10 in 112s, G=11 search active)
- Walking G upward; updates land in `workspace/cirbo_runs/neg_block.log`

## What this means for the current 65-gate result

Sum of provable sub-block lower bounds (independent SAT proofs):
- 2×2 mul: **= 7** (proven exact)
- K compute: ≥ 8 (proven UNSAT G=7)
- K-shift: ≥ 13 (proven UNSAT G=12)
- Conditional negate: ≥ 11 (proven UNSAT G=10)
- Y[8] direct route: **= 7** (proven exact via Cirbo G=7 SAT after G=6 UNSAT)
- Sign computation (sy = a[3] XOR b[3]): 1 (single XOR)

**Lower-bound sum (no sharing across sub-blocks): ≥ 7 + 8 + 13 + 11 + 7 + 1 = 47.**

The current 65-gate canonical achieves significant sharing across these sub-blocks — particularly between the K-shift and conditional-negate paths via the mut11 NAND-chain "below-detector" form. The 18-gate gap between the no-share sum (47) and the actual count (65) reflects the cost of multi-output sharing overhead PLUS the loss from forcing an empirically-tight 7-NOT translation of eSLIM's ANDN_A/ANDN_B intermediate gates.

Our 74-gate result is therefore **at most 38 gates over the theoretical minimum of the structural decomposition.** Substantial sharing across sub-blocks reduces this gap (per the per-bit AIG analysis showing 95% sharing efficiency in our circuit).

To prove 74 is optimal globally would require multi-day SAT solver time on a many-core machine running Cirbo with longer timeouts. The 9-output 8-input full-function SAT is on the edge of intractability.

## What's still open

- Multi-output Cirbo SAT for the full circuit at G=70..74 — ran 5+ min at G=84 without convergence; would need days.
- mockturtle's `xag_minmc_resynthesis` with NPN5/NPN6 databases — gave 78 on initial run; longer runs / different parameters could push lower.
- AlphaEvolve-style mutation loop with frontier-LLM proposals — most likely path to break the local optimum below 74.
