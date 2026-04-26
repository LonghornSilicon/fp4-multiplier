# INSTRUCTIONS.md — Understanding the FP4 Multiplier and Where It Fits in Inference

**A teaching doc, written for Alan.** Read top to bottom. Each section answers "what" then "why," and ends with "how it connects to the next."

---

## 0. The 30-second framing

You're staring at 74 logic gates that compute one tiny operation: take two 4-bit floating-point numbers and produce 9 bits representing their product. That's *one* multiplication. A modern transformer model running inference doesn't do *one*; it does **trillions per second.** Every gate you save in this multiplier saves silicon area in every copy on the chip × every chip in the fab run × every datacenter that buys them. **74 instead of 85 means ~13% less area in the part of the chip that dominates inference compute.**

This document teaches you how a 4-bit number can carry meaning, how multiplication of two 4-bit numbers becomes the heartbeat of every transformer inference, and why an ASIC-grade gate count matters for tape-out.

---

## 1. What is FP4 and why is it weird?

### 1.1 Numbers in computers — quick rebuild

A computer represents a real number with a finite bit string. Two main schemes:

**Integers** — bits map to powers of 2: `0b1011` = 1·8 + 0·4 + 1·2 + 1·1 = 11. Simple, exact, but limited range.

**Floating-point** — split the number into a *sign*, an *exponent*, and a *mantissa* (fractional part):
$$\text{value} = (-1)^\text{sign} \times \text{mantissa} \times 2^\text{exponent}$$

You're trading some precision for a much wider dynamic range. IEEE-754 double precision uses 64 bits (1 sign, 11 exponent, 52 mantissa). FP4 uses **4 bits total**.

### 1.2 MX-FP4 / E2M1 specifically

The "MX-FP4" format (microscaling FP4, an OCP standard) and its pure form **E2M1** allocate:
- 1 sign bit
- 2 exponent bits (the "E2")
- 1 mantissa bit (the "M1")

That's 4 bits. The 16 possible bit patterns decode to these values (with both `0000` and `1000` decoding to 0 — there's a "signed zero" we ignore):

| code | value | code | value |
|:----:|:-----:|:----:|:-----:|
| 0000 | +0 | 1000 | -0 |
| 0001 | +0.5 | 1001 | -0.5 |
| 0010 | +1 | 1010 | -1 |
| 0011 | +1.5 | 1011 | -1.5 |
| 0100 | +2 | 1100 | -2 |
| 0101 | +3 | 1101 | -3 |
| 0110 | +4 | 1110 | -4 |
| 0111 | +6 | 1111 | -6 |

Just **8 magnitudes** (with signs giving 16 codes). Notice the spacing: the gaps grow geometrically — 0.5, 1, 1.5, 2, 3, 4, 6 — that's the floating-point's gift: a wide dynamic range at the cost of resolution between values.

### 1.3 Why so few bits?

A neural network is mostly multiply-and-accumulate operations on weights and activations. Empirically (Microsoft's MX paper, Meta's MX deployment, NVIDIA's NVFP4 on Blackwell), you can quantize down to 4 bits per number with a per-block shared 8-bit exponent (the "scaling factor") and lose only a tiny amount of model quality. That cuts the data movement, the multiplier area, and the power per op by 4× compared to FP16. **MX-FP4 is the new floor of training and inference precision in 2026.**

The Etched challenge tells us to ignore the per-block scaling factor (because it's added later, after a 32-input adder) — focus on raw FP4 × FP4.

**Forward link →** This is *one* number. Inference does many. The multiplier we're optimizing is the atom.

---

## 2. What does the multiplier actually do?

### 2.1 The contract

**Inputs:** Two FP4 codes `a, b` (4 bits each = 8 input bits total).
**Output:** A 9-bit two's-complement integer **Y = 4 · val(a) · val(b)**.

The "4 ×" is there because the smallest nonzero product, 0.5 × 0.5 = 0.25, is fractional. Multiplying by 4 makes every possible output an integer: range −144..+144, fits in 9-bit signed two's complement.

### 2.2 What's "two's complement"?

Two's complement is the standard way computers represent signed integers in binary. For an `N`-bit two's-complement integer:
- Bit `N-1` (the MSB) has weight `−2^(N-1)`.
- All other bits have weight `+2^i`.

So for 9 bits:
- `0_00000001` = +1
- `1_11111111` = −1 (because `−256 + 128 + 64 + 32 + 16 + 8 + 4 + 2 + 1 = −1`)
- `0_10010000` = +144
- `1_01110000` = −144

The clever thing: you can add two two's-complement numbers using the same hardware as adding two unsigned ones. That's why two's complement is the universal signed format in CPUs and ASICs.

### 2.3 The "QI9" name

The contest calls our 9-bit output format "QI9" with LSB = 0.25. That's a Q-format (fixed-point) interpretation: the integer value of the 9 bits divided by 4 gives the represented value. So a 9-bit pattern that *as an integer* means 1 represents 0.25 in QI9. Why 0.25? Because the smallest possible product (0.5 × 0.5) is 0.25, so QI9 can hold the exact product without rounding.

In our circuit, we just output the integer 4·a·b — the "QI9 interpretation" is mostly a naming convention that matters when this output feeds into a downstream accumulator.

### 2.4 The map of work

Computing `Y = 4·val(a)·val(b)` in raw bits is a 8-input-to-9-output Boolean function. Every output bit is a Boolean expression over the 8 input bits. We can either:
- **(a)** Brute force: write down the 256-row truth table, hand it to a logic synthesizer (Quine-McCluskey, Espresso, ABC), get a circuit. *That's the 390-gate baseline.*
- **(b)** Exploit structure: floating-point multiplication has natural parts (multiply mantissas, add exponents, fix sign). Build the circuit out of those parts. *That's how we got to 74.*

The journey from 390 → 74 is structure-discovery — telling the synthesizer the right *level* of abstraction so it can find compact gates.

**Forward link →** Now you know what one multiplier does. Next: how multipliers compose into matmul.

---

## 3. From one multiplier to a matmul

### 3.1 MAC: multiply-accumulate

Most useful arithmetic in ML is *not* a single multiplication — it's a **dot product**: take two vectors, multiply element-wise, sum the products. Each element is one multiply-and-accumulate (MAC):

```
acc = a[0]·b[0] + a[1]·b[1] + ... + a[N-1]·b[N-1]
```

Hardware MACs do this in one tightly-pipelined cell: a multiplier (our 70 gates) feeds an adder, the adder writes back to an accumulator register. Then the next pair feeds in.

The reason we output 9-bit two's complement (signed integer) instead of FP4 directly is exactly so the accumulator can use a fast integer adder rather than a slow FP-aligned-add. The footnote in the contest doc spelled this out.

### 3.2 Matrix multiplication: many MACs

A matrix multiplication `C = A · B` for matrices of size `M×K` times `K×N` requires `M·N·K` scalar MACs. Each output element `C[i,j]` is a dot product of row `i` of `A` and column `j` of `B`.

In hardware, you build a **systolic array**: a 2D grid of MAC cells, each one streaming partial products and partial sums to its neighbors. NVIDIA's tensor cores, Google's TPU MXU, Etched's Sohu — they're all variations of this. A typical one has 256×256 = 65,536 MAC cells in a single block; multiple such blocks per chip; many chips per server.

**Each MAC cell contains an instance of our 74-gate multiplier.** Saving 11 gates × 65,536 cells = ~720,000 gates per block. At silicon-scale, that's real die area.

### 3.3 Why FP4 specifically for matmul?

Two reasons:
1. **Precision is enough.** Modern LLMs tolerate FP4 weights and FP4 activations during inference with negligible quality loss when paired with per-block (32-element) FP8 scaling. Pre-Blackwell hardware needed FP16 or FP8.
2. **Bandwidth and power scale with bit width.** A 4-bit value is half the bytes of FP8, a quarter of FP16. Memory bandwidth — the *real* bottleneck of LLM inference — improves linearly. So does power, which is dominated by data movement.

The flip side: you need a *very* good FP4 multiplier in silicon, because you'll have a million of them on a chip.

**Forward link →** Matmul is the heartbeat. Next: where it sits in a transformer.

---

## 4. From matmul to transformer inference

### 4.1 What a transformer does, in three lines

A transformer turns an input sequence (text tokens, image patches, audio frames) into an output sequence by applying a stack of identical "layers." Each layer is two sub-blocks:

1. **Attention** — every token looks at every other token, computes a similarity, weights them, and sums. Three matmuls per token (Q, K, V projections), one matmul to produce attention weights, one to combine.
2. **Feed-forward (FFN)** — a 2-layer fully-connected network applied independently to each token. Two big matmuls.

**Inference** = run the input through the layer stack, producing one output token at a time.

### 4.2 Where the FP4 matmuls are

In a Llama-70B-scale model (the standard reference for "big" inference workload):
- The attention QKV projection is a matmul of size `(seq_len × hidden_dim) × (hidden_dim × 3·hidden_dim)`. For Llama-70B with hidden_dim ≈ 8192, that's roughly 8192 × 24576 = 200M MACs *per token, per layer*.
- The FFN's two matmuls are even bigger: hidden_dim → 4·hidden_dim → hidden_dim. ~270M MACs per token per layer.
- 80 layers in the model.
- **≈ 38 billion MACs per token, per forward pass.**

If you serve 1000 tokens/second (modest throughput), that's 38 trillion MACs per second per query. In FP4, every one of those is an instance of our multiplier. Even at 1 GHz, you need 38,000 multipliers running in parallel just to keep up — hence the systolic array.

### 4.3 Where attention specifically is FP4

Sohu (Etched), Blackwell (NVIDIA's NVFP4), and AMD's MI400 all do FP4 *weights* with sometimes-higher activations during attention. Modern training runs (NVIDIA's NVFP4 paper from 2025) showed FP4 throughput training matching FP16 quality with FP4 *both* sides of the matmul. **This is the scenario our multiplier targets.**

### 4.4 The Sohu-class ASIC bet

A general-purpose GPU spends a *lot* of die area on flexibility: control logic, instruction decode, branch prediction, register files, generic caches. Estimates say only ~3–5% of an H100's transistors are *the multipliers themselves.*

A transformer-only ASIC (Sohu) goes the other direction: kill the flexibility, devote 50%+ of die to MAC cells. To do that, every MAC cell must be as small as possible — *which is why a 74-gate FP4 multiplier vs an 85-gate one matters.* Saving 11 gates × 100,000 cells × 8 chips per server × 1000 servers per pod is real silicon, real wafers, real CapEx.

**That's why this little contest matters for Longhorn Silicon.**

**Forward link →** Now you know why we care. Next: how we actually built the 74-gate version.

---

## 5. How we got from 390 to 70 gates

### 5.1 The naive approach (390 gates)

Take the 256-row truth table. Feed it to ABC's `read_pla; resyn2; resyn2; resyn2; map`. ABC builds a sum-of-products AIG, optimizes locally, technology-maps to {AND2, OR2, XOR2, NOT1}. **390 gates.** This is what you'd call "inflated" — the synthesizer started from the wrong abstraction level.

### 5.2 Behavioral Verilog (222 gates)

Wrote a `case`-statement Verilog that decodes each input to a signed 6-bit value, multiplies, shifts. yosys elaborates the case statements (turning them into a tiny ROM), runs ABC. **222 gates.** Better, because the synthesizer sees "lookup → multiply → shift" rather than 256 unrelated minterms.

### 5.3 Structural Verilog with sign-magnitude split (86 gates)

Wrote the multiplier as humans would: split the input into (sign, exponent, mantissa). Compute the magnitude path independently of the sign. At the end, conditionally negate. **86 gates** — a 2.6× reduction just from giving the synthesizer the right structural decomposition.

### 5.4 Input remap (85 gates)

The contest allows a free bijective renaming of the 4-bit input codes (applied identically to both ports). We searched 5040 sign-symmetric remaps. The winner: σ = (0,1,2,3,6,7,4,5), which moves the magnitudes 4 and 6 to "lower" code positions where the K-shift logic simplifies. **85 gates.** The XOR-decoded `el = a[1] XOR a[2]` is the trick that pays.

### 5.5 Raw-bit collapse (81 gates)

Algebraic identity: `a OR (a XOR b) = a OR b`. The leading-bit signal `lb = eh OR el` reduces from `a[2] OR (a[1] XOR a[2])` to `a[1] OR a[2]` — no XOR needed. Saved 4 gates by removing the decoder XOR from the leading-bit path. **81 gates.**

### 5.6 NAND-chain conditional negate (75 gates)

The standard way to negate a number in two's complement is: invert all bits, then add 1. The "+1" propagates through trailing zeros until it hits the first 1, flipping bits along the way. Most circuits implement this as a ripple-carry chain of half-adders.

**The mut2 trick:** rewrite the conditional negate as

> `y[i] = mag[i] XOR (sy AND ~below_i)` where `below_i = below_{i-1} AND ~mag[i-1]`

This is functionally identical to the standard form, but its AIG topology lets ABC find a much tighter circuit. **75 gates** — saved 6 gates with one Verilog rewrite.

### 5.7 Hardcoded Y[8] (74 gates)

The MSB of a 9-bit signed result is 1 iff the result is negative. A negative result means: signs differ AND magnitude ≠ 0. Magnitude ≠ 0 ⟺ both inputs are nonzero ⟺ (a[0] OR a[1] OR a[2]) AND (b[0] OR b[1] OR b[2]).

Express that directly in raw input bits and ABC saves one more gate by skipping the long below-chain reaching the sign output. **74 gates.**

### 5.8 eSLIM SAT-based windowed local improvement (70 gates)

ABC's `&deepsyn` is a heuristic optimizer — it converges to a deterministic local optimum (in our case, 74 gates). Re-feeding the 74-gate netlist back through ABC returns 74. **It's saturated.**

To go below 74, we used [eSLIM](https://github.com/fxreichl/eSLIM) (SAT 2024 paper by Reichl/Slivovsky), a fundamentally different optimizer. eSLIM does **SAT-proven windowed local improvement**: for every k-gate window in the circuit, it asks SAT "is there a smaller equivalent sub-circuit for this window?" — if yes, replaces. Iterates until no further improvement.

Critical configuration: `--syn-mode sat` (NOT `--aig`). AIG mode forces our 11 XOR2's to expand to 3 ANDs each (since AIG = AND/NOT only); after eSLIM compressed the AIG and ABC tried to remap back to {AND, OR, XOR, NOT}, the XOR patterns weren't fully recovered, giving 91–94 gates *worse* than 74. Non-AIG SAT mode preserves XOR2 as a basis primitive.

**Result: 70 gates** in 240 sec of SAT solver time on the 74-gate input.

### 5.9 The cell breakdown of the 70-gate result

| Cell type | Count |
|:---|---:|
| AND2 | 30 |
| OR2 | 10 |
| XOR2 | 21 |
| NOT1 | 9 |
| **Total** | **70** |

eSLIM's optimization significantly **rebalanced the cell mix** — 7 fewer ANDs, 8 fewer ORs, 10 *more* XORs. The SAT-proven local replacements found compact XOR-based sub-circuits that ABC's heuristic resub didn't see.

**Lesson transferable to other Longhorn Silicon blocks:** if your gate library has a native XOR (cost ~ AND), don't reduce to AIG before optimizing. Use XOR-aware tools (eSLIM SAT mode, mockturtle XAG, ABC `&fx`).

**Forward link →** That's the engineering. Next: how to actually use the design.

---

## 6. How to use what's in this repo

### 6.1 Files of interest

```
PRD.md — full design doc (research grounding, optimality argument, milestones)
SUMMARY.md — quick reference, "everything accomplished" summary
MEMORY.md — chronological journal across Claude sessions
INSTRUCTIONS.md — this file
current_best/
 ├── fp4_mul.v — Verilog source (mut11 form, ready to drop into a tape-out flow)
 ├── fp4_mul.blif — synthesized 74-gate netlist (BLIF format, 74 .subckt lines)
 ├── contest.lib — Liberty file, AND2/OR2/XOR2/NOT1 area=1 each
 ├── synth.ys — yosys synthesis script that produced the BLIF
 └── README.md — provenance + reproduction recipe
code/
 ├── fp4_spec.py — ground truth: input encoding + 256-pair reference truth table
 ├── verify.py — frozen evaluation harness (BLIF parser + simulator)
 ├── remap.py — sign-symmetric remap enumerator
 ├── gen_*.py — Verilog generators (per-remap structural / raw / mut2 / mut11)
 ├── synth_*.py — synthesis pipelines (PLA / Verilog / remap-aware)
 ├── search_*.py — multi-worker remap sweep drivers
 ├── fp4_mul_*.v — 18 hand-mutated Verilog formulations explored
 ├── cirbo_*.py — SAT-based exact synthesis experiments
 ├── strategy.py — autoresearch-style proposal file (agent-edited)
 ├── program.md — the human-edited "skill" spec for the autoresearch loop
 └── ...
results_*.tsv — experiment ledgers (~7000 rows total)
```

### 6.2 To reproduce the 74-gate result

```bash
cd "/Users/alanschwartz/Downloads/Projects/FP4 Mul"
python3 code/run_mutations.py fp4_mul_mut11.v
```

That re-synthesizes from the Verilog and prints `... gates=74 verify=OK`.

### 6.3 To verify the saved netlist

```bash
python3 code/verify.py current_best/fp4_mul.blif
```

(Internally hard-coded to use the σ=(0,1,2,3,6,7,4,5) remap; matches the saved netlist.)

### 6.4 To drop into your tape-out flow

The Verilog source is in `current_best/fp4_mul.v`. It's standard Verilog-2001, no system tasks, fully synthesizable. The module is `fp4_mul(a, b, y)` with `[3:0] a, b` and `[8:0] y`. Drop it into your block, instantiate one per MAC.

The Liberty file (`contest.lib`) is contest-specific (unit-cost AND2/OR2/XOR2/NOT1). For real silicon, you'll re-synthesize against your foundry standard cell library — yosys + your foundry's `*.lib` file — but the Verilog source structure is what matters.

### 6.5 To search for further reductions

```bash
# Wide remap sweep with mut11 form (5040 sign-symmetric perms × deepsyn-3s)
python3 code/search_mut11.py --n 5040 --top-k 50 --workers 4

# Cirbo SAT-based exact synthesis on small sub-blocks
python3 code/cirbo_subblocks.py 2x2 # proves 7 gates exact
python3 code/cirbo_subblocks.py k # K computation
python3 code/cirbo_subblocks.py shift # K-shift
```

---

## 7. The big picture (and what to ask Claude next)

1. **You now know what the multiplier does, where it sits in inference, and how the 70 gates were earned.** That's the engineering content of this project.

2. **The path lower than 74 likely needs SAT-based local improvement (eSLIM) or LLM-driven mutation search (AlphaEvolve loop with a frontier coder API).** Both are spawned as agents in this session — check `MEMORY.md` for the latest.

3. **For tape-out**, you have everything you need: a verified Verilog source, a synthesis script, a frozen test bench. Your real next steps are timing closure and place-and-route in your foundry's tools — outside the scope of this contest, well within Longhorn Silicon's mission.

4. **The transferable insights for your chip** beyond just-this-multiplier:
 - **Input remap** as a free degree of freedom: at every encoder/decoder interface in your dataflow, you can permute the wire ordering for free area savings. Don't waste this.
 - **NAND-chain "below" detector** for two's-complement conditional negation: the trick is general and saves gates whenever you have to negate a small magnitude.
 - **Sign-magnitude internal representation** when both operands have a sign-bit-as-MSB encoding: keep the magnitude path unsigned, defer the negation to the very end. Avoids carry propagation across the multiplier.
 - **Direct-route the most-significant output bit** when you can compute it independently of the magnitude shifter (Y[8] in our case). One free gate every time.

5. **Things to ask a frontier AI next when you want to push deeper:**
 - "What's the multiplicative complexity of an 8-input × 9-output Boolean function with this specific structure?" (theoretical lower bound)
 - "Synthesize an exact-minimum netlist using mockturtle's `xag_minmc_resynthesis`" (research-grade EPFL tool)
 - "Run an OpenEvolve loop with this verifier and the Anthropic API for 1000 mutations overnight" (closes the gap to AlphaEvolve)
 - "Re-do the synthesis with a Liberty file that prices the gates by your foundry's actual transistor counts" (the unit-cost contest result is a *proxy*; the real die savings depend on your foundry's transistor multipliers per cell type)

Now you're caught up. Let's keep pushing.
