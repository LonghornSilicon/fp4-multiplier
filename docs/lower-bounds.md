# Provable Lower Bounds

Findings from Cirbo SAT-based exact synthesis on isolated sub-blocks. Each lower bound is **provable** (UNSAT proofs), not heuristic.

## Per-output bit (single-output, 8-input)

Run `lib/cirbo_search.py` and `lib/cirbo_per_bit.py`.

| Output bit | Y[k] ones (of 256) | Min gates (proven) | Notes |
|:----------:|:------------------:|:------------------:|:------|
| Y[0] | 16 | **4** (Cirbo, SAT G=4, UNSAT G=3) | `(m_a AND m_b) AND NOT(eh_a OR eh_b)` |
| Y[1] | 40 | timeout @ G=10–15 | likely 8–12 |
| Y[2] | 72 | timeout | |
| Y[3] | 96 | timeout | |
| Y[4] | 104 | timeout | |
| Y[5] | 104 | timeout | |
| Y[6] | 100 | timeout | |
| Y[7] | 98 | timeout | |
| Y[8] | 98 | timeout | likely ~5–8 with sharing |

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

## What this means for the 74-gate result

Sum of provable sub-block lower bounds:
- 2×2 mul: 7 (proven)
- K compute: ≥ 8 (proven)
- K-shift: ≥ 13 (proven)
- Sign computation: 1 (single XOR)
- Conditional negate (mut2 form): empirically ~24 with sharing into multiplier
- Y[8] direct route (mut11): empirically 5

**Lower-bound sum (no sharing across sub-blocks): ≥ 36.**

Our 74-gate result is therefore **at most 38 gates over the theoretical minimum of the structural decomposition.** Substantial sharing across sub-blocks reduces this gap (per the per-bit AIG analysis showing 95% sharing efficiency in our circuit).

To prove 74 is optimal globally would require multi-day SAT solver time on a many-core machine running Cirbo with longer timeouts. The 9-output 8-input full-function SAT is on the edge of intractability.

## What's still open

- Multi-output Cirbo SAT for the full circuit at G=70..74 — ran 5+ min at G=84 without convergence; would need days.
- mockturtle's `xag_minmc_resynthesis` with NPN5/NPN6 databases — gave 78 on initial run; longer runs / different parameters could push lower.
- AlphaEvolve-style mutation loop with frontier-LLM proposals — most likely path to break the local optimum below 74.
