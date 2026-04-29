# Analysis report — sub-63 search

Generated 2026-04-29. Snapshot of theoretical analyses + creative-track results
that complement the eSLIM perturbation search.

## #5 — Theoretical lower bound

Per-output ANF degrees and monomial counts under Longhorn's σ remap:

| bit | ones | degree | #monomials | mc-lb (=deg−1) |
|----:|----:|-------:|-----------:|---------------:|
|  y0 |  98 |   7    |     98     |       6        |
|  y1 |  98 |   7    |    102     |       6        |
|  y2 | 100 |   6    |     72     |       5        |
|  y3 | 104 |   6    |     97     |       5        |
|  y4 | 104 |   6    |     60     |       5        |
|  y5 |  96 |   6    |     54     |       5        |
|  y6 |  72 |   5    |     53     |       4        |
|  y7 |  40 |   5    |     20     |       4        |
|  y8 |  16 |   4    |      4     |       3        |

- **Per-bit deg−1 multiplicative complexity LB (no sharing): 43 ANDs**
- **Distinct monomials union (max sharing): 139**, degree distribution
  {2:9, 3:30, 4:49, 5:36, 6:13, 7:2}
- **Naive max-sharing AND LB: 437**
- **Per-output XOR LB: 551**

These are *very* loose. Our 63-gate solution uses **24 AND2** — far below the 43-LB
sum because of cross-output sharing — and **22 XOR2** — vastly below 551 because
real circuits use Boolean rewriting (De Morgan, distributivity, etc.) that ANF
synthesis cannot exploit.

**Conclusion:** ANF / monomial-based bounds are too weak to settle 62 vs 63.
Tighter bounds (Boyar-Peralta gate-elimination, communication-complexity)
would be needed.

## #2 — Algebraic re-derivation from ANF

Greedy monomial-sharing AND-XOR synthesis:
- **691 gates total** (140 AND + 551 XOR + 0 NOT)
- vs our 63-gate Longhorn-derived solution

Pure ANF synthesis is **~11× larger** than the Longhorn decomposition. This is
strong evidence that the structure of the multiplier reduction tree (partial
products, carry chain, MAJORITY/CARRY identities) provides compression that
generic monomial sharing cannot reach.

**Implication:** to find sub-63, we need methods that operate on circuit
*structure* (Boolean equivalence rewriting + window SAT), not on the
ANF representation. This re-validates the eSLIM-based approach but tells us
the perturbation set must be richer than XOR-re-association alone.

## #1 — SAT k=62 attempt (in progress)

eSLIM `--size 63` (full-circuit window) on `fp4_63gate_nobuf.blif`,
budget 600s. If it returns a 62-gate netlist, that's the headline result.
If it returns 63 (no improvement) within budget, we have empirical evidence
that 63 is at least *eSLIM-stable* under full-circuit SAT improvement.
True UNSAT proof would require a custom encoder.

## #4 — Iterative perturbation chains (Exp G, in progress)

4 chains × 5 iterations × size=6 × 90s/iter from `fp4_63gate_nobuf.blif`.
Each chain: eSLIM → output → eSLIM(output) → ... 5 deep. Tests whether
compound (multi-hop) basin transitions reach sub-63 where single-hop doesn't.

## #3 — LLM-guided rewriting (queued)

Requires `ANTHROPIC_API_KEY`. Not set in current env.
Plan: feed the 63-gate body + simulator harness to Claude API, ask for
gate-removal proposals, validate each via the bit-parallel simulator.
