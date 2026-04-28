# Provable Lower Bounds

Findings from Cirbo SAT-based exact synthesis on isolated sub-blocks. Each lower bound is **provable** (UNSAT proofs), not heuristic.

Per-output bit campaign last updated 2026-04-27 on a 28-vCPU/56GB Ubuntu VPS using Cirbo 1.0.0 + cadical 1.9.5 (pysat backend), 1200s per G step.

## Per-output bit (single-output, 8-input)

Run `lib/cirbo_per_bit.py` (or the current parallel campaign at `workspace/cirbo_runs/cirbo_perbit.py`).

| Output bit | Y[k] ones (of 256) | Min gates (proven) | Notes |
|:----------:|:------------------:|:------------------:|:------|
| Y[0] | 16 | **= 4** (SAT G=4, UNSAT G=3) | `(m_a AND m_b) AND NOT(eh_a OR eh_b)` |
| Y[1] | 40 | **≥ 8** (UNSAT G=6 in 70s, G=7 in 3110s, 4hr budget) | tighter bound 2026-04-27 |
| Y[2] | 72 | **≥ 8** (UNSAT G=6 in 73s, G=7 in 4018s) | |
| Y[3] | 96 | **≥ 8** (UNSAT G=6 in 92s, G=7 in 2653s) | |
| Y[4] | 104 | **≥ 8** (UNSAT G=6 in 54s, G=7 in 2610s) | |
| Y[5] | 104 | **≥ 8** (UNSAT G=6 in 55s, G=7 in 4131s) | |
| Y[6] | 100 | **≥ 8** (UNSAT G=6 in 84s, G=7 in 3523s) | |
| Y[7] | 98 | **≥ 8** (UNSAT G=6 in 104s, G=7 in 3518s) | |
| Y[8] | 98 | **= 7** (SAT G=7 in 45s, UNSAT G=6 in 81s) | matches mut11 form: `sy & (a_nz) & (b_nz)` |

**Sum of proven per-bit lower bounds (no sharing): ≥ 4 + 8×7 + 7 = 67 gates.**

This sum is HIGHER than the actual 64-gate full-circuit upper bound — which is consistent with multi-output sharing: a single gate in the full circuit can contribute to multiple Y[k] cones simultaneously, so the sum is a loose UPPER bound on what an unshared (per-bit-independent) implementation would need, not a lower bound on the multi-output minimum.

The 28-core campaign tightened Y[1..7] from "≥ 7" to "≥ 8" by running each at G=7 with a 4-hour cadical195 budget and getting UNSAT proofs.

ABC `&deepsyn` heuristic counts (no sharing): Y[0]=3, Y[1]=22, Y[2]=35, Y[3]=44, Y[4]=33, Y[5]=32, Y[6]=23, Y[7]=17, Y[8]=9 → sum = 218. Our 64-gate full circuit shares ~70% of this.

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
- **Lower bound ≥ 11 gates** (UNSAT G=8 in 55s, G=9 in 49s, G=10 in 112s; G=11 TIMEOUT at 30min budget — could not decide)
- The bound is tight: increasing the budget on cadical195 at G=11 may resolve to SAT (= 11) or UNSAT (≥ 12)

## What this means for the current 64-gate result

Sum of provable sub-block lower bounds (independent SAT proofs):
- 2×2 mul: **= 7** (proven exact)
- K compute: ≥ 8 (proven UNSAT G=7)
- K-shift: ≥ 13 (proven UNSAT G=12)
- Conditional negate: ≥ 11 (proven UNSAT G=10; G=11 timed out)
- Y[8] direct route: **= 7** (proven exact via Cirbo G=7 SAT after G=6 UNSAT)
- Sign computation (sy = a[3] XOR b[3]): 1 (single XOR)

**Lower-bound sum from sub-block decomposition (no sharing): ≥ 7 + 8 + 13 + 11 + 7 + 1 = 47.**

The current **64-gate canonical** (achieved via gate-neutral XOR re-association + eSLIM size 8 seed 7777) achieves significant sharing across these sub-blocks — particularly between the K-shift and conditional-negate paths. The 17-gate gap between the no-share sum (47) and the actual count (64) reflects multi-output sharing overhead.

**Saturation evidence**: **124 distinct 64-gate solutions** found across 600+ eSLIM SAT-mode configurations spanning 5 distinct gate-neutral starting topologies × {sizes 6, 8, 10, 12, 14} × 5 seeds. **All 124 have exactly 6 NOTs.** No 5-NOT (sub-64-gate) solution found anywhere in the search space.

Independent corroboration:
- **mockturtle XAG** (different SAT engine, NPN-class cut rewriting): saturated at 87 internal — couldn't even match eSLIM's 58.
- **ABC `&deepsyn`** (heuristic, no SAT): saturated at 74; eSLIM beats it by 10.
- **Cirbo full-circuit SAT** at G=50/55/58/60: all OOM'd or timed out before producing UNSAT proofs.
- **Custom DIMACS encoder + kissat-direct on G=63**: 76K vars, 194M clauses, 5.2 GB CNF. Ran 16h 35m on a single core, stable 16 GB RSS, no verdict — instance is genuinely intractable on a non-dedicated machine. Killed 2026-04-28 to free the VPS.

The 17-gate gap between the no-share sub-block lower-bound sum (47) and the 64-gate full-circuit count reflects multi-output sharing overhead.

## Optimality assessment

**Is 64 the global minimum?** Honest assessment: **probably (≈70% confidence), not proven.**

### What pushes toward "yes"
- 124 independent search paths converged on 64 with the same 6-NOT signature
- Three structurally different optimization tools (eSLIM SAT, mockturtle XAG, ABC heuristic) all saturated at or above 64
- Y[0] = 4 and Y[8] = 7 proven exactly — the small-cone bounds are tight
- eSLIM's windowed SAT replacement (up to 14 gates per window) is genuinely strong; if a 5-NOT solution existed within any 14-gate sub-circuit of any of those 124 starting points, it would have been found

### What keeps it below "certain"
- **eSLIM is windowed.** Anything requiring non-local rearrangement spanning 20+ gates simultaneously is invisible to it.
- **Lower-bound gap is wide.** Best provable multi-output LB is ~30-40 gates; UB is 64. That's a 24-34 gate gap of pure ignorance.
- **AlphaEvolve / frontier-LLM mutation has not been run.** Identified as the highest-EV remaining move; needs API budget.
- **The 65→64 unlock came on 2026-04-27** via a move (gate-neutral starting-topology perturbation) that nobody had tried for the prior days. There may be one more such move at 64→63.
- **The kissat full-circuit UNSAT proof is the only thing that would have certified optimality.** It was attempted (G=63, 16h 35m) but is intractable in any reasonable time/cost budget on a shared VPS.

### Defensible writeup phrasing
> 64 gates with strong empirical optimality evidence: 124 distinct 64-gate solutions across 600+ SAT-based optimization configurations, multiple independent tools (eSLIM, mockturtle, ABC) all saturating at or above 64 with consistent 6-NOT signature. Formal optimality proof attempted via direct kissat on a custom DIMACS exact-synthesis encoding at G=63, but the 9-output 8-input multi-output SAT instance (5.2 GB CNF, 194M clauses) is on the practical edge of intractability and did not terminate within a 16-hour budget. We believe 64 is optimal but do not have a proof.

## What's still open

- **AlphaEvolve-style mutation loop with frontier-LLM proposals** — highest-EV remaining lever; will be run on Alan's own machine post-VPS-shutdown.
- **Multi-day kissat / Cirbo full-circuit SAT at G=63** on a dedicated CPU box — would either prove 64 is optimal (UNSAT) or yield the missing 63-gate netlist (SAT). Right hardware: cheap many-core CPU with no GPU, run for 1-2 weeks.
- **Custom symmetry-breaking / structural-hint augmentations to the SAT encoding** — could collapse the search space enough to make G=63 tractable in days rather than weeks.
