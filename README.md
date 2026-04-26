# FP4 Multiplier — 74 Gates

A minimum-gate hardware multiplier for the **MX-FP4 (E2M1)** floating-point format. Takes two 4-bit FP4 numbers, outputs `4·a·b` as a 9-bit two's-complement integer (the "QI9" accumulator format). Built for Etched's take-home challenge — the design and tricks are directly transferable to Longhorn Silicon's tape-out.

## Result

**74 gates** in the contest gate library `{AND2, OR2, XOR2, NOT1}` (each = 1 unit). Verified correct on all 256 input pairs.

| Cell type | Count |
|:---|---:|
| AND2 | 37 |
| OR2  | 18 |
| XOR2 | 11 |
| NOT1 | 8 |
| **Total** | **74** |

5.3× reduction from the naïve PLA→ABC baseline (390 gates). 13.5% reduction from the prior published-style baseline (~85 gates).

## Repo layout

```
.
├── README.md             — this file
├── INSTRUCTIONS.md       — teaching doc: FP4 → multiplier → MAC → matmul → transformer inference
├── PRD.md                — product/research design doc with research grounding and optimality argument
├── SUMMARY.md            — concise "what we accomplished" report
├── MEMORY.md             — chronological research journal (resume-ready for future Claude sessions)
│
├── src/                  — the canonical 74-gate solution
│   ├── fp4_mul.v         — Verilog source (mut11 form: NAND-chain "below" detector + raw P_nonzero)
│   ├── fp4_mul.blif      — synthesized BLIF netlist (74 cells)
│   ├── contest.lib       — Liberty file: AND2/OR2/XOR2/NOT1 area=1 each
│   ├── synth.ys          — yosys synthesis script that produced the BLIF
│   └── README.md         — provenance + reproduction
│
├── lib/                  — Python library (verifier, generators, synth pipelines, search drivers)
│   ├── fp4_spec.py       — FROZEN: ground-truth truth-table generator + spec
│   ├── verify.py         — FROZEN: BLIF parser + 256-pair simulator (the eval harness)
│   ├── remap.py          — sign-symmetric remap enumerator
│   ├── gen_*.py          — Verilog generators per remap (struct / raw / mut2 / mut11)
│   ├── synth_*.py        — synthesis pipelines (PLA / Verilog / structural / remap-aware / mut11)
│   ├── search_*.py       — multi-worker remap sweep drivers
│   ├── cirbo_*.py        — SAT-based exact-synthesis experiments (lower bounds)
│   ├── exact_per_bit.py  — per-output AIG-node analysis
│   ├── sympy_minimize.py — 2-level SOP minimization (sanity check)
│   ├── strategy.py       — Karpathy-autoresearch proposal file (agent-edited)
│   ├── run_mutations.py  — driver to synthesize and verify one or more mutation Verilogs
│   └── contest.lib, abc.rc
│
├── mutations/            — 24 hand-mutated Verilog formulations (mut1..mut24 + struct/hand/bw/etc)
│
├── results/              — experiment ledgers (.tsv, ~7000 rows total across all sweeps)
│
├── docs/                 — extended docs
│   └── program.md        — Karpathy-autoresearch skill spec for the agent loop
│
└── reference/            — the original Etched contest spec
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
cd lib && python3 cirbo_subblocks.py 2x2     # proves 7 gates exact for 2x2 mul
cd lib && python3 cirbo_subblocks.py k       # K computation
cd lib && python3 cirbo_subblocks.py shift   # K-shift
```

## How we got here (trajectory)

| Stage | Gates | Win |
|---|---:|---|
| PLA → ABC FAST (flat truth table) | 390 | — |
| Behavioral case-stmt Verilog → yosys+ABC | 222 | yosys structural elaboration |
| Structural Verilog (sign-magnitude split) + deepsyn | 86 | explicit decomposition exposed to ABC |
| + best input remap σ = (0,1,2,3,6,7,4,5) | 85 | XOR-decoded `el = a[1]^a[2]` |
| + raw-bit `lb = a[1]\|a[2]` collapse | 81 | algebraic identity `a\|(a^b)=a\|b` |
| + mut2 NAND-chain "below" conditional negate | 75 | replaces +1 carry chain |
| + mut11 raw P_nonzero direct-route for Y[8] | **74** | bypasses long below-chain for sign output |

## Optimality argument (in brief)

- **Provable lower bounds (Cirbo SAT):** 2×2 unsigned mul = 7 gates exact (G=6 UNSAT, G=7 SAT). K computation ≥ 8 (G=7 UNSAT). K-shift ≥ 13 (G=12 UNSAT).
- **deepsyn fixed-point:** re-feeding the 74-gate BLIF through ABC's full pipeline returns 74. Saturated for our toolchain.
- **Coverage:** 5040+2000+1000 sign-symmetric remap sweeps × 24 hand-mutated Verilog forms × 9+ ABC scripts × eSLIM SAT-local-improvement (gave 100, worse) × mockturtle XAG resynthesis (gave 78, worse) — none of these break 74.
- **Y[0] minimum proven = 4 gates** (`(m_a AND m_b) AND NOT(eh_a OR eh_b)`) by Cirbo SAT.

## Context

Read `INSTRUCTIONS.md` for the full teaching-style explanation: what FP4 is, how the multiplier slots into a MAC, how MACs tile into matmul, how matmuls become transformer attention/FFN, and why ASIC-grade gate counts matter.

Read `PRD.md` for the design doc with research grounding (28+ citations).

Read `MEMORY.md` for the chronological research journal — fully resume-ready across Claude sessions.

## License

To be determined by the org.

## Acknowledgments

Built for Longhorn Silicon. Methodology: Karpathy-autoresearch loop, AlphaEvolve-style mutation/verify cycle, Cirbo SAT-based exact synthesis. References cited inline throughout `PRD.md` and `MEMORY.md`.
