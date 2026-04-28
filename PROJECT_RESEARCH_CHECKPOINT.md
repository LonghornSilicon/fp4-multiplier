# FP4×FP4 → QI9 Multiplier — Research Checkpoint (2026-04-28)

This file is a **durable, in-repo memory** of what has been tried so far, what worked, what didn’t, and what (if anything) is still worth exploring. It’s written so a future session/model can resume without needing chat history.

## Current best solution

- **Best known correct circuit**: **82 gates**, verified by:
  - `python3 eval_circuit.py autoresearch/multiplier.py` → `Result: CORRECT`, `Gates: 82`
- **Core architecture** (from `RESEARCH_NOTES.md`):
  - Free input remapping used to choose a magnitude encoding where:
    - exponent \(E'\) is directly encoded by two bits
    - mantissa-type \(M\) is a single bit
  - Multiply magnitudes by:
    - compute sign (XOR)
    - non-zero detect
    - compute exponent sum \(S\) (2-bit adder)
    - compute K-type flags (3-way case on mantissa bits)
    - decode \(S\) to one-hot (SAT-optimized 11-gate decoder)
    - assemble sparse magnitude (≤2 bits set)
    - conditional two’s complement negation (prefix-OR optimized)

## “Ceiling” observation

Everything attempted so far (ABC, Cirbo exact synthesis on sub-blocks, SOP/ESOP style minimization, encoding sweeps, structural resynthesis) has **not** beaten 82. Multiple tools suggest 82 is at least **locally optimal** under the current decomposition.

The emerging hypothesis is:
- **Sub-75** likely requires a **fundamentally different decomposition/topology**, not incremental optimization of the current K×shift design.

## Directions explored (and results)

### 1) Log-domain approach

- **Status**: **Not promising**.
- **Reason**: The current circuit already *is* the log-domain factorization:
  - \( \log_2(|x|) = E + M \log_2(1.5) \)
  - current design computes \(E\)-sum and \(M\)-sum (K-type), then “antilog-decodes” via shift decode + sparse assembly.
  - explicit fixed-point log encoding adds encoder/decoder overhead.
- **Artifact**: `experiments/exp_log_domain.py`

### 2) ROM-style / lookup decomposition (6-in → 8-out magnitude)

- **Status**: **Not promising** relative to the structured 54–57 gate magnitude path.
- **Reason**: Flat ROM/PLA synthesis ignores the exploitable K-type × shift structure; ABC AIG results don’t translate into fewer {AND,OR,XOR,NOT} gates.
- **Artifacts**:
  - `experiments/exp_rom_decomposition.py`
  - `experiments/exp_rom_abc_deep.py`

### 3) Joint E-sum + S-decoder synthesis

- **Status**: **Open / marginal** (at best ~1 gate).
- **What it is**: Instead of 7-gate adder + 11-gate decoder = 18 gates, attempt a jointly optimized 4-in → 7-out block.
- **Artifact**: `experiments/exp_esum_decoder_joint.py`
- **Expectation**: even if successful, this is **small** (0–1 gate) and unlikely to unlock sub-75 alone.

### 4) BDD-based synthesis

- **Status**: **Unclear** (analysis tooling exists; not yet shown to produce a smaller circuit in our gate basis).
- **Artifact**: `experiments/exp_bdd_synth.py`
- **Notes**:
  - BDD node counts can suggest sharing opportunities, but node count ≠ gate count in our {AND,OR,XOR,NOT} cost model.
  - Past results for flat SOP/AIG approaches were worse than structural decomposition.

### 5) Evolutionary / stochastic circuit search

- **Status**: **Implemented, but no breakthrough recorded**.
- **Artifact**: `evolutionary_search.py`
- **Notes**:
  - Search space is enormous; naive mutation tends to break correctness.
  - Script includes a seeded start from known structure and local/SA/evolutionary phases.

## “Still genuinely untried” (as of this checkpoint)

These are the only directions that might plausibly beat 82, but **none are proven promising yet**:

1. **Radically different topology** (not “K×shift + decode + sparse-assemble + conditional negate”).
2. **Encoding rethink beyond the current sign/magnitude split**:
   - sign not necessarily a dedicated bit
   - non-power-of-2 encodings that make the *Boolean* mapping simpler (even if the arithmetic interpretation is weird)
3. **Stronger global synthesis over the full 8→9 function** in {AND,OR,XOR,NOT} with multi-output sharing:
   - not per-bit SOP
   - not AIG-only cost proxies
   - must respect XOR as 1 gate (most AIG tools heavily penalize XOR)

## Practical environment notes (WSL)

- In WSL, `eval_circuit.py` runs fine.
- `verify_submission.py` needs `ml_dtypes`. If pip is blocked by PEP 668, one workaround used was:
  - `python3 -m pip install --break-system-packages ml-dtypes==0.5.1`

## Where the “source of truth” lives

- **High-level reasoning + final 82-gate accounting**: `RESEARCH_NOTES.md`
- **Reference circuit used by evaluator**: `autoresearch/multiplier.py`
- **Experiment scripts**: `experiments/`
- **Search / synthesis tooling**: `evolutionary_search.py`, `bdd_synthesis*.py`

