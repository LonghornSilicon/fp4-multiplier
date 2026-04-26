# SUMMARY — FP4 Multiplier Challenge: Everything Accomplished

**Project:** Etched Take-Home Multiplier Assignment (FP4 × FP4 → 9-bit QI9)
**Owner:** Alan Schwartz (Longhorn Silicon)
**Stakes:** Real — informs Alan's chip tape-out, not academic
**Date(s):** 2026-04-25 (intensive session, multiple pushes)
**Companion files:** `PRD.md` (full design doc), `MEMORY.md` (chronological journal), `current_best/` (canonical answer), `code/` (all infrastructure)

---

## The result

**74 gates**, verified correct on all 256 input pairs.

| | |
|---|---|
| **Total gate count** | **74** |
| AND2 | 37 |
| NOT1 | 8 |
| OR2  | 18 |
| XOR2 | 11 |
| Verified | ✅ all 256/256 input pairs |
| Synthesis flow | yosys 0.64 → ABC `&deepsyn -T 3 -I 4` |
| Wall time to synthesize | ~13 sec (M-series, single thread) |
| Saved to | `current_best/fp4_mul.{v,blif,README.md}` |

### Trajectory (this session)

| Stage | Gates | Win |
|---|---:|---|
| PLA + ABC FAST | 390 | — |
| Behavioral Verilog (case-stmt) | 222 | yosys structural elaboration |
| Structural Verilog + deepsyn | 86 | explicit sign-mag split |
| + best remap σ | 85 | XOR-decoded `el = a[1]^a[2]` shrinks decoder |
| + raw-bit `lb = a[1]\|a[2]` collapse | 81 | algebraic identity `a\|(a^b)=a\|b` |
| + mut2 NAND-chain "below" detector | 75 | replaces +1 carry chain |
| + mut11 raw P_nonzero for Y[8] | **74** | bypasses long below-chain for sign output |

**5.3× reduction from naive PLA baseline.** **13.5% reduction** over the prior 85-gate result.

### Winning input remap
σ = (0,1,2,3,6,7,4,5) on magnitudes; sign-MSB preserved. Codepoint table:

| 4-bit code | value | | 4-bit code | value |
|:---:|:---:|---|:---:|:---:|
| 0000 | +0   | | 1000 | -0   |
| 0001 | +0.5 | | 1001 | -0.5 |
| 0010 | +1   | | 1010 | -1   |
| 0011 | +1.5 | | 1011 | -1.5 |
| 0100 | +4   | | 1100 | -4   |
| 0101 | +6   | | 1101 | -6   |
| 0110 | +2   | | 1110 | -2   |
| 0111 | +3   | | 1111 | -3   |

The remap collapses, in the structural multiplier, to a single-XOR decode trick: `dec_el = a[1] XOR a[2]` (other bits passthrough). Four distinct sign-symmetric remaps tied at 85.

---

## What was accomplished, in order

### 1. Spec digestion + integrity check
- Identified **two typos in spec example 2**: ("−3 represented in FP4 binary as 0001" — should be 1101; "output 110111000" should be 111101110 for 4·(−3·1.5)=−18)
- Locked canonical interpretation via the **only-fits-in-9-bits** argument: `output_int = 4·val_a·val_b`, max |144| (the alt reading max=576 overflows 9 bits)
- Encoded canonical truth table in `code/fp4_spec.py`

### 2. Literature survey (lit-review agent, 28+ citations)
Key references (full list in `PRD.md` §3, also URLs throughout `MEMORY.md`):
- **MX FP4 / E2M1 spec:** [OCP MX v1.0](https://www.opencompute.org/documents/ocp-microscaling-formats-mx-v1-0-spec-final-pdf), [arXiv 2310.10537](https://arxiv.org/abs/2310.10537)
- **Sign-magnitude internal encoding:** [arXiv 2507.18179](https://arxiv.org/abs/2507.18179) — ~50% transistor reduction at 4-bit (confirmed empirically in our work)
- **SAT-based exact synthesis:** [Cirbo IWLS 2024 winner](https://arxiv.org/abs/2412.14933), [eSLIM SAT 2024](https://drops.dagstuhl.de/entities/document/10.4230/LIPIcs.SAT.2024.23), [Soeken DATE 2018](https://msoeken.github.io/papers/2018_date_2.pdf), [TCAD 2020](https://people.eecs.berkeley.edu/~alanmi/publications/2020/tcad20_exact.pdf)
- **Knuth on Boolean complexity:** TAOCP Vol 4 §7.1.2 (NPN-class minimums for ≤5-input)
- **AI for circuit synthesis:** [AlphaEvolve (DeepMind 2025)](https://deepmind.google/blog/alphaevolve-a-gemini-powered-coding-agent-for-designing-advanced-algorithms/), [AlphaTensor](https://www.nature.com/articles/s41586-022-05172-4), [AlphaDev](https://www.nature.com/articles/s41586-023-06004-9), [Circuit Transformer](https://github.com/snowkylin/circuit-transformer), [VeriGen](https://dl.acm.org/doi/10.1145/3643681)
- **Recent FP4 hardware:** [Wonjun-Han DotProduct_FP4](https://github.com/Wonjun-Han/DotProduct_FP4), [AxCore (MICRO 2025)](https://soldierchen.github.io/assets/pdf/axcore-micro25.pdf), [MX+ (MICRO 2025)](https://yong2355.github.io/assets/pdf/micro25-mxplus.pdf), [Kida-Sato 4-bit (arXiv 2510.21533)](https://arxiv.org/abs/2510.21533), NVIDIA Blackwell NVFP4

### 3. Karpathy autoresearch — confirmed and operationalized
- Verified [karpathy/autoresearch](https://github.com/karpathy/autoresearch) is real (released 2026-03-06, 76.5k stars). Methodology: single scalar metric, fixed wall-clock per experiment, frozen evaluation harness, agent edits exactly one file, git/TSV ledger, "MODIFY → VERIFY → KEEP/DISCARD → REPEAT FOREVER"
- Encoded the methodology as `code/program.md` (the human-edited skill spec) + `code/strategy.py` (the agent-edited proposal file) + `code/search.py` (the driver) + `results.tsv` (the ledger). Loop is ready to run on demand.

### 4. Truth-table enumerator + frozen verifier (`code/fp4_spec.py`, `code/verify.py`)
- 256-input × 9-output truth table generator
- BLIF parser supporting both `.gate` (ABC) and `.subckt` (yosys) syntax, both `a3` and `a[3]` naming conventions, dead-logic tolerance (yosys leaves orphan BUFs)
- `verify_blif(blif, values)` returns (ok, mismatches) — used as the **frozen evaluation harness** per Karpathy autoresearch convention

### 5. Synthesis pipelines (multiple input formats explored)

| Input format | Best gate count | Notes |
|---|---:|---|
| PLA (256-minterm SOP) | 390 | flat truth-table → ABC; SOP form is bad starting AIG |
| Behavioral case-stmt Verilog (`fp4_mul.v`) | 222 | yosys lifts case → memory; ABC techmaps |
| **Structural Verilog (sign-magnitude split)** | **86** (default) / **85** (best remap) | sign-XOR + 2×2 mantissa mul + K-shift + conditional negate |
| Hand-explicit-shift Verilog (`fp4_mul_hand.v`) | 88 | each mag bit as OR of (P[j] AND isK[i-j]) |
| Hand-Baugh-Wooley-folded Verilog (`fp4_mul_bw.v`) | 88 | rigid hand structure; deepsyn rearranges to worse |
| Hierarchical Verilog (submodule + flatten) | 89 | flat is slightly better |

**Lesson:** give synthesis the right *level* of structure (sign/mag split, 2×2 mul) but don't over-constrain low-level patterns — ABC's optimizer already finds the equivalent BW fold from the simpler structural form.

### 6. Search infrastructure (Karpathy-autoresearch loop)
- `code/synth.py` — PLA → ABC pipeline (legacy, brittle)
- `code/synth_v.py` — Verilog → yosys → ABC
- `code/synth_struct.py` — variant-script comparator
- `code/synth_remap.py` — per-remap structural Verilog + decoder
- `code/gen_struct.py` — emit structural Verilog with simple decoder for arbitrary remap
- `code/search_remap.py` — parallel sweep driver with two-stage (FAST + deepsyn) refinement
- `code/strategy.py`, `code/program.md`, `code/search.py` — Karpathy autoresearch skeleton

### 7. Wide remap search (5040 sign-symmetric perms)
- All 5040 sign-symmetric remaps with mag-0 fixed at code 0
- 4-worker parallel FAST pass + deepsyn-3s on top 30
- **Best: 85 gates, 4 distinct perms tie**:
  - `(0,1,2,3,6,7,4,5)` ← canonical (saved)
  - `(0,1,6,7,2,3,4,5)`
  - `(0,2,1,3,6,4,7,5)`
  - `(0,2,6,4,1,3,7,5)`
- Random non-sign-symmetric (50 sampled): all ≥ 140 gates → sign-symmetric is strictly preferred (matches the lit prediction)

### 8. AlphaEvolve-style hand mutations (`code/fp4_alphaevolve.py`)
- 6 alternate Verilog formulations: standard struct, explicit isK indicators, signed-2x multiply, K as OR-sum, muxed shift, signed-2x with explicit XOR negate
- Best = struct/muxed-shift at 86 (default encoding)
- Two signed-multiplier variants exploded (211, 225 gates) — confirms sign-magnitude internal path is correct

### 9. Per-output-bit AIG node counts (`code/exact_per_bit.py`)
ABC `&deepsyn -T 5` on each output independently (no sharing):

| Y[0] | Y[1] | Y[2] | Y[3] | Y[4] | Y[5] | Y[6] | Y[7] | Y[8] | sum |
|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| 3 | 22 | 35 | 44 | 33 | 32 | 23 | 17 | 9 | **218** |

Our 85-gate full circuit shares ~60% of the per-bit cost. Healthy.

### 10. Cirbo SAT-based exact synthesis (`code/cirbo_search.py`, `cirbo_per_bit.py`, `cirbo_full.py`, `cirbo_lb.py`, `cirbo_magnitude.py`)
- Installed [cirbo 1.0.0](https://github.com/SPbSAT/cirbo)
- **Y[0] minimum proven = 4 gates** (basis {AND, OR, XOR, NOT}, 1.6 sec):
  ```
  Y[0] = (m_a AND m_b) AND NOT(eh_a OR eh_b)
  ```
- Multi-output Cirbo SAT at G=84: TIMEOUT (5+ min, 2 GB memory)
- G=10 lower-bound probe: TIMEOUT at 70s (the 9-output × 256-minterm SAT instance is too big for our budget)
- **Conclusion:** rigorous SAT-based proof of optimality below 85 needs days-to-weeks of compute, not hours.

### 11. ABC `&deepsyn` saturation analysis
- Tested at T = 1, 2, 3, 5, 10, 30, 60s on the best remap
- All return 85 (or worse). Increasing time budget does NOT improve.
- Combined with `compress2`, `resyn3`, `mfs2 -L 200`, `if -K 6 -a` variants returning ≥ 85: **85 is a robust local optimum for ABC's reachable structures.**

### 12. Optimality argument (PRD §6)
- **Provable per-output minimum:** Y[0] = 4 gates (Cirbo SAT, our basis)
- **Multi-output SAT proof:** infeasible on workstation budget
- **Search saturation:** 5040 remaps × 9 ABC scripts × 6 Verilog forms × 50 random bijections — no path under 85
- **Per-bit AIG sum (no sharing) = 218** → 85-gate solution shares ~60%, healthy
- **Information-theoretic floor** (73 distinct outputs, ≥ 7 bits) — doesn't bound gate count usefully

---

## Quantitative trajectory

| Stage | Gates | Method |
|---|---:|---|
| PLA + ABC FAST | 390 | flat truth-table SOP — bad start |
| Behavioral Verilog + ABC | 222 | case-stmt → memory → flatten → ABC |
| Structural Verilog (default encoding) + FAST | 93 | sign-mag split lifted into Verilog |
| Structural Verilog + ABC `&deepsyn -T 3` | 86 | best for default encoding |
| **Structural Verilog + best remap + `&deepsyn -T 3`** | **85** | sign-symmetric remap σ=(0,1,2,3,6,7,4,5) |

**4.6× reduction from naïve PLA baseline.** **2.6× reduction from behavioral Verilog.** **8% reduction from default-encoding structural** via input remap alone.

---

## Files persisted (for resume across Claude sessions)

```
/Users/alanschwartz/Downloads/Projects/FP4 Mul/
├── PRD.md                                  # full design doc (research + decomposition + optimality)
├── MEMORY.md                               # chronological journal (~12 KB)
├── SUMMARY.md                              # this file
├── results.tsv                             # PLA-pipeline experiment ledger (~250 rows)
├── results_remap.tsv                       # remap-aware ledger (~5070 rows)
├── current_best/                           # canonical 85-gate answer
│   ├── fp4_mul.v                           #   structural Verilog with 1-XOR remap decoder
│   ├── fp4_mul.blif                        #   85 .subckt lines
│   ├── contest.lib                         #   AND2/OR2/XOR2/NOT1 area=1 each
│   ├── synth.ys                            #   yosys script that produced it
│   └── README.md                           #   provenance + reproduce instructions
├── code/
│   ├── fp4_spec.py                         # truth-table source of truth + spec-typo fix
│   ├── verify.py                           # FROZEN evaluation harness (BLIF simulator)
│   ├── remap.py                            # sign-symmetric perm enumerator
│   ├── gen_struct.py                       # emit structural Verilog for any remap
│   ├── synth.py / synth_v.py / synth_remap.py / synth_struct.py
│   │                                       # 4 synthesis pipelines (PLA / Verilog / remap-aware / variant comparator)
│   ├── search.py / search_remap.py         # autoresearch search drivers (parallel)
│   ├── strategy.py / program.md            # Karpathy autoresearch skeleton (agent-editable + skill spec)
│   ├── exact_per_bit.py                    # per-output-bit AIG analysis
│   ├── fp4_alphaevolve.py                  # hand-mutated Verilog candidate comparison
│   ├── cirbo_search.py / cirbo_per_bit.py / cirbo_full.py / cirbo_magnitude.py / cirbo_lb.py
│   │                                       # SAT-based exact synthesis (Y[0] proven optimal)
│   ├── fp4_mul.v                           # behavioural reference (case-stmt)
│   ├── fp4_mul_struct.v                    # structural sign-mag (the 86-gate basis for default)
│   ├── fp4_mul_hand.v                      # explicit-shift hand variant
│   ├── fp4_mul_bw.v                        # explicit Baugh-Wooley fold
│   ├── fp4_mul_hier.v                      # hierarchical (submodule)
│   ├── contest.lib                         # 4-cell unit-area Liberty
│   └── abc.rc                              # ABC alias definitions (resyn2 etc)
└── synth_artifacts/, synth_artifacts_v/    # per-experiment BLIFs (~200 files, can prune)
```

---

## What's left (next-tier escalations, ranked by expected value)

### Tier 1 — Most likely to unlock sub-85 (high variance, high upside)
**AlphaEvolve-style verifier-in-the-loop with frontier coder model.**
- Per [DeepMind 2025](https://deepmind.google/blog/alphaevolve-a-gemini-powered-coding-agent-for-designing-advanced-algorithms/), this approach rewrote a Google TPU matrix-multiply circuit. The mechanism: LLM proposes a Verilog/AIG mutation; verifier checks; ABC synthesizes; keep on improvement. Loop runs thousands of times overnight.
- **Why this likely works here:** ABC's `&deepsyn` has a local optimum at 85; my hand-mutations didn't break it; SAT-exact is too slow. LLMs are *specifically* good at proposing creative restructurings that synthesizers don't see.
- **Required:** Anthropic API budget (Opus 4.x, ~$300–1500 for an overnight run of 1000–3000 iterations). OR an open-source coder model on a GPU (DeepSeek-Coder-V3 / Qwen2.5-Coder-32B / Codestral) for ~$5–10/hr cloud × 24 h.
- **Time to first result:** ~30 min after API key.

### Tier 2 — SAT-based local improvement (medium variance, medium upside)
**eSLIM** ([SAT 2024](https://drops.dagstuhl.de/entities/document/10.4230/LIPIcs.SAT.2024.23)) post-pass on the 85-gate AIG.
- Lit-claims 12% avg gate reduction beyond ABC `&deepsyn` via SAT-based windowed local improvement.
- **Required:** install eSLIM (research code), CPU.
- **Time:** ~30 min build + several hours running.

### Tier 3 — Rigorous lower-bound proof (low variance, defensive value)
**Multi-day Cirbo SAT campaign** on a 32–64-core CPU box.
- Run G=83, 82, 81, 80 in parallel cores. Each is a long single-thread SAT instance.
- Likely outcome: confirms 85 (good for tape-out justification) or finds 80–84.
- **Required:** 32+ core box for ~1 week.

### Tier 4 — Toolchain expansion (variance unknown, exploratory)
- **mockturtle** `exact_synthesis` (different SAT encoding than Cirbo)
- **ABC's `&exact`** with custom cost functions
- **Multi-output Boolean relation synthesis** (Soeken et al.)

---

## Compute ask — explicit

If you can give me **one** thing, in priority order:
1. **Anthropic API key + $500–1000 of Opus 4.x token budget** — most likely to unlock sub-85 via AlphaEvolve-style mutation search. The autoresearch infrastructure is already built; we'd be running within 30 min.
2. **32-core CPU box for 3–7 days** — rigorous Cirbo SAT proof of (or break of) 85-gate optimality.
3. **GPU box** — only useful if option #1 isn't available; we'd self-host an open coder model. ~$5–10/hr cloud × 24 h.

If you can give me **two**, the combination of #1 (creative search) + #2 (rigorous proof) is the strongest. They're complementary: the API loop tries to *break* 85, the SAT cluster tries to *prove* whatever lower bound emerges.

GPU specifically (without LLM inference) is **NOT useful** here — the dominant tools (ABC, Cirbo, mockturtle, eSLIM) are CPU-only symbolic solvers.

---

## What this means for Longhorn Silicon

- 85 gates per FP4 multiplier × N multipliers per chip × N chips per fab run is a real silicon win. The structure (sign-magnitude internal, 1-XOR remap decoder, 2×2 mantissa mul, variable shift, conditional negate) is **hardware-clean and ready for tape-out**.
- The XOR-decode trick (`dec_el = a[1] XOR a[2]`) is a free **input-side rewiring** — costs nothing at the input pad, saves one gate in the critical multiplier path. Trivial to implement at RTL.
- The sign-symmetric remap can be applied identically to MAC accumulators: same trick reduces gates in the magnitude-product portion of the multiply-add as well.
- For a multi-cycle pipelined design, the 85-gate combinational logic translates to a small number of pipeline stages; the critical path is dominated by the K-shift mux (≈ log₂(5) = 3 levels of 2-input gates).

---

*Generated 2026-04-25. Resume context across Claude sessions: read this file + `MEMORY.md` top-to-bottom before continuing work.*
