# FP4 Multiplier — 65 Gates (with active 28-vCPU campaign to push lower)

A minimum-gate hardware multiplier for the **MX-FP4 (E2M1)** floating-point format. Takes two 4-bit FP4 numbers, outputs `4·a·b` as a 9-bit two's-complement integer (the "QI9" accumulator format). Built for Etched's take-home challenge — the design and tricks are directly transferable to Longhorn Silicon's tape-out.

## Result

**65 gates** in the contest gate library `{AND2, OR2, XOR2, NOT1}` (each = 1 unit). Verified correct on all 256 input pairs.

| Cell type | Count |
|:---|---:|
| AND2 | 25 |
| OR2 | 12 |
| XOR2 | 21 |
| NOT1 | 7 |
| **Total** | **65** |

**6.0x reduction from the naive PLA->ABC baseline (390 gates).** **23.5% reduction from the prior published-style baseline (~85 gates).** Last 9 gates came from eSLIM SAT-based local improvement applied on top of the 74-gate ABC-deepsyn output (74 -> 70 with default size; 70 -> 65 with `--size 8` windows on a re-application).

## Active campaign (2026-04-27, dedicated 28-vCPU VPS)

Per the prior session's tier-1/2 recommendations, two campaigns are running on a 28-vCPU / 56GB Ubuntu VPS:

1. **Massive eSLIM SAT sweep** — 35+ diverse starting BLIFs (mut11/2/26/27/30..34 across deepsyn seeds 1..555 + canonical 65/70/74) × 4 window sizes × multiple seeds = ~140-360 experiments. Each verifies under the frozen σ=(0,1,2,3,6,7,4,5) harness; all parameters logged to `workspace/eslim_runs/sweep_ledger.tsv`. Goal: find a 58-internal eSLIM solution with ≤6 distinct ANDN inputs (would yield ≤64 contest cells), or a 57-internal solution.
2. **Cirbo per-output-bit SAT lower bounds** — 8 parallel SAT searches (one per output bit Y[1..8]) using cadical 1.9.5, walking G upward to find proven minimums. Y[0]=4 is already proven (prior session). Tightening the per-bit lower bounds gives a defensible "≥ X" floor for tape-out review even if no cell improvement is found.
3. **AlphaEvolve-style mutation generation** — 5 new structurally distinct decompositions (mut30..34) added to the experiment grid: above-detector OR-ladder (mut30), one-hot K + SOP magnitude (mut31), Sklansky parallel-prefix below detector (mut32), Booth-2 B-operand recoding (mut33), Shannon-on-sy with shared above-ladder (mut34). All elaborate cleanly; eSLIM compresses each as one of the round-1 starts.

The previous session exhausted the parameter space available on a single workstation in a fixed time budget. This campaign uses the dedicated VPS (28-vCPU/56GB) the previous session explicitly requested. Round 1 of the eSLIM sweep is running as of 2026-04-27 03:46 UTC; expected wall time ~1.6 hours. See `MEMORY.md` for the full campaign log.

## Repo layout

```
.
├── README.md — this file
├── INSTRUCTIONS.md — teaching doc: FP4 → multiplier → MAC → matmul → transformer inference
├── PRD.md — product/research design doc with research grounding and optimality argument
├── SUMMARY.md — concise "what we accomplished" report
├── MEMORY.md — chronological research journal (resume-ready for future Claude sessions)
│
├── src/ — the canonical 70-gate solution
│ ├── fp4_mul.v — Verilog source (mut11 form: NAND-chain "below" detector + raw P_nonzero)
│ ├── fp4_mul.blif — final 70-gate BLIF (post eSLIM)
│ ├── contest.lib — Liberty file: AND2/OR2/XOR2/NOT1 area=1 each
│ ├── synth.ys — yosys synthesis script (produces the 74-gate BLIF; eSLIM takes it from there)
│ └── README.md — provenance + reproduction
│
├── lib/ — Python library (verifier, generators, synth pipelines, search drivers)
│ ├── fp4_spec.py — FROZEN: ground-truth truth-table generator + spec
│ ├── verify.py — FROZEN: BLIF parser + 256-pair simulator (the eval harness)
│ ├── remap.py — sign-symmetric remap enumerator
│ ├── gen_*.py — Verilog generators per remap (struct / raw / mut2 / mut11)
│ ├── synth_*.py — synthesis pipelines (PLA / Verilog / structural / remap-aware / mut11)
│ ├── search_*.py — multi-worker remap sweep drivers
│ ├── cirbo_*.py — SAT-based exact-synthesis experiments (lower bounds)
│ ├── exact_per_bit.py — per-output AIG-node analysis
│ ├── sympy_minimize.py — 2-level SOP minimization (sanity check)
│ ├── strategy.py — Karpathy-autoresearch proposal file (agent-edited)
│ ├── run_mutations.py — driver to synthesize and verify one or more mutation Verilogs
│ └── contest.lib, abc.rc
│
├── mutations/ — 24 hand-mutated Verilog formulations (mut1..mut24 + struct/hand/bw/etc)
│
├── results/ — experiment ledgers (.tsv, ~7000 rows total across all sweeps)
│
├── docs/ — extended docs
│ └── program.md — Karpathy-autoresearch skill spec for the agent loop
│
└── reference/ — the original Etched contest spec
```

## Quick start

```bash
# Re-synthesize the 74-gate canonical from Verilog source
cd lib && python3 run_mutations.py ../mutations/fp4_mul_mut11.v

# Verify the saved BLIF on all 256 inputs
cd lib && python3 -c "
from verify import verify_blif
from remap import encoding_from_magnitude_perm
v = encoding_from_magnitude_perm((0,1,2,3,6,7,4,5))
ok, _ = verify_blif('../src/fp4_mul.blif', values=v)
print('verify:', 'OK' if ok else 'FAIL')
"

# Wide remap sweep with the mut11 form (5040 sign-symmetric perms)
cd lib && python3 search_mut11.py --n 5040 --top-k 50 --workers 4

# SAT-based exact synthesis on small sub-blocks (proves lower bounds)
cd lib && python3 cirbo_subblocks.py 2x2 # proves 7 gates exact for 2x2 mul
cd lib && python3 cirbo_subblocks.py k # K computation
cd lib && python3 cirbo_subblocks.py shift # K-shift
```

## How we got here (trajectory)

| Stage | Gates | Win |
|---|---:|---|
| PLA -> ABC FAST (flat truth table) | 390 | - |
| Behavioral case-stmt Verilog -> yosys+ABC | 222 | yosys structural elaboration |
| Structural Verilog (sign-magnitude split) + deepsyn | 86 | explicit decomposition exposed to ABC |
| + best input remap sigma = (0,1,2,3,6,7,4,5) | 85 | XOR-decoded `el = a[1]^a[2]` |
| + raw-bit `lb = a[1]\|a[2]` collapse | 81 | algebraic identity `a\|(a^b)=a\|b` |
| + mut2 NAND-chain "below" conditional negate | 75 | replaces +1 carry chain |
| + mut11 raw P_nonzero direct-route for Y[8] | 74 | bypasses long below-chain for sign output |
| + eSLIM SAT-based windowed local improvement (`--syn-mode sat`) | 70 | SAT-proven minimal sub-circuit replacements; XOR-aware |
| + **eSLIM SAT `--size 8` windows on the 70-gate result** | **65** | larger SAT window finds non-local replacements ABC's heuristics miss |

## Optimality argument (in brief)

- **Provable lower bounds (Cirbo SAT):** 2×2 unsigned mul = 7 gates exact (G=6 UNSAT, G=7 SAT). K computation ≥ 8 (G=7 UNSAT). K-shift ≥ 13 (G=12 UNSAT). Sum of provable sub-block lower bounds + sign + negate ≈ 36+ gates.
- **deepsyn fixed-point at 74:** re-feeding the 74-gate BLIF through ABC's full pipeline returns 74 deterministically. Saturated for ABC's heuristic optimizer.
- **eSLIM broke 74 via SAT-proven windowed replacements** (with `--syn-mode sat` to preserve XOR2 in the basis). Reached 70 in 240 sec on the 74-gate input.
- **Y[0] minimum proven = 4 gates** (`(m_a AND m_b) AND NOT(eh_a OR eh_b)`) by Cirbo SAT.

## Context

Read `INSTRUCTIONS.md` for the full teaching-style explanation: what FP4 is, how the multiplier slots into a MAC, how MACs tile into matmul, how matmuls become transformer attention/FFN, and why ASIC-grade gate counts matter.

Read `PRD.md` for the design doc with research grounding (28+ citations).

Read `MEMORY.md` for the chronological research journal — fully resume-ready across Claude sessions.

## License

To be determined by the org.

## Acknowledgments

Built for Longhorn Silicon. Methodology: Karpathy-autoresearch loop, AlphaEvolve-style mutation/verify cycle, Cirbo SAT-based exact synthesis. References cited inline throughout `PRD.md` and `MEMORY.md`.
