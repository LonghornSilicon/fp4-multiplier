# FP4 Multiplier Gate Minimization — Research Notes

## Problem

Design a minimum-gate Boolean circuit computing FP4×FP4→QI9:
- **Input**: two FP4 numbers (float4_e2m1fn, 4-bit floating point), each encoded as 4 bits with an arbitrary input remapping
- **Output**: 9-bit two's complement fixed-point integer (QI9), where LSB = 1/4
- **Primitive gates**: NOT, AND, OR, XOR (each costs 1 gate; 2-input except NOT)
- **Free**: constants (0, 1), input remapping (arbitrary bijection on FP4 values to 4-bit codes)

FP4 (E2M1) has 16 values: {0, ±0.5, ±1, ±1.5, ±2, ±3, ±4, ±6}.  
The product of two FP4 values scaled ×4 fits in 9-bit two's complement (range −256 to 255, but actual max is |6×6|×4 = 144).

---

## Mathematical Structure (Key Insight)

All non-zero FP4 magnitudes are of the form:

```
|a| = 1.5^M_a × 2^(E_a)
```

where M_a ∈ {0,1} (mantissa type) and E_a ∈ {-1, 0, 1, 2} (exponent).

| FP4 Magnitude | M | E |
|:---:|:---:|:---:|
| 0.5 | 0 | -1 |
| 1.0 | 0 | 0 |
| 2.0 | 0 | 1 |
| 4.0 | 0 | 2 |
| 1.5 | 1 | 0 |
| 3.0 | 1 | 1 |
| 6.0 | 1 | 2 |

The product magnitude is:
```
|a × b| = 1.5^(M_a + M_b) × 2^(E_a + E_b)
```

Scaled by 4 (for QI9): `QI9_magnitude = 1.5^M_sum × 2^S`

where:
- **M_sum** = M_a + M_b ∈ {0, 1, 2} → determines **K-type**
- **S** = E'_a + E'_b ∈ {0,...,6} → determines **shift** (using E' = E+1 ∈ {0,...,3})

K-types and their bit patterns:
| M_sum | K value | QI9 bits set |
|:---:|:---:|:---|
| 0 (K=1) | 1 × 2^S | bit S only |
| 1 (K=3/2) | 3 × 2^(S-1) = 2^S + 2^(S-1) | bits S and S-1 |
| 2 (K=9/4) | 9 × 2^(S-2) = 2^(S+1) + 2^(S-2) | bits S+1 and S-2 |

The QI9 magnitude has **at most 2 bits set** (extreme sparsity — only 19 distinct non-zero values out of 256 possible 8-bit patterns).

---

## Circuit Architecture

The multiplier decomposes into 5 stages:

```
Inputs: a0..a3, b0..b3 (4-bit FP4 codes with remapping)
  │
  ├── Stage 1: Sign          sign = XOR(a0, b0)
  │
  ├── Stage 2: Non-zero detect  nz = OR(a1..a3) AND OR(b1..b3)
  │
  ├── Stage 3: Magnitude circuit
  │     ├── E-sum: S = (a2,a3)_binary + (b2,b3)_binary    [2-bit adder]
  │     ├── K-flags: k9 = NOR(a1,b1), k3 = XOR(a1,b1), nmc = OR(a1,b1)
  │     ├── K-masking: AND each K-flag with nz
  │     ├── S decoder: one-hot sh_0..sh_6
  │     ├── AND-terms: K × sh_j products
  │     └── OR assembly: m_i = nmc_i OR k3_{i+1} OR k9_{i-1} OR k9_{i+2}
  │
  ├── Stage 4: Conditional 2's complement negation
  │     Carry chain from LSB to MSB, carry-in = sign
  │
  └── Stage 5: Sign masking
        res0 = AND(sign, nz)
        res1..res8 = conditional negation outputs (auto-zero via K-masking)

Output: res0..res8 (9-bit QI9)
```

---

## Encoding Design

The input remapping is free, so we choose it to minimize circuit complexity.

**Chosen encoding** (magnitude code = a1 a2 a3, MSB first):

| Code | Magnitude | M | E' |
|:---:|:---:|:---:|:---:|
| 000 | zero | — | — |
| 001 | 1.5 | 1 | 1 |
| 010 | 3.0 | 1 | 2 |
| 011 | 6.0 | 1 | 3 |
| 100 | 0.5 | 0 | 0 |
| 101 | 1.0 | 0 | 1 |
| 110 | 2.0 | 0 | 2 |
| 111 | 4.0 | 0 | 3 |

**Key property**: E'_a = (a2, a3) as a 2-bit binary number, for all non-zero codes.  
**Key property**: M_a = NOT(a1) (M=1 for codes 001,010,011; M=0 for codes 100,101,110,111).  
**Key property**: Zero maps to code 000, enabling zero detection via NOR tree (5 gates).

From these, the K-flags derive directly:
```
not_k9 = OR(a1, b1)           # M_sum ≠ 2  [= 1 gate]
k9     = NOT(OR(a1, b1))      # M_sum = 2  [= 1 gate, after OR]
k3     = XOR(a1, b1)          # M_sum = 1  [= 1 gate]
```

---

## Magnitude Output Formula

For output bit i of the 8-bit magnitude (QI9 bits 1–8):

```
m_i = (not_k9 AND S==i) OR (k3 AND S==i+1) OR (k9 AND S==i-1) OR (k9 AND S==i+2)
```

This follows directly from the K-type bit patterns:
- **K=1** (not_k9, not k3): single bit at S → contributes to m_i when S=i
- **K=3/2** (k3): bits at S and S-1 → k3 contributes to m_i at S=i (upper) and S=i+1 (lower bit)
- **K=9/4** (k9): bits at S+1 and S-2 → k9 contributes to m_i at S=i-1 (upper) and S=i+2 (lower)

Note: `not_k9 AND S==i` handles both K=1 and the upper bit of K=3/2 correctly, because:
- K=1: nmc=1, k3=0
- K=3/2: nmc=1, k3=1 (and the upper bit is the S==i term)

### Impossible K×S Combinations (saves AND-terms)

With the chosen encoding, M=1 requires E'∈{1,2,3} (codes 001,010,011 for the M=1 group):
- **k9 AND S∈{0,1} impossible**: k9 requires M_a=M_b=1 → E'_a,E'_b≥1 → S≥2
- **k3 AND S=0 impossible**: k3 requires one M=1 → that input has E'≥1 → S≥1

This eliminates 3 AND-terms (k9_0, k9_1, k3_0), reducing from 21 to **18 AND-terms**.

---

## Optimization History

### v1 → v2: Gate sharing in K×shift precomputation (135→126 gates, −9)
- Pre-compute shared sub-expressions for K-type × shift combinations
- Eliminate redundant per-bit computations

### v2 → v3: Direct formula, eliminate subtractor (126→101 gates, −25)
- Previous approach used E-sum with a subtractor to compute E_a + E_b (costs ~11 gates)
- By defining E' = E+1 (making all exponents ≥0), the E-sum is a simple 2-bit adder
- The formula `m_i = nmc×sh_i | k3×sh_{i+1} | k9×sh_{i+2} | k9×sh_{i-1}` uses S=E'_a+E'_b directly
- No subtractor needed!

### v3 → v4: Zero=000 encoding + K-flag masking (101→89 gates, −12)
- **Encoding change**: zero maps to code 000 (vs 100 in v3)
- **Zero detection**: NOR tree costs 5 gates (vs 9 gates with zero=100)
- **Key insight**: Instead of masking 9 output bits with `nz` (9 AND gates), mask the 3 K-flags:
  - `k9 = AND(k9_raw, nz)`, `k3 = AND(k3_raw, nz)`, `nmc = AND(not_k9, nz)` (3 AND gates)
  - When nz=0 (either input zero): all K-flags=0 → all magnitude bits=0 → all outputs=0
  - res0 = AND(sign, nz) (1 gate for sign masking)
  - Total zero overhead: 5 (detect) + 3 (K-mask) + 1 (sign) = 9 gates vs 19 gates before
- **r8 = m0 pass-through**: Two's complement preserves the LSB (the negation of bit 0 = bit 0 always), saving 1 XOR gate in the carry chain

### v4 → v4b: S decoder optimization (89→88 gates, −1)
- **Key observation**: S = E'_a + E'_b ≤ 3+3 = 6 (maximum possible)
- In the S decoder: u11 = AND(s2, s1) = 1 only when S∈{6,7}
- Since S=7 is impossible, u11=1 implies S=6 implies s0=0 implies ns0=1
- Therefore sh6 = AND(u11, ns0) = u11 (the AND with ns0 is redundant)
- **Saves 1 gate** in the S decoder (14→13 gates)

### v4b → v4c: Prefix-OR conditional negation (88→86 gates, −2)
- **Key insight**: For 2's complement negation, carry_i = 1 iff all lower bits are 0 = NOT(OR(m_0,...,m_{i-1}))
- Therefore: `result_i = XOR(m_i, AND(sign, prefix_or_i))` where `prefix_or_i = OR(m_0,...,m_{i-1})`
- This replaces the carry chain (22 gates: 8 XOR + 7 XOR + 7 AND) with:
  - 6 OR gates for prefix chain: p2=OR(m0,m1), p3=OR(p2,m2), ..., p7=OR(p6,m6)
  - 7 AND gates: sp1=AND(sign,m0), sp2=AND(sign,p2), ..., sp7=AND(sign,p7)
  - 7 XOR gates: r_i = XOR(m_i, sp_i), plus r8=m0 passthrough
- Total: 6+7+7 = **20 gates** (down from 22), saving 2 gates
- Correctness: prefix_or_0 is empty (=0), so r8=XOR(m0,0)=m0 (free); for sign=0 all sp_i=0 so r_i=m_i (magnitude pass-through); for sign=1 r_i = XOR(m_i, OR(m_0..m_{i-1})) which is exactly 2's complement negation

### v4c → v4d: sp7 = res0 alias from prefix_or_7 = nz (86→84 gates, −2)
- **Key observation**: prefix_or_7 = OR(m_0, ..., m_6). For all 19 reachable product magnitudes, this OR equals nz.
- **Why**: The only product magnitude with bit 7 set is 144 (= 9×16, K=9 case at maximum shift), and 144 = 0b10010000 also has bit 4 set. Therefore every non-zero magnitude has at least one bit in positions 0..6 set → prefix_or_7 = nz.
- **Consequence**: sp7 = AND(sign, prefix_or_7) = AND(sign, nz) = res0 (already computed in the sign-mask stage).
- **Eliminations**: drop the p7 = OR(p6, m6) gate AND the sp7 = AND(sign, p7) gate; reuse res0 directly in the MSB XOR (`r1 = XOR(m7, res0)`).
- **Cond_neg total**: 5 OR + 6 AND + 7 XOR = **18 gates** (down from 20).
- **Note**: this saving is *structural* (depends on the 19-magnitude set being reachable), not generic to 8-bit conditional negation. It only kicks in because the reachable output set is sparse.

### v4d → v4e: Cirbo SAT exact-synthesis for S-decoder (84→82 gates, −2)
- **Method**: Used Cirbo's `CircuitFinderSat` SAT-based exact synthesizer in our exact AND/OR/XOR/NOT basis.
- **S-decoder (3-in 7-out)**: N=7,8,9 UNSAT (<6s each); N=10 **UNSAT (476s)**; N=11 SAT (0.43s). **11 gates is the proven optimum.**
- **11-gate circuit found** (4 AND + 2 OR + 4 XOR + 1 NOT):
  ```python
  _or01  = OR(s2, s1)          # 2 OR gates
  _or012 = OR(s0, _or01)
  sh0    = NOT(_or012)         # 1 NOT (NOR of s2,s1,s0)
  sh1    = XOR(_or01, _or012)  # = s0 AND NOT(s2 OR s1)
  _xor2  = XOR(s0, _or012)
  _and2  = AND(s2, _xor2)      # 4 AND gates
  sh3    = AND(s1, s0)
  sh5    = AND(s2, s0)
  sh6    = AND(s1, _and2)      # 4 XOR gates
  sh2    = XOR(_xor2, _and2)
  sh4    = XOR(_and2, sh6)
  ```
- **Saves 2 gates** vs the 13-gate hand-crafted decoder (3 NOT + 10 AND).
- **Circuit verified**: all 7 S-values decoded correctly; all 256 FP4×FP4 pairs verified CORRECT at 82 gates.

---

## Final Gate Count: 82

| Stage | Gates | Notes |
|:---|:---:|:---|
| Sign | 1 | XOR(a0,b0) |
| Non-zero detect | 5 | 2 OR-trees + 1 AND |
| E-sum | 7 | 2-bit adder for (a2,a3)+(b2,b3) |
| K-flags | 3 | OR, NOT, XOR |
| K-masking | 3 | AND each with nz |
| S decoder | 11 | 4 AND + 2 OR + 4 XOR + 1 NOT (Cirbo SAT-optimal in {AND,OR,XOR,NOT}) |
| AND-terms | 18 | 7 nmc + 6 k3 + 5 k9 terms |
| Magnitude OR | 15 | OR assembly for m0..m7 |
| Conditional negation | 18 | Prefix-OR formula: 5 OR + 6 AND + 7 XOR (r8=m0 free, sp7=res0) |
| Sign mask | 1 | AND(sign, nz), also serves as sp7 |
| **Total** | **82** | |

---

## Approaches Eliminated

### Flat SOP (Quine-McCluskey) Synthesis
- Searched all 8! = 40,320 magnitude encodings
- Best flat SOP (6-input, per-bit QM minimization): **288 gates total** (264 magnitude + 24 overhead)
- Even with zero=000 constraint (7! = 5040 perms): similar result
- Flat 2-level logic is completely infeasible for this problem — multi-level synthesis is essential

### Direct 8-Input SOP
- Treating all 9 output bits as functions of all 8 inputs (flat SOP)
- Results in 2000+ gates per output bit
- Confirmed infeasible; structural decomposition is necessary

### Shared Gate Synthesis (Track C)
- XOR/AND decomposability analysis across output bits
- Result: no useful decomposition found; the sign-magnitude structure already captures the main sharing

### ABC Logic Synthesis (Track D)
- Generated PLA format files for the magnitude function
- Requires ABC binary installation; PLA files saved to `autoresearch/data/pla_files/` for manual use

---

## Structural Lower Bound Analysis

Each stage appears near-optimal:
- **Sign** (1 gate): XOR is the minimum for sign computation
- **Non-zero detect** (5 gates): Minimum OR-tree for detecting zero in 3-bit codes × 2 inputs + AND
- **E-sum** (7 gates): Standard minimum for 2-bit + 2-bit adder (known optimal)
- **K-flags** (3 gates): OR + NOT + XOR is minimal for computing not_k9, k9, k3
- **K-masking** (3 gates): One AND per K-flag, no sharing possible
- **S decoder** (13 gates): Near-optimal 3→7 one-hot with sharing; sh6=u11 eliminates 1 redundant AND
- **AND-terms** (18 gates): 7+6+5, determined by number of valid K×S combinations
- **Magnitude OR** (15 gates): Optimal binary OR tree given 0+1+2+3+3+2+2+2 terms per bit
- **Cond neg** (18 gates): Prefix-OR formula; r8=m0 free; sp7=res0 (from P_7=nz reachability); 5+6+7 structure; ABC mfs3 with -W 6 finds zero subcircuit replacements; locally minimal
- **S decoder** (11 gates): Cirbo SAT proves N≤10 UNSAT (N=10 UNSAT in 476s completing the proof); N=11 SAT. **11 is the proven optimal gate count.**
- **Sign mask** (1 gate): Minimum for gating sign with nz

**Estimated lower bound (structural decomposition)**: ~75–84 gates. Achieving below this would require either cross-stage sharing not visible in this decomposition, or a fundamentally different topology.

**Empirical evidence from automated synthesis (added 2026-04-28)**:

| Sub-function | Inputs/Outputs | Hand-crafted | ABC `compress2rs` (AIG) |
|:---|:---:|:---:|:---:|
| S-decoder | 3 / 7 | 13 (incl. 3 NOTs) | 11 ANDs |
| E-sum + decoder | 4 / 7 | 20 | 21 ANDs |
| Magnitude | 6 / 8 | 46 | 109 ANDs |
| Full circuit | 8 / 9 | 84 | 274 ANDs |

ABC operating on the flat PLA truth table cannot beat the hand decomposition for the larger functions; structural sharing across the K-flag / S-decoder / mag-OR boundary is invisible from the PLA. ABC is *better* on the standalone S-decoder (11 ANDs vs. our 10 ANDs + 3 NOTs = 13 gates), but those NOTs feed many downstream gates and are essentially free in our basis. The path to <70 likely runs through one of: (a) Cirbo's SAT-based subcircuit-replacement on our existing 84-gate netlist (k_max=8 windows), (b) exact synthesis on the magnitude-only block, or (c) a different topology (e.g. direct signed computation) that exposes new sharing.

---

## Possible Further Reductions

To push below 88 gates, one would need to explore:

1. **ABC multi-level synthesis** on the 6-input magnitude function (factored from the structural formula): could find cross-stage sharing not visible manually
2. **Alternative carry chain implementations** exploiting the output sparsity (≤2 bits set per magnitude value)
3. **Different overall circuit topology**: e.g., precompute both ±magnitude and MUX vs. conditional negation
4. **SAT/ILP-based exact synthesis**: for proving optimality of individual stages
5. **Asymmetric K-type implementations**: exploiting that K=1, K=3/2, and K=9/4 have different frequencies in the truth table

---

## Verification

The circuit passes all 256 FP4×FP4 input pair tests via `eval_circuit.evaluate_fast()`.

```bash
python eval_circuit.py autoresearch/multiplier.py
# Result: CORRECT, Gates: 82 (max per pair)

python etched_take_home_multiplier_assignment.py
# Should pass all 256 asserts
```

---

*Research conducted 2026-04-27 / extended 2026-04-28. Gate count reduced from flat SOP baseline (~288) to structural approach (82) through progressive mathematical insight, systematic optimization, and SAT-based exact synthesis (Cirbo CircuitFinderSat).*
