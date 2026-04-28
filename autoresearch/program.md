# FP4 Multiplier Autoresearch Program

## Goal
Minimize the gate count in `autoresearch/multiplier.py` while maintaining correctness on all 256 FP4×FP4 input pairs.

**Metric**: `gate_count` from `eval_circuit.evaluate_fast()` — lower is better.
**Constraint**: `correct == True` (all 256 pairs must produce correct QI9 output).

## Problem Summary

Design a circuit that multiplies two 4-bit FP4 values and outputs a 9-bit QI9 two's complement integer representing 4× the product.

- Legal gates: AND(x,y), OR(x,y), XOR(x,y) — cost 1 each; NOT(x) — cost 1
- Constants (True/False) are free; input remapping is free
- The INPUT_REMAP dict remaps FP4 values to 4-bit codes — choose this optimally

FP4 values: 0, ±0.5, ±1, ±1.5, ±2, ±3, ±4, ±6

## Critical Mathematical Structure

ALL outputs obey: **|4 × a × b| = K × 2^shift**
where K ∈ {1, 3, 9} and shift ∈ {0..6}

In binary:
- K=1: exactly ONE bit set (a power of 2)
- K=3: TWO ADJACENT bits set (e.g., 0b00001100 for K=3, shift=2)
- K=9: TWO BITS SET 3 APART (e.g., 0b00001001 for K=9, shift=0)

This means the 8-bit magnitude output has at most 2 bits set. This is EXTREME sparsity.

Each non-zero magnitude decomposes as: mag = 1.5^M × 2^E
- M ∈ {0, 1}     (mantissa type)
- E ∈ {-1,0,1,2} (exponent)

Product: K = 1.5^(M_a + M_b), shift = (E_a + E_b + 2) - M_sum_correction

## Current Best (update this section each iteration)

| Approach | Gates | Notes |
|----------|-------|-------|
| Baseline structural | TBD | First correct implementation |

**Target milestones**:
- 80 gates: structural decomposition baseline
- 60 gates: with optimal remapping + exact QM cover
- 40 gates: with gate sharing and multi-level optimization
- 25 gates: theoretical near-optimal

## Encoding Strategy

Current: Canonical (M, E+1) encoding:
- bit 0 (MSB) = sign
- bit 1 = M (mantissa flag: 1 if 1.5^1 component)
- bits 2-3 = (E+1) in range {0,1,2,3}
- Zero = 0b0111 (mag_code = 111)

This makes M and E directly readable from input bits.

Alternative encodings found by search are in `autoresearch/data/best_remappings.json`.

## How to Run Experiments

```bash
# Test baseline
python autoresearch/run.py "baseline"

# Run a specific experiment
python experiments/exp_qm_exact.py

# Test any circuit file
python eval_circuit.py path/to/multiplier.py
```

## Approaches to Try (in priority order)

### High Priority
1. **Exact QM cover**: Replace greedy set cover with Petrick's method in `fp4_synth_real.py`. Run all 8! remappings with exact cover and pick the best.

2. **Direct structural optimization**: The `mag_bit()` function in the baseline creates many redundant AND(k_is_X, sh_Y) computations. Many `k_is_X AND sh_Y` combinations are never simultaneously true for valid inputs — exploit this to eliminate gates.

3. **Shared sub-expressions**: k_is_1, k_is_3, k_is_9 each appear many times. Compute once. Also `AND(k_is_3, sh[i])` and `AND(k_is_3, sh[i-1])` can be combined.

4. **Conditional negation improvement**: Current uses 3n-1=23 gates for 8-bit. Since magnitude only takes 19 distinct values, many carry patterns never occur — use don't cares to simplify the carry chain.

5. **Zero detection simplification**: With canonical encoding, zero_a = AND(a1, AND(a2, a3)) = 3 gates. Can we do better? With a different encoding where zero maps to 0b0000, zero_a = NOR(a1, OR(a2, a3)) ... depends on encoding.

### Medium Priority
6. **ABC synthesis**: Export truth table as PLA/BLIF, run through ABC tool with `resyn2` optimization. This finds multi-level minimizations automatically.

7. **Direct 9-bit synthesis**: Bypass the 2-stage (magnitude + sign) approach. Use QM minimization directly on all 9 output bits from 8 inputs, with aggressive gate sharing.

8. **XOR decomposition**: Check if output_bit_i = f(a_bits) XOR g(b_bits) — if so, implement f and g independently (smaller inputs) and XOR them together.

### Research Directions
9. **Lower bound proof**: The circuit has 8 inputs, 9 outputs, and 256 input combinations with 37 distinct outputs. What is the Shannon lower bound? Can we prove a circuit of fewer than N gates is impossible?

10. **DNNF/BDD minimization**: Represent as DNNF or BDD, then map to gates.

## Rules for the Loop

1. ALWAYS verify with `evaluate_fast()` before claiming a gate count
2. ONLY update `multiplier.py` if `correct=True` AND `gate_count < current_best`
3. Log EVERY experiment to `log.jsonl` (even failures)
4. When trying a new approach, document WHY you expect it to improve
5. If an approach reduces gates by ≥5%, explore it further before switching
6. Don't make incremental changes when a structural rethink might be better

## Log Format

Each line in `log.jsonl`:
```json
{"timestamp": "...", "approach": "...", "correct": true/false, "gate_count": N, "notes": "..."}
```
