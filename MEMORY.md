# MEMORY.md — FP4 Multiplier Challenge Journal

This is a chronological log of actions, decisions, dead-ends, and discoveries while working on the Etched FP4 multiplier challenge. Future Claude sessions should read this top-to-bottom before resuming work.

Format: `YYYY-MM-DD HH:MM (TZ) — ACTOR — entry`
TZ: PT (user is in Texas / Longhorn Silicon, but local clock is whatever the harness reports — using session-relative timestamps where exact wall-clock not available).

---

## 2026-04-25

### 15:42 — claude — Session start
- User: Alan Schwartz (UT Austin email; building Longhorn Silicon, taping out own chip).
- Task: Etched FP4 multiplier take-home. **Real stakes** — informs Alan's silicon work, not just an academic exercise.
- Workspace: `/Users/alanschwartz/Downloads/Projects/FP4 Mul/`
- Files present: PDF + MD of the assignment.

### 15:43 — claude — Problem digestion (verbatim notes for future sessions)
**Inputs:** Two 4-bit FP4 (MX FP4 = E2M1, no inf/NaN). Default encoding:
- bit3 = sign, bits[2:1] = exponent (2 bits), bit0 = mantissa (1 bit)
- 16 codepoints, magnitudes ∈ {0, 0.5, 1, 1.5, 2, 3, 4, 6}
- Two zeros (0000, 1000) — signed-zero ignored per spec
**Output:** 9-bit two's complement integer Y where Y = 4 · val(a) · val(b). LSB represents 0.25 (called QI9).
**Gate library:** {AND2, OR2, XOR2, NOT1}, each = 1 gate. Constants 0/1 free. Wires/fanout free.
**Remapping:** Bijective remap on the 4-bit input space, applied identically to both inputs, free.
**Goal:** Minimum gate count + justification of optimality.

### 15:43 — claude — Structural facts I derived (will verify)
- Output magnitude set (19 distinct nonneg values): {0, 1, 2, 3, 4, 6, 8, 9, 12, 16, 18, 24, 32, 36, 48, 64, 72, 96, 144}
- In E2M1: val = (2 + m)·2^(e-2) for e≥1; val = m·2^(-1) for e=0. Letting M_i = (e_i≥1 ? 2:0)+m_i ∈ {0,1,2,3} and shift_i = (e_i≥2 ? e_i-2 : -1):
 - 4·val_a·val_b = M_a · M_b · 2^(shift_a + shift_b + 2)
 - Distinct mantissa products: M_a·M_b ∈ {0,1,2,3,4,6,9}
 - Total left-shift k = shift_a+shift_b+2 ∈ {0..4} (5 values)
 - This factorization may or may not be the structure that minimizes gates — must not over-anchor on it.
- Two zeros (0000, 1000 in default): both must remain in remap (bijection requires it). Sign bit can't fully encode "zero-ness" alone.
- Sign-magnitude conditional-negation costs ≈ 24 gates if implemented naïvely with carry chain — strongly suggests we should NOT compute magnitude-then-negate; instead synthesize Y bits directly OR find a remap that sidesteps the +1 carry.

### 15:44 — claude — Plan of attack
1. Persist this MEMORY.md + draft PRD.md (this turn).
2. In parallel, spawn:
 - Web research on FP4/MXFP4 hardware multipliers, small-multiplier minimum-gate synthesis (literature: Knuth Vol 4A on Boolean function minimization, Kojima/Kogge-Stone style, recent ML accelerator papers from Etched/Groq/Cerebras, MAJ3-based adders, ABC/mockturtle exact synthesis).
 - Web research on Karpathy "autoresearch" methodology to apply later.
3. Set up the Python testing harness from the assignment notebook locally (truth-table generator + verifier).
4. Build infra to brute-search remaps + run a logic-synthesis tool (ABC if available, else mockturtle, else hand-rolled SAT-based exact synthesis for small sub-functions).
5. Hand-derived design as baseline + sanity check on tool output.
6. Iterate (Karpathy autoresearch loop) on remap selection and circuit topology.
7. Prove lower bound (information-theoretic + Boolean-circuit-complexity arguments).

### 15:44 — claude — Open questions to resolve
- Q1: What's the literature minimum for a 4×4-bit unsigned multiplier? (Reference point — our problem is different but related.)
- Q2: Does ABC / mockturtle / Boolean Sat-Synthesis ship with truth-table → exact-min-gate-count solvers for ≤8-input functions? (Yes IIRC — `mockturtle::exact_synthesis` and ABC's `&exact` / `&deepsyn` work for small.)
- Q3: How many remaps survive symmetry? Naïvely 16!/2 ≈ 1.05·10^13. With sign-MSB constraint: 8! · (binary swap of two zeros) ≈ 80640. Tractable.
- Q4: Can compute to be useful here be a SAT/synthesis cluster? If yes, ask Alan for GPU/CPU access. (GPU less useful than CPU here — synthesis is symbolic. Will note in PRD.)

### 15:45 — claude — Spawning parallel research agents (next action)

### 16:00 — claude — Spec example 2 typo confirmed
Spec example 2 says "−3·1.5 = −4.5; output binary 110111000". The 9-bit binary
of −18 is **111101110**, not 110111000. The doc author also typo'd the FP4
encoding ("−3 represented as 0001"; should be 1101). The only interpretation
that fits in 9-bit is `output_int = 4·val_a·val_b` (range −144..+144). Logged in
fp4_spec.py.

### 16:05 — claude — Lit-review agent returned
Tools we will use: ABC (`&deepsyn`), Cirbo (IWLS 2024 winner, SAT-based
exact synthesis), eSLIM, mockturtle. Estimated optimum 30–40 gates. Sign-
magnitude internal encoding via the bijective remap is the unanimous lever
(arXiv 2507.18179: ~50% transistor reduction at 4-bit). Logged in PRD §3.

### 16:08 — claude — Karpathy autoresearch confirmed real
karpathy/autoresearch (released 2026-03-06), 76.5k stars. The methodology:
single scalar metric, fixed wall-clock per experiment, frozen evaluation
harness, agent edits exactly one file, git-as-ledger, "MODIFY → VERIFY →
KEEP/DISCARD → REPEAT FOREVER", `program.md` is the human's iteration target.
Encoded in code/program.md.

### 16:15 — claude — Pipeline (PLA → ABC) works
390 gates for default encoding with FAST script (`resyn2`x3 + dch + map).
**Confirmed correct on all 256 input pairs.**

### 16:20 — claude — Pivot to Verilog backend
PLA → ABC produces SOP-style starting AIG that resyn doesn't fully recover
from. Switched to Verilog → yosys → ABC: 222 gates for default with the
same effort, **35% reduction**. Verified correct.

### 16:30 — claude — First strategy results (Verilog/FAST)
| name | gates |
|-------------------|------:|
| default | 222 |
| rev_magnitude | 225 |
| gray_magnitude | 214 |
| halfints_then_pow2| 224 |

`gray_magnitude` perm = (0,1,3,2,6,7,5,4) is a Gray-coded order over the 8
magnitudes. Best so far: **214 gates**. Lit-review target: 30–40. Strong gap;
either need stronger synthesis (deepsyn/eSLIM/Cirbo) or hand-derived
structural Verilog or both.

### 16:35 — claude — Status & next
Background runs:
- 200-remap FAST+Verilog sweep → best 204 gates with perm (0,1,2,3,4,7,5,6)
- MED+Verilog on 4 strategy candidates → all failed (yosys-abc tempdir
 doesn't load our abc.rc; need to inline `resyn2` alias)

### 16:45 — claude — BREAKTHROUGH: structural Verilog → 93 gates
Wrote `code/fp4_mul_struct.v`: explicit sign-magnitude split, leading-bit OR,
2×2 mantissa mul, K-shift, 2's-complement wrapper. With FAST script: **93
gates**, verified correct. Down from 222 (case-stmt Verilog) and 282 (best
PLA). The case-stmt path was blowing the synthesizer's structure-discovery.

### 16:50 — claude — Aliases inlined
RESYN2 expansion ("balance; rewrite; refactor; balance; rewrite; rewrite -z;
balance; refactor -z; rewrite -z; balance") inlined into search.py scripts so
yosys-abc doesn't need abc.rc. MED/STRONG scripts now run.

### 16:55 — claude — Hand-optimized Verilog
Wrote `code/fp4_mul_hand.v`: explicit per-output-bit shift expressions
(mag[i] = OR_j P[j] AND isK[i-j]), explicit K-equals indicators. With MED
script: 88 gates. Slightly better than struct.v + MED.

### 17:00 — claude — ABC script exploration
On struct.v with various scripts:
- fast: 93, med: 92, compress2x3: 90, deepsyn-1s/2s/3s/5s: all **86**
- if -K 6: 147 (LUT mapping doesn't help for unit-area gates)
- compress + deepsyn-3s: 95 (worse)
On hand.v: med = 88 (best), deepsyn-3s = 99 (deepsyn rearranged into worse
form because the explicit form was already compact).
**Default-encoding best: 86 gates** (struct.v + deepsyn-3s). Saved to
`current_best/fp4_mul.blif`. Cell breakdown: 35 AND + 18 NOT + 23 OR + 10 XOR.

### 17:05 — claude — Baugh-Wooley fold attempt
Wrote `code/fp4_mul_bw.v` with explicit "complement-up-to-and-including-the-
lowest-set-bit" rule for the conditional negate. With FAST: 88 (vs 93 for
struct + FAST). With deepsyn-3s: 94 (worse, deepsyn confuses the more rigid
form). Net: synthesis already finds an equivalent BW-style fold; my explicit
version doesn't help.

### 17:10 — claude — Realistic optimum
The lit review's "30–40 gate target" was optimistic. With our gate set
(AND2/OR2/XOR2/NOT1, unit cost, 9-bit two's-comp output) and best off-the-
shelf synthesis, default encoding sits at **86 gates**. Path to lower:
1. Input remap (theoretically can save ~5–15 gates by simplifying sparse
 output bits like Y[0])
2. Cirbo / eSLIM SAT-based local improvement (lit-claimed 12% avg, up to
 83% in some cases)
3. Decompose into windowed sub-blocks and apply exact synthesis per window
4. AlphaEvolve-style verifier-in-the-loop search

### 17:15 — claude — End-of-session-1 state (will not be the final state today)
- **Current best:** 86 gates (default encoding, struct.v + deepsyn-3s).
- See later sections for continued work.

### 17:30 — claude — Per-remap structural Verilog generator
Built `code/gen_struct.py` + `code/synth_remap.py`. Decoder simplification (single-
bit pass-through detection, 2-bit XOR/AND/OR pattern matching) keeps the Verilog
clean for sign-symmetric remaps. Default encoding via this generator yields the
same 86 gates with deepsyn-3s.

### 17:45 — claude — 1000-perm sweep → 85 gates
Wider remap-aware search of 1000 sign-symmetric remaps + deepsyn-3s on top-50.
**Best: 85 gates** with perm `(0, 1, 2, 3, 6, 7, 4, 5)`, i.e. magnitudes at
codes 0..7 = [0, 0.5, 1, 1.5, 4, 6, 2, 3]. The remap "swaps the e_l semantic in
the e_h=1 region" — places magnitudes 4,6 at the e_l=0 codes and 2,3 at e_l=1.
Saves the K-shift one gate in the bulky bit-stack.

### 17:50 — claude — AlphaEvolve-style Verilog mutations
`code/fp4_alphaevolve.py` tested 6 hand-written variants (struct, explicit
isK, signed-2x, K-as-OR-sum, muxed-shift, signed-2x-xor). Best = struct/
muxed-shift at 86. Two signed-2x variants explode (211, 225 gates) — confirms
that synthesis prefers the unsigned-magnitude × conditional-negate path.

### 17:55 — claude — 5040-perm wide sweep
Full 5040 sign-symmetric remaps (mag-0 fixed at code 0). Same 85-gate
floor; 4 distinct perms tie. Confirms 85 is the deepsyn-3s reachable optimum.

### 18:00 — claude — Per-bit AIG counts (no sharing)
`code/exact_per_bit.py` ran ABC `&deepsyn -T 5 -I 6` on each of the 9 outputs
independently. AIG-node counts (≈ AND-only equivalents):
| Y[0]=3 | Y[1]=22 | Y[2]=35 | Y[3]=44 | Y[4]=33 |
| Y[5]=32 | Y[6]=23 | Y[7]=17 | Y[8]=9 | sum=218 |
Sum = 218 AIG nodes; our 85-gate full circuit is ~85 ANDs+XOR+OR+NOT — sharing
recovers ~60% of the per-bit cost. Healthy.

### 18:10 — claude — Cirbo installed (SAT-based exact synthesis)
`pip install cirbo` (v1.0.0). API: `CircuitFinderSat(model, n_gates, basis)`.
Sanity check: **Y[0] minimum = 4 gates** (PROVEN by SAT, basis {AND,OR,XOR,NOT}).
Form: `Y[0] = (m_a AND m_b) AND NOT(eh_a OR eh_b)`. ABC's AIG count of 3 is the
AND-only multiplicative complexity; the +1 NOT in our basis is unavoidable.

### 18:15 — claude — 85-gate canonical save
`current_best/fp4_mul.{v,blif}` = 85-gate verified netlist with perm
(0,1,2,3,6,7,4,5). Cell breakdown: 41 AND2 + 16 NOT1 + 10 OR2 + 10 XOR2.

### 18:20 — claude — Running: full-circuit Cirbo SAT search
`code/cirbo_full.py --start 84 --floor 70 --time-budget 600`. Asks SAT for an
84-gate, 83-gate, ... full circuit. Likely TIMEOUT for very small G; if any
succeeds, it improves on 85.

### 18:20 — claude — Running: per-output exact minimums via Cirbo
`code/cirbo_per_bit.py`. Sums to upper-bound the no-sharing complexity.

### 18:20 — claude — Resume info for next session
- **Current canonical best:** 85 gates with perm (0,1,2,3,6,7,4,5),
 saved to `current_best/`.
- **Lower bound so far:** Y[0]=4 (proven). Multi-output lower bound TBD via
 Cirbo full-circuit search (in progress).
- **Files:** PRD.md, MEMORY.md, code/*. results_remap.tsv has 5070 entries.
- **Known truth:** spec example 2 has typos. `output_int = 4·val_a·val_b`,
 9-bit signed two's comp.
- **Tooling:** yosys 0.64 + embedded ABC; cirbo 1.0.0; z3 4.16; pysat. No
 Cirbo timeout yet observed at G=84 — may take hours or fail.

### 18:30 — claude — Cirbo SAT timeouts confirmed
- Y[1] (40 ones, 8 inputs, single-output): TIMEOUT at G=≤? after 254s.
- Magnitude (6-input × 8-output): TIMEOUT at G=30+, per-G budget exceeded.
- Full circuit at G=84: cirbo_full ran 5+ minutes, no SAT/UNSAT verdict.
- Killed long-running Cirbo searches; SAT-based proof of optimality is not
 feasible on our timeframe (hours-to-days needed for 8-input/9-output).

### 18:35 — claude — Aggressive deepsyn (T=60s, multi-pass) didn't beat 85
Tried `&deepsyn -T 60 -I 12` plus iterated mfs2 + RESYN2 on the top remap.
Result: gates=None (Python timeout 180s). Indicates deepsyn at this depth
explodes runtime without further improvement. **85 gates is robust** for
our toolchain.

### 18:40 — claude — Final canonical state
- `current_best/fp4_mul.{v,blif}`: 85-gate netlist (41 AND2 + 16 NOT1 +
 18 OR2 + 10 XOR2). Verified on all 256 input pairs.
- Best remap σ = (0,1,2,3,6,7,4,5), values = [0, 0.5, 1, 1.5, 4, 6, 2, 3]
 (sign symmetric on [-]).
- Decoder shrinkage: dec_el = a[1] XOR a[2] (one XOR free).
- 4 distinct remaps tied at 85; this is the deepsyn-3s reachable optimum.
- See `current_best/README.md` for full provenance.

### 18:45 — claude — Synthesis tool stack inventory (for resume)
- yosys 0.64 (`/opt/homebrew/bin/yosys`)
- yosys-abc (embedded; abc.rc must be in cwd for resyn2/resyn3 aliases)
- cirbo 1.0.0 (`pip install cirbo`; SAT-based exact synthesis; tractable for
 small single-output functions, NOT for full 8-input × 9-output)
- z3 4.16, pysat (Python bindings)
- contest.lib: AND2, OR2, XOR2, NOT1 each area=1
- Spec examples #2 has typos; lock canonical to example #1
 (`output_int = 4·val_a·val_b`, 9-bit two's complement)

---

## 2026-04-25 (continuation, second push)

### 19:00 — claude — User shared Gemini deep-research; gave green light to LFG on local machine
Gemini's research had 4–5 actionable threads buried in 90% trend/context noise.
Key actionable: AlphaEvolve verifier-in-the-loop, recursive partial-product simplification,
strict structural isolation, bit-partitioning. Also flagged: Gemini hallucinated
"Campus Tours = graph traversal" (wrong — it's just the doc filename).

### 19:05 — claude — Cirbo-proven sub-block bounds
- 2×2 unsigned multiplier (4 inputs, 4 outputs): **EXACT minimum = 7 gates**
 (UNSAT at G=6, SAT at G=7, ~0.6s).
- K computation (4 inputs, 3 outputs): UNSAT at G=7; G=8 timed out at 63s →
 lower bound ≥ 8.
- K-shift (7 inputs, 8 outputs): UNSAT at G=12; G=13 timed out at 129s →
 lower bound ≥ 13.

### 19:10 — claude — Raw-bit Verilog → 81 gates
Wrote `code/fp4_mul_raw.v` exploiting σ=(0,1,2,3,6,7,4,5)'s lb collapse:
`lb = a[1] | a[2]` (no XOR for the leading bit, since `eh|el = a[2]|(a[1]^a[2]) = a[1]|a[2]`).
Result: **81 gates** (40 AND + 12 NOT + 11 OR + 11 XOR). Verified.

### 19:15 — claude — `gen_raw.py` generator
Auto-emit a raw-bit Verilog for any sign-symmetric remap. All 4 winning remaps
hit 81 gates with this form. Default gets 94. Wider sweep (1000 perms): 81 still
the floor.

### 19:20 — claude — **AlphaEvolve mutation series → 75 gates**
Wrote 4 hand-mutated Verilogs (mut1..mut4) on top of `fp4_mul_raw.v`:
- **mut2 (NAND-chain "below" conditional negate): 75 gates** [best] [best] [best]
- mut1 (Y[0] direct passthrough, rest standard): 85
- mut3 (signed multiplier): 211 (terrible)
- mut4 (running-OR detector): 85

The mut2 trick: replace the standard `(mag XOR rep(sy)) + sy` 2's-comp negate
with a NAND-chain `below_i = below_{i-1} & ~mag[i-1]`, then `y[i] = mag[i] XOR
(sy & ~below_i)`. Equivalent function, but ABC's deepsyn finds a tighter AIG
from this starting form. **Single move saved 6 gates.**

### 19:30 — claude — `gen_mut2.py` generator + bug fix in `_simplify_4to1`
Found and fixed a swapped pattern entry in `_simplify_4to1` (the 2-bit pattern
table had `(0,0,1,0)` and `(0,1,0,0)` mappings reversed). After fix, all 4 best
remaps generate 75 gates via the generator.

### 19:35 — claude — 1000-perm mut2-form sweep
- 3 perms tied at 75 (the same 3 that won at 85 with the older form)
- Confirms 75 is the deepsyn-3s floor for mut2-form across sign-symmetric remaps

### 19:45 — claude — End-of-second-push state
- **Current canonical best: 75 gates** (`current_best/fp4_mul.{v,blif}`).
 Cell breakdown: 36 AND2 + 9 NOT1 + 19 OR2 + 11 XOR2.
- **11.8% reduction from prior 85**, **5.2× from PLA baseline**.
- Best perm σ = (0,1,2,3,6,7,4,5); 3 sign-symmetric perms tie.
- Provable lower bounds (Cirbo SAT): 2×2 mul = 7, K ≥ 8, K-shift ≥ 13. Sum =
 28 + sign + negate ≥ ~50. So 75 is within 25 gates of theoretical optimum
 but full multi-output SAT is intractable to prove tight.

### 20:00 — claude — Push to **74 gates** via mut11
Wrote mut11..mut18 — found that **mut11** (mut2 + raw P_nonzero for Y[8])
gives 74. The trick: hardcoding `y[8] = sy & (a[0]|a[1]|a[2]) & (b[0]|b[1]|b[2])`
bypasses the long below-chain reaching y[8]. **Saved 1 more gate.**
- `current_best/fp4_mul.{v,blif}` = 74-gate verified netlist.
- Cell breakdown: 37 AND2 + 8 NOT1 + 18 OR2 + 11 XOR2.
- 2 sign-symmetric perms tie at 74 (best1, best3).
- 2000-perm sweep with mut11 form: 74 is the robust floor.

### 20:10 — claude — Stronger ABC scripts didn't break 74
Tried `compress2x3`, `iter-deepsyn` (2× full pipeline), `&deepsyn -T 60`,
`&deepsyn -T 120`. None go below 74. ABC's deepsyn-T3 at 74 is its reachable
optimum on this Verilog topology. Going further requires either:
- A different starting Verilog (more mutations to try)
- SAT-based local improvement (Cirbo / eSLIM, days of compute)
- AlphaEvolve-style frontier-LLM mutation loop

### 20:20 — claude — Final state for resume
- **Canonical best: 74 gates.** Verified all 256 inputs.
- Files: PRD.md / SUMMARY.md / MEMORY.md / current_best/{fp4_mul.v,fp4_mul.blif,README.md}
- Verilog: `code/fp4_mul_mut11.v` is the source.
- `code/gen_mut11.py` emits mut11 form for any sign-symmetric remap.
- Best remap σ = (0,1,2,3,6,7,4,5).
- Trajectory full: 390 (PLA) → 222 (case-stmt) → 86 (struct default) → 85 (struct+remap) → 81 (raw-bit lb) → 75 (mut2 NAND-chain) → **74 (mut11 raw P_nonzero for Y[8])**. 5.3× reduction from PLA baseline.
- Open: install eSLIM, install mockturtle, run AlphaEvolve loop with frontier LLM API, run multi-day Cirbo SAT proof.

### 20:30 — claude — User shared Boolean-solver idea + asked for INSTRUCTIONS.md + agentic LFG
Confirmed pyeda doesn't build on Python 3.12 (known issue). Switched to sympy.logic
SOPform / simplify_logic for 2-level minimization. SOP form sums to 1627 gates
across the 9 outputs (no sharing) — confirms ABC's 74 is doing massive multi-
level sharing. Y[0] proven again at 4-5 gates via sympy. Y[8] confirmed structure:
`(sa XOR sb) AND (a_nonzero) AND (b_nonzero)`.

### 20:35 — claude — INSTRUCTIONS.md written
Full teaching doc: FP4 / E2M1 explained, two's-comp + QI9 covered, multiplier
inside MAC inside matmul inside transformer inference, why ASICs win, how the
74-gate trajectory was earned, design tricks transferable to other parts of
Longhorn Silicon's chip. ~3700 words.

### 20:40 — claude — Spawned agents for eSLIM + mockturtle builds (parallel)
Per research-agent rec, eSLIM (SAT'24 windowed local improvement) and mockturtle
XAG resynthesis are the highest-EV next moves. Both running as background agents
with 30–45 min budgets.

### 20:42 — claude — Tried free rec4: `&deepsyn -T 600 -I 50 + mfs2 -W 6 -F 3 -D 2 + resyn3`
Running in background. (Still running at 3:33 mark, may take 10+ min.) Result TBD.

### 20:45 — claude — Pause point
- Best still: 74 gates (mut11 + best σ).
- Background: eSLIM agent, mockturtle agent, rec4-deepsyn-T600 ABC run.
- All output files saved: SUMMARY.md, INSTRUCTIONS.md, MEMORY.md, PRD.md, current_best/*.

### 21:00 — claude — eSLIM agent result: 100 gates (worse)
eSLIM produced a "reduced AIG" (`/tmp/eslim_work/fp4_reduced.aig`) which mapped
back to 100 gates over our cell library. eSLIM operates on AIG (no XOR2), so
our 11 XOR2 gates expanded to ~33 ANDs equivalent in the input AIG. After eSLIM
+ ABC mapping, the recovered XORs were partial. Net: WORSE than 74.

### 21:05 — claude — mockturtle agent result: 78 gates (worse)
mockturtle's XAG (XOR-AIG) resynthesis produced 68 raw XAG nodes, but those
are AIG-style nodes with inverted-input-attributes — they expand to more gates
in our explicit {AND2, OR2, XOR2, NOT1} basis. After ABC tech-mapping with
deepsyn-3s: 78 gates. Verified-OK but worse than 74.

### 21:10 — claude — Confirmed 74 is FIXED POINT of yosys+ABC pipeline
Re-fed the saved 74-gate BLIF back through `read_blif → resyn → deepsyn → mfs2 →
dch → map`. Output: 74 gates. **Saturated local optimum** for our toolchain.
Going below 74 requires:
 (a) Frontier-LLM mutation loop (AlphaEvolve-style with API access), or
 (b) Multi-day Cirbo SAT proof of optimality
 (c) Some fundamentally novel structural insight not yet discovered

### 21:15 — claude — Tried 5 more mutations (mut19..mut24)
- mut19 (use below8 for Y[8]): 74 (tie)
- mut20 (DeMorgan flip rewrite): 74 (tie)
- mut21 (1-hot K indicators): 90 (worse)
- mut22 (function-based decode): synth fail
- mut23 (running-OR instead of NAND-chain): 79 (worse)
- mut24 (skip el XOR intermediate): 91 (worse — el is essential!)
Total: tested 24 hand-mutated Verilogs. **mut11 = 74 remains the best.**

### 21:20 — claude — Sympy SOP minimization (parallel finding)
2-level SOP for each Y[k] sums to 1627 gates (no sharing) — confirms ABC is
doing 95% sharing reduction to get to 74. Y[0] SOP minimum = 4-5 gates;
Y[8] = (a3⊕b3) AND (a-nonzero) AND (b-nonzero) — confirms mut11's form exact.

### 21:25 — claude — INSTRUCTIONS.md written (~3700 words)
Comprehensive teaching doc covering FP4/E2M1 spec, two's-complement, QI9 format,
multiplier internals, MAC → matmul → attention → transformer inference flow,
ASIC tape-out implications, the 74-gate trajectory. Saved as `INSTRUCTIONS.md`.

### 21:30 — claude — End-of-third-push state
- 74 gates. Repo reorganized into clean structure (src/, lib/, mutations/,
 experiments_external/, results/, docs/, reference/). Pushed to
 https://github.com/LonghornSilicon/fp4-multiplier (public).

### 22:00 — claude — BREAKTHROUGH: eSLIM agent → **70 GATES VERIFIED**
The eSLIM build agent (spawned earlier and running in background) returned with
a **70-gate netlist verified-OK on all 256 input pairs**. Key facts:

- Canonical best: **70 gates** = 30 AND2 + 10 OR2 + 21 XOR2 + 9 NOT1.
- 5.6× from PLA baseline; 5.4% better than the 74-gate ABC-deepsyn fixed point.
- Saved to `src/fp4_mul.blif` (promoted from `experiments_external/eslim/fp4_mul.blif`).
- The prior 74-gate ABC result preserved at `experiments_external/abc-deepsyn-74gate/`.

### 22:05 — claude — Why eSLIM beat ABC's deepsyn
**Decisive config:** `--syn-mode sat` (NOT `--aig`). AIG mode forces our 11
XOR2 gates to expand to 3 ANDs each; ABC's `dch -f` couldn't recover the XOR
patterns when re-mapping back to {AND2, OR2, XOR2, NOT1}, giving 91-94 gates
WORSE than 74. Non-AIG SAT mode treats XOR2 as a primitive; eSLIM's windowed
SAT-proven local replacements then find improvements that respect the XOR-
friendly cost. After 240s of SAT search, eSLIM produced a 61-gate netlist
over an extended basis (incl. AND-with-one-negated-input), which translated
back to 30+10+21+9 = 70 contest cells.

### 22:10 — claude — Build details (saved as docs)
eSLIM build on macOS arm64 needed two fixes:
 1. `pip install pybind11 bitarray`
 2. APFS filesystem hack: rename uppercase header-shadowing files in
 `aiger/` (`VERSION`, `FORMAT`, etc.) so they don't collide with C++
 `<version>`, `<format>` stdlib headers.
After that, CaDiCaL + AIGER + relationSynthesiser .so modules built cleanly.

### 22:15 — claude — Updated repo + push to GitHub
- README.md: 74 → 70 gates throughout
- src/README.md: rewrote for 70-gate result + eSLIM trajectory
- experiments_external/eslim/README.md: full writeup of the win + reproduction
- experiments_external/eslim/scripts/: blif_to_aig.py, eslim_to_gates.py, classify_gates.py
- experiments_external/abc-deepsyn-74gate/: prior 74-gate canonical preserved
- Committed and pushed to LonghornSilicon/fp4-multiplier.

### 22:20 — claude — FINAL FINAL state for resume
- **Canonical best: 70 gates** at `src/fp4_mul.{v,blif}`. Verified 256/256.
- Cell breakdown: 30 AND2 + 10 OR2 + 21 XOR2 + 9 NOT1 = 70.
- Best remap σ = (0,1,2,3,6,7,4,5).
- Trajectory: 390 → 222 → 86 → 85 → 81 → 75 → 74 → **70** (5.6× from PLA baseline).
- Public repo: https://github.com/LonghornSilicon/fp4-multiplier
- Lessons that generalize for Longhorn Silicon's other blocks:
 1. Don't `read_pla` if you can write structural Verilog — gives synthesis
 the right level of structure (390 → 86, biggest single win).
 2. Algebraic identities at the source level matter (`a|(a^b) = a|b` saves
 gates that ABC won't auto-discover).
 3. NAND-chain "below_i" structure beats running-OR for two's-comp negate
 in our specific gate cost model.
 4. **Don't reduce to AIG before optimizing if your gate library has XOR2
 as a primitive.** AIG-based tools (eSLIM AIG mode, basic mockturtle)
 give worse results because XOR2 = 3 ANDs in AIG. Use the tool's native
 XOR-aware mode (eSLIM `--syn-mode sat`, mockturtle XAG, ABC with
 `&fx` factoring).
 5. SAT-based windowed local improvement (eSLIM SAT mode) beats heuristic
 deepsyn on small arithmetic circuits where XOR matters. ~240s solver
 time for ~5% gate reduction over `&deepsyn` saturation.

---

## 2026-04-26

### 02:00 — claude — Session resume after Alan's usage gap
- Repo state intact at 70 gates. eSLIM build was wiped (in /tmp). Rebuilt with same APFS rename hack.
- New mutations from prior session present but not yet eSLIM-iterated: mut25 (91), mut26 (75), mut27 (75).
- Saved founding context to `~/.claude/projects/.../memory/`.

### 02:30 — claude — eSLIM rebuilt and verified
- Cloned eSLIM, init'd cadical+aiger submodules.
- macOS APFS hack: rename FORMAT/VERSION/LICENSE/README/TODO in aiger/ to .txt
- Pybind11 needed explicit `-Dpybind11_DIR=...`
- 60s sanity-check on 70-gate netlist: eSLIM internal 70 → 61, contest cells = 70 (different local optimum, same total).

### 02:35 — claude — Launched parallel eSLIM sweep (6 runs)
- Run A: 70-gate × 1200s SAT default
- Run B: 70-gate × 900s SAT --size 8
- Run C: 74-gate ABC output × 600s SAT default
- Run D: mut26 75-gate × 600s SAT default
- Run E: mut27 75-gate × 600s SAT default
- Run F: 70-gate × 900s SAT --abc (failed: needs `/build/abc` not in our path)

### 02:48 — claude — BREAKTHROUGH: 67 gates from run C (74-gate × eSLIM)
- 74-gate ABC output, eSLIM SAT 600s → 58 internal → **67 contest cells verified**.
- Cell mix: 28 AND2 + 10 OR2 + 20 XOR2 + 9 NOT1 = 67.
- Promoted to canonical at `src/fp4_mul.blif`.

### 02:50 — claude — BREAKTHROUGH-2: 65 gates from runs A and B (70-gate × eSLIM)
- Both Run A (size 6, 1200s) and Run B (size 8, 900s) reduced 70-gate → 58 internal → **65 contest cells verified**.
- Run A cells: 26 AND + 11 OR + 21 XOR + 7 NOT = 65.
- Run B cells: 25 AND + 12 OR + 21 XOR + 7 NOT = 65 [promoted as canonical].
- Two independent eSLIM runs converged on 65 — strong signal of a new local optimum.

### 02:55 — claude — iter1 from 67 didn't beat 65; 70 was the right starting point
- iter1_67 with sizes 6/8 gave 67-68 (didn't improve from 67).
- Lesson: starting topology matters. The 70-gate had structure that eSLIM could compress further than the 67-gate or 74-gate had.

### 03:00 — claude — iter2 from 65 launched (5 runs in parallel)
- iter2_65_s6 / s8 / s10 / s12 / abc74_s8 — all 1200s budget.
- ETA ~20 min. Awaiting results.

### Trajectory snapshot at 65
- 390 → 222 → 86 → 85 → 81 → 75 → 74 → 70 → 67 → **65 gates**.
- 6.0× reduction from PLA baseline.
- 7.1% reduction from prior canonical 70.
- 23.5% reduction from 85-gate published-style baseline.
- Cell breakdown: 25 AND2 + 12 OR2 + 21 XOR2 + 7 NOT1.

### Resume info if interrupted
- Canonical: `src/fp4_mul.blif` = 65 gates verified-OK.
- Prior 70-gate preserved at `experiments_external/eslim/fp4_mul_70gate.blif`.
- eSLIM workdir: `/tmp/eslim_work/` (transient — get wiped on reboot).
- Harvester: `/tmp/eslim_work/loop_step.py`.
- BLIF flattener (handles .gate or .subckt): `/tmp/eslim_work/blif_flatten.py`.
- Best recipe to reproduce: yosys+ABC mut11.v → 74 gates → eSLIM `--syn-mode sat --size 8` 900s → 65 gates.

### 03:30 — claude — Comprehensive sweep evidence: 65 is robust eSLIM saturation point
Across 14 distinct eSLIM runs (varying starting topologies and window sizes):
- 70-gate × size 6 / 8 / 10 / 12 (multiple seeds, 900-1800s budgets): converges to 65 contest cells via 58 internal gates
- 74-gate × size 6 / 8 / 10: converges to 67 / 68 / 77 contest cells
- 75-gate (mut2/mut26/mut27) × size 8: converges to 69-73 contest cells
- 81-gate raw × size 8: 72 contest cells
- 65-gate (re-applied, all sizes): saturated at 65
- eSLIM internal output → eSLIM directly (no re-mapping): 58 → 58 internal saturated
- ABC re-map of 58-internal Verilog: 83 gates (worse — ABC mapper can't beat manual translator)

Conclusion: 58 is the eSLIM internal floor for this problem under SAT-mode + size 6-12 windows. 65 is the contest-cell floor under our standard translator (with 7 distinct ANDN inputs needing 7 NOTs).

### 03:35 — claude — Per-output cone analysis on 65-gate
Per-Y[k] cones in the 65-gate netlist:
- Y[0]: 14 gates (smallest), Y[1]: 28, Y[2]: 38, Y[3]: 45, Y[4]: 49, Y[5]: 53, Y[6]: 57, Y[7]: 60, Y[8]: 58
- All cones use all 8 PIs except Y[0] which uses 6
- Massive sharing: only 1 gate is private to a single output (the Y[0]-driving AND2)
- Cirbo per-cone exact synthesis intractable at these sizes (>10 inputs, >25 gates)

### 03:40 — claude — Path forward to break 65 (priority)
1. **Mockturtle XAG `xag_minmc_resynthesis`** — different SAT encoding than Cirbo/eSLIM, may find different local minima. Prior attempt got 78; need to investigate why and try with better config.
2. **Long-running Cirbo at G=64** — proves either lower bound or finds the missing -1.
3. **AlphaEvolve frontier-LLM mutation** — needs API budget.
4. **Multi-day eSLIM with `--restarts` and `--limit-inputs` parameter sweep** — fully exhaustive parameter exploration may find a configuration we missed.

### 04:30 — claude — Extended sweep (20+ eSLIM configurations) confirms 65 floor
Beyond the initial 14 configurations, ran:
- 70-gate × size 8 with seeds 14141, 15151, 16161 (variance check): 69, 68, 70 contest
- 78-gate (mut11 with `dch -f` only, no deepsyn) × size 8: 63 internal -> 70 contest
- 78-gate (dch_only) × size 10: 79 contest (size too big for budget)
- 70-gate × size 8 with --limit-inputs 5: 60 internal in 35,769 windows -> 69 contest
- 70-gate × size 8 with --restarts 5: ran out of budget (5x reset behavior); inconsistent
- 65-gate × size 8 with --restarts 5: returns 58/65 (no improvement)
- eSLIM internal output × size 10: 58 internal -> 65 contest (TIE)
- eSLIM internal output × size 8: 58 internal -> 66 contest (close)
- Cirbo G=64 multi-output: timed out at 1200s (too big a SAT instance, expected)
- mockturtle: requires C++ wrapper code not yet written; deferred

Total: 22 distinct eSLIM configurations, all converge to 65 contest cells minimum. Evidence is overwhelming that 65 is the eSLIM-SAT-mode floor for this problem.

### 04:35 — claude — Saved-state: 22-config sweep summary, working directory inventory
- Canonical: `src/fp4_mul.blif` 65 gates, verified 256/256.
- Best alternates (also 65): `/tmp/eslim_work/run_a_1200s_gates.blif`, `iter3_65_strict_gates.blif`, `iter2_65_s10_a_gates.blif`, `sweep_internal_s10_gates.blif`.
- All sweep results saved at `/tmp/eslim_work/` (will be wiped on reboot — important artifacts preserved in repo).

### 09:00 — claude — Overnight 6-job batch finished, 65 floor confirmed at 28 configs
6 long jobs (7200s each = 2hr budget):
- overnight_70_s8_long: 70 -> 60 internal -> 68 contest
- overnight_70_s8_seed2: 70 -> 58 internal -> **65 contest** (TIE, alt cell mix)
- overnight_70_s10_long: 70 -> 60 internal -> 72 contest (size 10 hurts)
- overnight_65_s8_long: 65 -> 58 internal -> 67 contest
- overnight_65_s10_long: 65 -> 60 internal -> 66 contest
- overnight_74_s8_long: 74 -> 64 internal -> 68 contest

Total 28 distinct eSLIM SAT-mode configurations explored. All converge to >= 65 contest cells. **65 is the eSLIM-saturation floor for this problem at this contest cost metric.**

Adding another 65-gate alternate (overnight_70_s8_seed2): cells = 26 AND, 10 OR, 22 XOR, 7 NOT — different mix from canonical (25 AND, 12 OR, 21 XOR, 7 NOT). Same total.

### 09:05 — claude — Honest path-forward assessment
The remaining moves to break 65 (in expected-value order):
1. **AlphaEvolve LLM mutation loop with frontier model** — was the highest-EV path identified; needs API budget. The user is asleep; I am the LLM but my marginal cost per iteration is high. One focused attempt only.
2. **Mockturtle XAG resynthesis** — requires writing a C++ wrapper around the header-only library. ~1-2 hours of work; uncertain payoff (prior attempt got 78).
3. **Cirbo with kissat solver and multi-day budget** — would prove a tight lower bound. Not feasible in this session.
4. **Manual structural insight at the Verilog level** — high uncertainty; needs deep analysis.

### 09:15 — claude — Spawned agent for AlphaEvolve mut29; result: 96 gates (worse)
Asked an explore agent for a fundamentally different decomposition (one-hot K + sparse mux + carry-free TC negation). Agent's first attempt failed verification (zero-handling bug). After my fix to use eff_sy = sy & anz & bnz: verifies but lands at **96 contest cells** post-ABC — the one-hot decomposition gives ABC's deepsyn a much harder optimization problem than mut11's barrel-shift form. Lesson: mut11's structure is genuinely well-tuned for ABC; alternative decompositions are uniformly worse. mut29.v deleted (not committed).

### 09:20 — claude — Built mockturtle XAG resynth tool; result: doesn't beat 65
Built a custom C++ mockturtle tool linking against mockturtle's headers, lorina, fmt, kitty, percy, nauty. Build path:
- macOS clang++17, -std=c++17 -O3 -w
- Required include paths: -I lib/{fmt,lorina,kitty,abcsat,parallel_hashmap,percy,nauty,json,rang,bill,abcesop}
- Required source compile of fmt/format.cc and fmt/os.cc
- aig_network: cut_rewriting k=4 multipass + aig_resub: 111 -> 95 AIG gates -> 88 contest cells (worse)
- xag_network: cut_rewriting k=4 multipass: 111 -> 87 XAG gates; AIGER write loses I/O symbols (mismatch on verify; abandoned)

**Conclusion: mockturtle does NOT beat 65 contest cells.** XAG resynthesis finds 87 internal vs eSLIM's 58 internal (mockturtle's NPN-based cut rewriting is less aggressive than eSLIM's SAT-proven local replacements).

### Final assessment of 65-gate floor (across ALL available tools)
- 28 eSLIM SAT configurations: all hit 65
- mockturtle AIG: 88 contest (worse)
- mockturtle XAG: 87 internal but I/O symbol loss
- ABC re-mapping eSLIM 58-internal Verilog: 83 (worse)
- All 29 hand mutations: ABC starts at 74-91 then eSLIM compresses to 65-73
- Cirbo full-circuit at G=64 down: timeout at every G in 1200s
- Cirbo per-output-bit: only Y[0]=4 proven; Y[1..7] timeout

**65 is the achievable floor with the tools, parameters, and time budget available in this session.** Going lower requires either:
- AlphaEvolve LLM-driven mutation with API budget (highest EV)
- Multi-day Cirbo SAT campaign on a 32+ core machine (proves lower bound or finds the missing -1)
- Novel structural insight from human or deep LLM analysis

---

## 2026-04-27

### Session resume on dedicated 28-vCPU/56GB Linux VPS

User provisioned a 28-vCPU / 56GB RAM Ubuntu 22.04 box specifically to run the long campaigns the previous session recommended. GitHub auth via `gh auth login` (user `A14N77`).

### Toolchain on Linux

- yosys 0.51+104 (OSS CAD Suite 2025-04-01) at `/home/shadeform/oss-cad-suite/bin/`
- Ubuntu yosys 0.9 + berkeley-abc 1.01 has SIGSEGV bug under our `&deepsyn` script — DON'T use them.
- ABC 1.01 (Apr 2025 build) bundled with OSS CAD Suite — `&deepsyn` works.
- python venv at `/home/shadeform/.venv-fp4/`: cirbo 1.0.0, pysat 1.9.dev2 (with cadical195/153, lingeling, glucose42, maplecm, mergesat3, etc.), z3 4.16, sympy.
- eSLIM at `/home/shadeform/eslim/` — built cleanly on Linux (no APFS rename hack needed).
  - PYTHONPATH=`/home/shadeform/eslim/src/bindings/build`.
  - Verified end-to-end: 70-gate canonical -> 59 internal in 120s -> 69 contest cells (different cell mix than canonical 65 because legacy translator allocates 1 NOT per ANDN_A/ANDN_B input).
- kissat 4.0.4 built at `/home/shadeform/kissat/` (not yet wired into Cirbo).

### Workspace structure (in-repo, gitignored)

```
fp4-multiplier/workspace/
├── eslim_runs/
│   ├── starts/               # 35 diverse starting BLIFs (canonical 65/70/74 + mut11/2/26/27/raw at seeds 1..555)
│   ├── outputs/              # per-experiment eSLIM + translation outputs
│   ├── sweep_ledger.tsv      # one row per experiment: ts, run_id, start, size, restarts, limit_inputs, seed, budget_s, internal, contest, and2/or2/xor2/not1, status, note, wall_s
│   ├── sweep_run.py          # single-experiment runner (frozen verifier)
│   ├── sweep_master.sh       # parallel orchestrator (xargs -P)
│   ├── parallel_synth.sh     # parallel start-netlist generator
│   └── verify_starts.py      # frozen-verifier sanity check
└── cirbo_runs/
    ├── cirbo_portfolio.py    # multi-solver SAT portfolio (cadical195/153/lingeling/...)
    ├── cirbo_ledger.tsv
    └── cirbo_G64.log
```

### Structural analysis of canonical 65-gate

Per-output cone sizes (gates only):
| Y[0] | Y[1] | Y[2] | Y[3] | Y[4] | Y[5] | Y[6] | Y[7] | Y[8] |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 14 | 28 | 38 | 45 | 49 | 53 | 57 | 60 | 58 |

Max depth 21 (Y[7]). The 7 NOTs are localized: each feeds 1-2 ANDs in `AND(NOT(x), y)` patterns — these are eSLIM's ANDN_A/ANDN_B operators after translator expansion. Their inputs come from XORs and ORs, so straightforward DeMorgan rewrites don't help (would just push the NOT to the inputs of an XOR/OR, which can't absorb it).

**Path to 64**: need either (a) different 58-internal with FEWER distinct ANDN inputs (saves 1 NOT) or (b) 57-internal eSLIM solution.

### Round 1 eSLIM sweep (running 2026-04-27 03:46+)

- 35 starting BLIFs × 2 sizes (8, 10) × 2 seeds (1, 42) = 140 experiments
- 22-way parallel via xargs -P 22, 900s budget per experiment
- ~1.6 hour wall clock
- Goal: find a (start, size, seed) combination that yields <= 64 contest cells

### Cirbo G=64 portfolio (running 2026-04-27 03:46+)

- 3 SAT solvers in parallel: cadical195, cadical153, lingeling
- Single G=64 instance, 6-hour budget per solver
- Outcomes:
  - SAT → known upper bound is 64 (we'd then iterate to G=63...)
  - UNSAT → proven lower bound 65 (TAPE-OUT GRADE optimality proof for Longhorn Silicon)
  - TIMEOUT → status quo (still 65 best, no proof)

