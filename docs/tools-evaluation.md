# Tools Evaluation — What Worked, What Didn't

Empirical results from this session. Useful for future Longhorn Silicon work; informs which tools to reach for first.

## Tools that delivered

| Tool | Use case | Best result | Notes |
|---|---|---|---|
| **yosys 0.64** | Verilog elaboration → BLIF / AIG | enabler for everything | Critical: structural Verilog elaboration is what allowed 222 → 86 transition. Behavioral case-stmt → memory cells is the failure mode; the `proc; opt; memory; opt; flatten; opt -full; techmap; opt` pass works for case-stmt + functions. |
| **ABC** (embedded in yosys-abc) | Logic synthesis | **74 gates final** | `&deepsyn -T 3 -I 4` saturates at 74. Longer T (10, 30, 60, 120, 600) did not improve. |
| **Cirbo 1.0.0** | SAT-based exact synthesis | proves Y[0]=4 (1.6s), 2×2 mul=7 (0.6s) | Tractable for ≤6-input single-output and ≤4-input multi-output. **NOT tractable** for 8-input × 9-output full circuit. |
| **sympy.logic** | 2-level SOP minimization | confirms ABC's sharing efficiency | Per-bit SOP totals 1627 gates no-share vs ABC's 74 with share = 95% sharing recovered. Y[0] SOP confirms minimum 4 gates. |

## Tool that broke 74 → 70 [best]

| Tool | What we tried | Result | Why it worked |
|---|---|---|---|
| **eSLIM (SAT 2024) `--syn-mode sat`** | Built from source, ran on flat-BLIF version of 74-gate netlist for 240s | **70 gates verified** | SAT-based windowed local improvement. The KEY was running in NON-AIG mode (preserves XOR2 in basis). 240s of SAT solver windowed minimization found 4 gates ABC's heuristic deepsyn missed. |

## Tools that didn't beat 74

| Tool | What we tried | Result | Why it didn't help |
|---|---|---|---|
| **eSLIM (SAT 2024) `--aig`** | AIG mode of the same tool | 91–94 gates | AIG mode reduces XOR2 to 3 ANDs, defeating the cost-aware optimization. Don't use AIG mode when your gate library has native XOR2. |
| **mockturtle XAG resynthesis** | Built from source, ran `cut_rewriting + xag_minmc_resynthesis` | 78 gates after re-mapping (raw XAG = 68 nodes) | XAG nodes don't 1:1 to our 4-cell library — inverter edges in XAG become explicit NOT1 in {AND,OR,XOR,NOT}. Inflates on tech-map. |
| **pyeda** | `pip install pyeda` | Build failed (Python 3.12 incompatibility) | Sympy is the working substitute. |
| **ABC `compress2x3`** | Strong-rewrite ABC script | 77 gates (worse) | Different local optimum; doesn't beat deepsyn. |
| **ABC `if -K 4 -a` LUT mapping** | LUT-based factoring | 147 gates (much worse) | Wrong granularity for unit-cost gate count. |
| **ABC `&deepsyn -T 600`** | 10-minute deepsyn budget | timeout (no convergence past 74) | Saturated; ABC's local optimum at this Verilog topology. |
| **OpenEvolve / AlphaEvolve loop** | (Identified as #1 path; needs API budget) | not yet attempted | Highest expected value for breaking 74. The "I am the LLM mutator" version of this got us from 85 to 74. |

## Heuristics that emerged

1. **Don't read PLA into ABC if you can avoid it.** Flat truth-table SOP is the worst starting AIG. Verilog → yosys → ABC is dramatically better (390 → 222 from this single change).
2. **Give the synthesizer the right *level* of structure, not the most.** Too-rigid hand structure (mut21's explicit isK indicators) made things worse than the simpler `mag = P << K` form.
3. **Algebraic identities at the Verilog level matter.** `lb = a[1] | a[2]` (raw bits) instead of `lb = eh OR el` with intermediate XOR saved 4 gates because it pre-collapses what ABC could only partially recover.
4. **Direct-route output bits whose function is independent of internal computations.** Y[8] = `sy & (a-nonzero) & (b-nonzero)` directly from raw inputs saved 1 gate by avoiding the long below-chain.
5. **NAND-chain is strictly better than running-OR for 2's-complement conditional negate** (in our specific topology). mut2's NAND form gave 75; mut23/mut10 running-OR gave 79–85.
6. **Sign-symmetric remaps strictly preferred.** Random non-sign-symmetric bijections gave ≥140 gates. Stay in the 8! = 40320 sign-symmetric subspace.
7. **Cirbo SAT is great for small sub-blocks, useless for full multi-output.** Use it to *prove* the optimality of components (2×2 mul = 7), not the whole circuit.

## What I would try next (in priority order)

1. **AlphaEvolve loop with frontier coder API** — the empirical evidence says creative LLM mutations can break ABC's local minima. The Karpathy-autoresearch infrastructure in `lib/strategy.py` + `docs/program.md` is ready.
2. **mockturtle's `exact_xag_resynthesis` per output cone** — apply SAT-based exact synthesis to *each Y[k] cone* separately. Different from cut_rewriting; may find tighter sub-circuits.
3. **eSLIM with a better starting AIG** — feed it our 78-gate XAG-derived AIG (instead of the 74-gate fully-mapped one) so it has more structural slack.
4. **Multi-day Cirbo with kissat solver** — if a CPU box is provided.

References for the tools above, with install commands, are in `PRD.md` §3 and `MEMORY.md` (the lit-survey agent's report).
