# LonghornSilicon FP4 Multiplier — 64-Gate Strategy Explainer

Repo studied: https://github.com/LonghornSilicon/fp4-multiplier
Verified: their `submission/colab_paste.py` runs through our `eval_circuit.py` at **64 gates**, 256/256 correct (`longhorn_verify.py`).

This document explains, top to bottom: (a) the problem, (b) what they did differently from us, (c) why it works, and (d) why our path stalled at 81.

---

## 1. The problem (recap)

- 8 input bits: two 4-bit FP4 numbers `(a, b)`, each ∈ {±0, ±0.5, ±1, ±1.5, ±2, ±3, ±4, ±6}.
- 9 output bits: two's-complement `int(round(4·a·b))`, range [−256, 255], practical max |144|.
- Cost: 1 gate per call to `AND/OR/XOR/NOT`. The 4-cell library is fixed; XOR2 costs the same as AND2.
- Free: a 16→16 input remap (any bijection mapping FP4 values to 4-bit codes).
- 256 input pairs → 31 effective care-set rows (16 nonzero magnitude pairs × signs); after dedup of `−0` codes the harness checks all 256.

Our best (independent): **81** gates, after 82-gate v4e + a care-set resub finding `k9 = XOR(nz, nmc)`.
Their best: **64** gates, 6.09× over flat ABC, 2.6× over behavioral Verilog, 21% under our 81.

---

## 2. The four differences that mattered

| | Us | Longhorn |
|---|---|---|
| **Decomposition** | `1.5^M_sum × 2^E_sum` (M ∈ {0,1}, E ∈ {0..6}) | `(2·lb + ma) × 2^class` — a 2-bit "core mantissa" times a 2^class shift |
| **Magnitude path** | One-hot `S` decoder (11 gates) → 18 K×sh AND-terms → 15-OR assembly | 7-gate Cirbo-optimal 2×2 mantissa multiplier → variable shift `<<K` (K ∈ 0..4) |
| **Conditional negate** | Prefix-OR + sign-AND + XOR (18 gates) | NAND-chain "below" detector (mut2) + raw P_nonzero direct-route for Y[8] (mut11) |
| **Search** | Hand optimization, ABC, Cirbo on sub-functions, bit-parallel resub | yosys → ABC `&deepsyn` → **eSLIM SAT-windowed local improvement** → **gate-neutral XOR re-association** before re-running eSLIM |

The remap is a force multiplier; it makes `(lb, ma)` line up so the 2×2 product is clean.

---

## 3. The decomposition, top-to-bottom

### 3.1 The remap σ = (0,1,2,3,6,7,4,5)

Magnitude index → 4-bit code:

| value | code | a[3] sign | a[2] | a[1] | a[0] |
|---|---|---|---|---|---|
| 0 | 0000 | 0 | 0 | 0 | 0 |
| 0.5 | 0001 | 0 | 0 | 0 | 1 |
| 1 | 0010 | 0 | 0 | 1 | 0 |
| 1.5 | 0011 | 0 | 0 | 1 | 1 |
| 4 | 0100 | 0 | 1 | 0 | 0 |
| 6 | 0101 | 0 | 1 | 0 | 1 |
| 2 | 0110 | 0 | 1 | 1 | 0 |
| 3 | 0111 | 0 | 1 | 1 | 1 |

`a[3]` is the sign bit; the remap rewires only the 8 magnitudes. The crucial property:

- `ma = a[0]` is "is this a 1.5-mantissa value?": ma=1 iff magnitude ∈ {0.5, 1.5, 3, 6}.
- `lb_a = a[1] | a[2]` is "is magnitude ≥ 1?": lb=1 iff magnitude ∈ {1, 1.5, 2, 3, 4, 6}.
- The 2-bit "core mantissa" is `(lb · 2 + ma)` ∈ {0, 1, 2, 3} — exactly what you'd want to multiply by 2×2.
- The "exponent class" is `sa1 = (a[2] & el_a, a[2] & ~el_a)` where `el_a = a[1] ^ a[2]`, encoding 0/1/2 for {0..1.5} / {2,3} / {4,6}.

So magnitude = `core_mantissa × 2^class`, and `class ∈ {0,1,2}` becomes a 2-bit unsigned addable to another `class`. This is **structurally simpler** than our `M ∈ {0,1}` + `E ∈ {0..6}` split because:
- Our `S = E_a + E_b ∈ {0..6}` needed a one-hot decoder (11 gates).
- Their `K = sa1_a + sa1_b ∈ {0..4}` is a 2-bit + 2-bit add (5 gates), driving a variable shift mux.

The remap σ was **not** chosen by hand; they swept all 5040 sign-symmetric magnitude permutations through ABC `&deepsyn` and picked the best (4 perms tied at 85 gates). The structural Verilog template is the same for every perm; only the decoder bits differ.

### 3.2 The 2×2 mantissa multiplier (7 gates, Cirbo-proven optimal)

Their Verilog body:

```verilog
wire pp_aml = lb_a & mb;          // 1 AND
wire pp_alb = ma & lb_b;          // 1 AND
wire pp_lll = lb_a & lb_b;        // 1 AND
wire P0 = ma & mb;                // 1 AND
wire P1 = pp_aml ^ pp_alb;        // 1 XOR
wire c1 = pp_aml & pp_alb;        // 1 AND
wire P2 = pp_lll ^ c1;            // 1 XOR
wire P3 = pp_lll & c1;            // 1 AND
```

That's a 4-bit unsigned product `P3 P2 P1 P0` of two 2-bit numbers, in 8 gates of straightforward half-adder structure. **Cirbo SAT proves G=6 UNSAT and G=7 SAT for unsigned 2×2 multiplication** — so the 7-gate optimum is reachable (the form above uses 8, but synthesis collapses one — `pp_lll = lb_a & lb_b` and `c1` patterns let ABC fuse a gate).

This is **the** key compression. We replicated this work clumsily as 18 K×sh AND-terms (`nmc_i`, `k3_i`, `k9_i`) plus a 15-gate OR assembly to compute the same 8-bit magnitude — 33 gates of ours collapse to ~7+shift in their version.

### 3.3 The variable shift `mag = P << K`

`K = sa1 + sb1` is a 2-bit + 2-bit add giving K ∈ {0..4}. Then `P << K` is the variable left-shift of a 4-bit `P` by 0..4 places, producing 8-bit `mag`. Synthesizers compile this to a barrel-shifter / mux network. ABC handles it well — no manual decomposition needed.

### 3.4 NAND-chain "below" detector for conditional negation (mut2)

```verilog
wire below1 = ~mag[0];
wire below2 = below1 & ~mag[1];
wire below3 = below2 & ~mag[2];
... (cascaded)
assign y[i] = mag[i] ^ (sy & ~below_i);  // for i ≥ 1
assign y[0] = mag[0];
```

`below_i` = "all bits below position i are zero". When `sy=1`, output bit i flips iff some lower bit is set (the standard 2's-complement trick: copy bits up to and including the lowest 1, flip everything above). This is structurally identical to our prefix-OR formulation but the **NOT-AND** chain shares inverters across rows, which post-eSLIM compresses better.

### 3.5 Direct Y[8] from raw bits (mut11)

```verilog
assign y[8] = sy & (a[0]|a[1]|a[2]) & (b[0]|b[1]|b[2]);
```

The MSB output (sign bit, after sign extension) doesn't need the `below_7` chain — it equals `sy ∧ P_nonzero`, and `P_nonzero = (a magnitude nonzero) ∧ (b magnitude nonzero)` reads directly off the input bits. This bypass saves several gates (74 → 65 stage in their trajectory hides this contribution, but the source-level rewrite is in `mutations/fp4_mul_mut11.v`).

---

## 4. The synthesis pipeline (the part we never touched)

```
fp4_mul.v (Verilog source, mut11 form, ~70 lines)
    │
    ▼
yosys synth.ys                 # structural elaboration
    │  produces flat .blif
    ▼
ABC: strash; ifraig; scorr; dc2; balance; rewrite; refactor;
     &get -n; &deepsyn -T 3 -I 4; &put;
     mfs2; dch -f; map -a -B 0 -liberty contest.lib
    │
    │  → 74 gates (deterministic, ABC-saturated)
    ▼
eSLIM --syn-mode sat --size 6  (240s)
    │  → 70 gates
    ▼
eSLIM --syn-mode sat --size 8  (900s)
    │  → 65 gates
    ▼
gen_variants.py: rewrite XOR(XOR(a,b),c) → XOR(a,XOR(b,c)) at w_75
    │  → "gate-neutral perturbation" (still 65, different AIG)
    ▼
eSLIM --syn-mode sat --size 8 --seed 7777  (900s)
    │  → **64 gates** (different convergence basin: 6 NOTs vs 7)
    ▼
src/fp4_mul.blif (canonical answer)
```

### 4.1 What is eSLIM?

eSLIM ([Reichl & Slivovsky, SAT 2024](https://drops.dagstuhl.de/entities/document/10.4230/LIPIcs.SAT.2024.23), [GitHub](https://github.com/fxreichl/eSLIM)) is **SAT-based windowed local improvement for combinational circuits**. Algorithm:

1. Pick a window of ≤ k gates in the netlist (k ∈ {6, 8, 10, ...}).
2. Compute the window's input/output relations (truth table over its boundary).
3. Pose a SAT query: "is there an equivalent sub-circuit using ≤ (current_size − 1) gates over the same boundary?"
4. If SAT, replace the window with the smaller circuit. If UNSAT, slide the window.
5. Iterate until no window can be reduced.

The key knobs are `--size k` (window size; larger = finds more replacements but exponentially slower SAT) and `--syn-mode sat | aig`. **Crucial detail**: `--syn-mode sat` keeps XOR2 as a primitive in the working representation, matching the contest cost. AIG mode would expand XOR to 3 ANDs + DeMorgan inverters, then post-map back — which loses the XOR-friendly structure (their AIG-mode runs gave **91–94 gates**, worse than 74).

This is the tool that took them 74 → 70 → 65. We never ran it.

### 4.2 What is the "gate-neutral XOR re-association" trick?

Once eSLIM saturates at 65, re-running it on the same netlist returns 65 (deterministic local optimum). The unlock: rewrite a `XOR(XOR(a,b),c)` somewhere in the AIG to `XOR(a,XOR(b,c))`. **Same gate count**, same function, but a structurally different AIG → eSLIM's window-walking lands in a different basin → finds a 6-NOT solution instead of a 7-NOT one. That's the 65 → 64 win.

The variant generator `workspace/eslim_runs/gen_variants.py` enumerates such rewrites systematically; they ran 600+ eSLIM configurations (5 starting variants × 5 window sizes × 5+ seeds) and got **124 distinct 64-gate solutions, all with exactly 6 NOTs**. No 5-NOT solution found anywhere in the explored space → strong empirical evidence (not formal proof) that 64 is the floor under this cost metric.

### 4.3 Lower bounds (Cirbo SAT, sub-block proofs)

They proved minima for sub-blocks via Cirbo (the same tool we used for the S-decoder):
- Y[0] = 4 gates (proven exact)
- 2×2 unsigned multiplier = 7 gates (proven exact)
- Y[8] = 7 (proven exact)
- K computation ≥ 8
- K-shift ≥ 13
- Conditional negate ≥ 11
- **Sum (no sharing): ≥ 47.** 64 with sharing is plausibly close to optimal.

Their attempted full-circuit Cirbo SAT at G=50/55/58/60 OOM'd or timed out; a custom DIMACS encoder + kissat at G=63 ran 16h 35min with no verdict. Full-circuit lower-bound proof is out of reach without an HPC cluster.

---

## 5. Why we never approached it this way

Five answers, in priority order:

### 5.1 We picked the wrong decomposition
Our v1 derivation factored magnitude as `1.5^M × 2^E`. That's mathematically equivalent to `(2·lb + ma) × 2^class` but the boolean structure is much worse:
- Our `M_sum` has 3 K-types (k9, k3, nmc), each contributing different bit patterns at different offsets, requiring an 18-AND-term + 15-OR assembly.
- Their core-mantissa is just a 2×2 multiply, which collapses to 7 gates by Cirbo lower bound.

By the time we were optimizing the K×sh AND-terms, the decomposition itself was already 25–30 gates more expensive than necessary. Local optimization can't recover that.

### 5.2 We didn't search remaps systematically
We did try an encoding sweep (the `experiments/exp_encoding_search.py` referenced in our PROJECT_RESEARCH_CHECKPOINT) but it wasn't tightly coupled to a Verilog template the way theirs is. Their `gen_struct.py` emits the **same** structural Verilog for any sigma; only the decoder is parameterised. So sweeping 5040 perms over yosys+ABC is pure CPU. Ours hand-builds a circuit per encoding, which doesn't generalise.

### 5.3 We used SAT only for sub-functions, never for windowed local optimization
We used Cirbo on the S-decoder (got 11-gate proven optimum). What we **did not** do:
- run eSLIM on the full netlist
- iterate eSLIM at increasing window sizes (`--size 6` → `--size 8` → ...)
- use SAT windows over the full netlist's structure

eSLIM is the tool that took them from 74 → 65. Without it, ABC saturates and you stall.

### 5.4 We worked at the gate level; they worked at the Verilog level
Our `sa_*.py` infrastructure operates on flat netlists (gate-by-gate). Their tooling operates on Verilog source — letting yosys/ABC do the structural lifting and using SAT (Cirbo, eSLIM) at well-chosen leverage points. The gate-level perspective is correct but its mutation neighborhood is too local; structural-rewrite mutations at the Verilog level move you across multiple basins at once.

### 5.5 We never built a hand-mutation library
They wrote 24+ explicit Verilog variants (mut1..mut24, plus struct/hand/bw/hier). Each is a different decomposition: `mut2` is the NAND-chain conditional negate, `mut11` is the raw-P_nonzero direct-route for Y[8], `mut30..34` are OR-ladder above-detector / one-hot K + SOP / Sklansky parallel-prefix / Booth-2 recoding / Shannon decomposition. Some give 75-78, some 92, some 110. The winning 74-gate input came from mut11. We had one decomposition; they had thirty.

This is the **AlphaEvolve methodology**: an LLM (or a person) proposes mutation drafts, a verifier evaluates, the loop keeps improvements. We knew about this — we even tried something similar — but never ran it as a tight loop on Verilog source.

---

## 6. The minimum viable path to 64

To replicate their result on this machine, the steps are:

1. **Switch decomposition** to `(2·lb + ma) × 2^class`. Use `mutations/fp4_mul_mut11.v` directly.
2. **Apply the σ remap** `(0,1,2,3,6,7,4,5)` for the input encoding.
3. **Synthesize via yosys + ABC** with the exact recipe in `src/synth.ys`. This gives 74 gates deterministically.
4. **Build and run eSLIM**:
   ```bash
   git clone https://github.com/fxreichl/eSLIM.git /tmp/eSLIM
   cd /tmp/eSLIM/src/bindings && cmake -B build && cmake --build build -j
   pip install pybind11 bitarray
   PYTHONPATH=/tmp/eSLIM/src/bindings/build python3 /tmp/eSLIM/src/reduce.py \
       fp4_flat.blif fp4_pass1.blif 240 --syn-mode sat
   ```
   → 70 gates after pass 1, 65 after pass 2 with `--size 8`, 64 after the gate-neutral XOR perturbation re-run.

The whole pipeline is reproducible with what's in their repo (`src/synth.ys`, `experiments_external/eslim/scripts`, `workspace/eslim_runs/gen_variants.py`).

---

## 7. Verification on our harness

`longhorn_verify.py` in this repo pastes their `colab_paste.py` body into our `eval_circuit.evaluate_fast` harness and gets:

```
Gates: 64
Correct: True
Errors: 0
```

256/256 input pairs pass under the σ remap.

---

## 8. Honest comparison

| | Us | Longhorn |
|---|---|---|
| Best gate count | 81 | 64 |
| Verified | 256/256 | 256/256 |
| Decomposition | 1.5^M × 2^E (sub-optimal) | core_mantissa × 2^class (Cirbo-optimal 2×2 mul) |
| Remap searched? | partial | full 5040-perm sweep |
| Tools used | Hand opt, ABC, Cirbo (sub-funcs), gate-level resub | yosys + ABC + Cirbo + **eSLIM** + gate-neutral perturb |
| Verilog mutations | none | 30+ |
| Time | ~2 days | ~3 days, 28-vCPU VPS |

The 81-gate and 64-gate results are the same problem solved with fundamentally different methodology. Their 17-gate edge breaks down (roughly):
- ~15 gates from the better decomposition (2×2 mul vs K×sh AND-terms)
- ~5 gates from eSLIM windowed SAT local improvement on top of ABC
- ~2 gates from gate-neutral perturbation + eSLIM re-run

---

*Written 2026-04-28 after pivoting from our independent 81-gate path to study LonghornSilicon's 64-gate public solution. The methodology is fully reproducible from `LONGHORN_STRATEGY.md` + their repo.*
