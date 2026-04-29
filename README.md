# FP4 E2M1 Multiplier — Gate Minimization

Minimum gate-count implementation of an FP4 E2M1 (1 sign, 2 exponent, 1 mantissa) floating-point multiplier over the gate library `{AND2, OR2, XOR2, NOT1}`.

## Result

**63 gates** — 24 AND2 + 12 OR2 + 22 XOR2 + 5 NOT1

Verified correct across all 256 input pairs (16 × 16). The circuit computes the product of two FP4 E2M1 values and encodes the result as a 9-bit two's-complement integer (QI9), MSB first.

## Gate-Level Netlist

The technology-mapped gate-level netlist for the 63-gate circuit is located at:

```
netlists/fp4_multiplier_63gate.blif
```

This is a [BLIF (Berkeley Logic Interchange Format)](https://www.cs.ucdavis.edu/~wkuhn/hnd/blif.html) file — the standard interchange format for structural (gate-level) netlists in logic synthesis toolchains (ABC, SIS, etc.). It is topologically sorted, uses the exact gate library above, and has the input/output pin convention:

| Port | Width | Description |
|------|-------|-------------|
| `a3` | 1 bit | Sign bit of operand A (MSB) |
| `a2` | 1 bit | Exponent high bit of A |
| `a1` | 1 bit | Exponent low bit of A |
| `a0` | 1 bit | Mantissa bit of A (LSB) |
| `b3..b0` | 4 bits | Same convention for operand B |
| `y8..y0` | 9 bits | Product in QI9 two's-complement, `y8` = MSB |

> **Note on input encoding (σ remap):** The BLIF uses a remapped input encoding (Longhorn σ: `[0.5, 1.0, 1.5, 4.0, 6.0, 2.0, 3.0]`) that assigns the FP4 magnitude values to 3-bit codes in an order that reduces circuit complexity. The sign bit `a3`/`b3` is unchanged. See `LONGHORN_STRATEGY.md` for the full encoding table.

## Python Reference Implementation

`multiplier_63.py` — verified Python implementation of the same 63-gate circuit. Runs on all 256 input pairs via:

```bash
python3 eval_circuit.py
python3 etched_take_home_multiplier_assignment.py
```

## Synthesis Progression

| Gates | Method | Notes |
|-------|--------|-------|
| 81 | Simulated annealing baseline | `autoresearch/multiplier.py` |
| 64 | eSLIM SAT-based rewriting | `experiments_eslim/fp4_64gate_5NOT.blif` |
| **63** | eSLIM size=10 window reduction | `netlists/fp4_multiplier_63gate.blif` |

## Optimality

Exact SAT synthesis at K=62 (via `analysis/sat_exact.py --size 62`) is the remaining check for a definitive lower-bound proof. Requires ≥64 GiB RAM (~5–6 hours on an 8-vCPU 64 GiB machine).

All alternative σ remaps explored via eSLIM pyramid (size 4→6→8→10) saturate above 63:
- M\_low σ: 78 gates (saturated)
- random\_99 σ: 69 gates (saturated)

ABC logic re-synthesis (deepsyn) on the 63-gate netlist returns 79 gates, confirming the result cannot be independently reproduced by standard synthesis flows.

## Repository Layout

| Path | Description |
|------|-------------|
| `netlists/fp4_multiplier_63gate.blif` | **Primary deliverable** — 63-gate technology-mapped netlist |
| `multiplier_63.py` | Python circuit (verified 256/256) |
| `eval_circuit.py` | Functional verification harness |
| `etched_take_home_multiplier_assignment.py` | Assignment verifier |
| `analysis/sat_exact.py` | PySAT exact synthesis encoder (K=62 check) |
| `experiments_eslim/` | eSLIM experiment scripts and intermediate BLIFs |
| `paper/paper.tex` | Research paper draft |
| `PROGRESS.md` | Append-only experiment log |
| `HANDOVER.md` | Toolchain setup and rebuild instructions |
| `LONGHORN_STRATEGY.md` | Explanation of the Longhorn σ remap and 64→63 reduction |
