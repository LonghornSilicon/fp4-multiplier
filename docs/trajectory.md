# Trajectory: 390 → 70 Gates

A round-by-round log of what each step did, why it worked, and how big the win was. Useful as a reference for the same kind of optimization on other Longhorn Silicon blocks.

## Round 0 — Baseline (390 gates)

**What:** Read the 256-row truth table as a PLA into ABC, run `strash; resyn2; resyn2; resyn2; dch -f; map -a -B 0`.

**Result: 390 gates.**

**Why bad:** Flat truth-table SOP is the worst possible starting AIG. ABC builds a sum-of-minterms representation (~256 wide AND-OR), and `resyn2` can only locally rewrite — it can't recover the natural arithmetic structure.

**Lesson:** Never `read_pla` if you can write structural Verilog instead.

## Round 1 — Behavioral case-stmt Verilog (222 gates)

**What:** Wrote a behavioral Verilog with `case (a)` and `case (b)` statements decoding each FP4 code to its signed integer value × 4, then `xa * xb >>> 2` for the multiply-and-scale. Ran through yosys + ABC.

**Result: 222 gates.**

**Why better:** yosys's `proc; opt; memory; opt; flatten; opt -full; techmap; opt` pipeline elaborates the case statements (lifting them to memory cells then back to logic), gives ABC a structured starting AIG.

**Caveat:** yosys turning case statements into `$mem` cells temporarily is a quirk; you must include the `memory; opt;` pass or the BLIF backend rejects the design.

## Round 2 — Structural Verilog with sign-magnitude split (86 gates)

**What:** Hand-decomposed the multiplier into:
- Decode field bits: sign, e_h, e_l, m
- 2×2 mantissa product P = M_a × M_b where M_i = (lb_i, m_i), lb_i = e_h_i | e_l_i
- K = sa1 + sb1 where sa1 = e_h × (1 + e_l)
- mag = P << K (8-bit unsigned magnitude)
- Sign-magnitude → two's complement via `(mag XOR rep(sy)) + sy`

**Result: 86 gates.**

**Why much better (–136 gates):** Gave ABC the right-level structure to optimize. The signed-multiplier expansion in Round 1 hid the natural arithmetic decomposition.

**Lesson:** Most of the gain came from ONE design decision (sign-magnitude split). Future rules of thumb: always split sign-magnitude paths in Verilog; let synthesizer share the magnitude path with conditional negate.

## Round 3 — Best input remap (85 gates)

**What:** Searched 5040 sign-symmetric remap permutations σ on the 8 magnitudes (with mag-0 fixed at code 0). Best: σ = (0,1,2,3,6,7,4,5), giving values [0, 0.5, 1, 1.5, 4, 6, 2, 3] at codes 0..7.

**Result: 85 gates.**

**Why better (-1 gate):** Under this remap, the decoded `el = a[1] XOR a[2]` (it's an XOR of two raw bits), so `lb = eh | el = a[2] | (a[1]^a[2])` — and crucially, `a OR (a XOR b) = a OR b` is an algebraic identity, so `lb = a[1] | a[2]` (no XOR needed).

**Caveat:** The XOR savings only manifested when the Verilog formulation used the explicit `el = a[1]^a[2]` intermediate signal. ABC didn't auto-discover the `a | (a^b) = a|b` identity from the underlying truth table — it required hand-coded Verilog to expose.

## Round 4 — Raw-bit `lb` collapse (81 gates)

**What:** Wrote `code/fp4_mul_raw.v` with `lb_a = a[1] | a[2]` directly (not via `eh | el`). The XOR for `el` is still computed because it's needed for K bits, but `lb` no longer goes through the XOR.

**Result: 81 gates.**

**Why much better (-4 gates):** The leading-bit OR-with-XOR-input was costing 4 gates total in mismatched gate-mapping; pre-collapsing in source code gave ABC the simpler form to work with.

**Lesson:** Algebraic identities at the source level matter. ABC's local rewrite rules don't always find these.

## Round 5 — mut2 NAND-chain conditional negate (75 gates)

**What:** Replaced the standard `(mag XOR rep(sy)) + sy` 2's-comp negate (which compiles into a +1 ripple-carry chain of 8 half-adders) with the equivalent expression:

```
y[i] = mag[i] XOR (sy AND ~below_i)
where below_i = below_{i-1} AND ~mag[i-1]
```

**Result: 75 gates.**

**Why much better (-6 gates):** Functionally identical to the +1 carry chain, but the AIG topology is fundamentally different. The NAND-chain "below_i = ~mag below" is amenable to ABC's resub/dch passes in a way that the half-adder ripple isn't. ABC found a tighter joint optimization with the magnitude-product side.

**Lesson:** Two equivalent expressions can give very different gate counts after synthesis. The NAND-chain "below" form is a transferable trick for any conditional 2's-comp negation in your circuits.

## Round 6 — Direct-route Y[8] (74 gates)

**What:** Hardcoded the sign output:

```
y[8] = sy AND (a[0] | a[1] | a[2]) AND (b[0] | b[1] | b[2])
```

This is literally "result is negative iff signs differ AND both inputs are nonzero." Bypasses the `~below_8` chain reaching the MSB.

**Result: 74 gates.**

**Why marginal-but-real (-1 gate):** ABC was building Y[8] off the long below-chain. Hardcoding it lets ABC skip one level of the chain for that bit.

**Lesson:** When an output bit has a clean expression in raw input bits (independent of internal magnitude state), hardcode it. Don't trust the synthesizer to factor it out.

## What we tried and didn't beat 74

- **Hardcoding Y[7]** (mag[7]=1 ⟺ both inputs ±6): 81 gates, worse — disconnects from shared structure.
- **1-hot K indicators** instead of `mag = P << K`: 90 gates, much worse.
- **Signed-multiplier formulations**: 211 gates, terrible.
- **Running-OR in conditional negate** instead of NAND-chain: 79–85 gates, worse.
- **Stronger ABC scripts**: deepsyn -T 60, T 120, T 600; compress2x3; iter-deepsyn; mfs2 -W 6 -F 3 -D 2 — all return 74 or timeout.
- **eSLIM** SAT-based local improvement on the 74-gate AIG: 100 gates after re-mapping (XOR2 expansion in AIG defeats eSLIM here).
- **mockturtle XAG resynthesis**: 75 gates after re-mapping; close but 1 over.
- **Random non-sign-symmetric remaps**: ≥ 140 gates (sign-symmetry strictly preferred).
- **5040 + 2000 + 1000 sign-symmetric remap sweeps** with the mut11 form: 74 floor across all.

## Saturated fixed-point at 74

Re-feeding the 74-gate BLIF through `read_blif → resyn → deepsyn → mfs2 → dch → map` returns 74. **It is a deterministic local optimum** for ABC's heuristic optimizer.

## Round 7 — eSLIM SAT-based windowed local improvement (70 gates) ⭐

**What:** Built [eSLIM](https://github.com/fxreichl/eSLIM) (SAT 2024 paper "eSLIM: Circuit Minimization with SAT-Based Local Improvement" by Reichl/Slivovsky) from source on macOS arm64. Ran on the 74-gate netlist with `--syn-mode sat` for 240 seconds. Translated the output back from eSLIM's basis (which includes "AND with one negated input" gates) to our contest 4-cell library by emitting shared NOT1 gates.

**Result: 70 gates.** Cell breakdown: 30 AND2 + 10 OR2 + 21 XOR2 + 9 NOT1.

**Why much better (-4 gates):** ABC's `&deepsyn` is a heuristic that converges to a deterministic local optimum (74 in our case). eSLIM is fundamentally different — it does SAT-proven local improvement on small windows, asking "is there a smaller equivalent sub-circuit for this k-gate window?" If yes, replaces. Iterates. The replacements are *provably* minimal at the window level, which lets it escape ABC's local optimum.

**Critical config — non-AIG mode:** Tested both `--aig` and `--syn-mode sat`. AIG mode forced our 11 XOR2 gates to expand to 3 ANDs each (since AIG is AND/NOT only); after eSLIM compressed the AIG and ABC tried to remap back to {AND, OR, XOR, NOT}, the XOR patterns weren't fully recovered. Result: 91–94 gates, *worse* than 74. Non-AIG SAT mode preserves XOR2 as a basis primitive and is the right choice when your cost metric counts XOR2 = 1 unit.

**Lesson (transferable to Longhorn Silicon):** Don't reduce to AIG before optimizing if your standard cell library has a native XOR2 (cost ≈ AND2). AIG-based tools (basic ABC modes, AIG-only mockturtle, eSLIM `--aig`) give worse results. Use XOR-aware modes: eSLIM `--syn-mode sat`, mockturtle XAG, ABC's `&fx` factoring extraction.

## Saturated fixed-point at 70

Re-running eSLIM on the 70-gate netlist with another 240s budget gives 70 (no further improvement on this window size). Going below 70 likely requires:
- Larger window size in eSLIM (k=4 → k=5 or 6, with much longer SAT solver time)
- Multi-day Cirbo SAT for a global proof
- A novel structural insight at the Verilog level

That said: 70 gates is a 5.6× reduction from the naïve baseline and a 17.6% improvement over the published-style 85-gate result. Solid stopping point.
