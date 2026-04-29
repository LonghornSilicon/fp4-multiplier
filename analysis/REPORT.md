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

## #1 — SAT k=62 attempt (memory-bound on this 23 GiB system)

Three angles tried:

1. **eSLIM `--size 63` (full-circuit window)** — OOM-killed within ~2 min
   (process VSZ exceeded 19 GiB before linker step).
2. **eSLIM `--size 20`** — climbed to 17.3 GiB RSS (70% of system RAM)
   within ~90 s, killed by us before system OOM.
   Empirical limit on this system: eSLIM windowed SAT is tractable up to
   ~size 14; beyond that, memory dominates wall time.
3. **Direct SAT encoder (`analysis/sat_exact.py`, PySAT/CaDiCaL)** — written but
   not run at K=62. Naive encoding emits clauses on every (g, m, s0, s1, kind)
   tuple → ~1.5 B clause attempts at K=62, intractable. Would need reformulation
   with auxiliary `in0_val[g][m]` / `in1_val[g][m]` variables (Knuth/Kullmann-style)
   to reduce to ~O(K · M · (8+K)) scale. Encoder kept in repo as scaffold for
   future runs on a larger machine.

**Verdict:** SAT-based exact synthesis at K=62 over 8 inputs / 9 outputs / 256
minterms is at the edge of tractability and not feasible on a 23 GiB machine.
Either rent a bigger box or settle for the empirical "63 is sticky across
all perturbation methods we tried" evidence.

## #4 — Iterative perturbation chains (Exp G, done)

4 chains × 5 iterations × size=6 × 90s/iter from `fp4_63gate_nobuf.blif`.
Each chain: eSLIM → output → eSLIM(output) → ... 5 deep.

**Result: 20 runs, contest distribution {64:3, 65:3, 66:5, 67:5, 69:4}.
Zero sub-63 and zero =63.** Every iteration converged to a 58-internal-gate
basin which translates to 64-69 contest cells. Iterating doesn't escape, and
in fact even loses the original 63 (the 63 corresponds to a particular 58-
internal arrangement that small-window iteration doesn't preserve).

**Implication:** the 63-gate result is *fragile* in the eSLIM size-6 landscape.
It was found by a single lucky size=10 SAT window on the 5-NOT 64-gate seed.
Re-discovering it in different starting topologies has roughly the same
probability as the original discovery — and we've spent ~300 runs trying.

## #3 — LLM-guided rewriting (queued)

Requires `ANTHROPIC_API_KEY`. Not set in current env.
Plan: feed the 63-gate body + simulator harness to Claude API, ask for
gate-removal proposals, validate each via the bit-parallel simulator.
