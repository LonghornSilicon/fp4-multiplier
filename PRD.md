# PRD: Etched FP4 Multiplier — Minimum-Gate Design

**Owner:** Alan Schwartz (Longhorn Silicon)
**Author of this doc:** Claude (in service of Alan's chip work)
**Status:** Draft v0 — **2026-04-25**, opening pass after problem digestion + literature scan
**Companion files:** `MEMORY.md` (chronological journal across sessions), `code/` (truth tables, synthesis pipeline, search infra)

---

## 1. Problem statement (verbatim, normalized)

Inputs: two 4-bit MX-FP4 (E2M1, no Inf/NaN, signed-zero ignored) values.
Default 4-bit codepoint table:
| code | val | code | val |
|------|-----|------|-----|
| 0000 | 0   | 1000 | 0    |
| 0001 | 0.5 | 1001 | -0.5 |
| 0010 | 1   | 1010 | -1   |
| 0011 | 1.5 | 1011 | -1.5 |
| 0100 | 2   | 1100 | -2   |
| 0101 | 3   | 1101 | -3   |
| 0110 | 4   | 1110 | -4   |
| 0111 | 6   | 1111 | -6   |

Output: 9-bit two's-complement integer **Y = 4 · val(a) · val(b)** (called QI9; the LSB equals 0.25 in the represented Q-value space, but the bit pattern is the integer 4·a·b directly). Range: −144 to +144 (fits 9-bit signed which is −256..+255).

Allowed gates (each costs 1, no other costs):
- AND2 (2-in)
- OR2 (2-in)
- XOR2 (2-in)
- NOT1 (1-in)

Free: constant 0/1 inputs to gates; arbitrary fan-out; one bijective remap of the 4-bit input space, applied identically to both ports.

Goal: **minimize total gate count + provide a strong argument for optimality.**

### Spec gotchas already resolved
- Spec example 2 in the take-home doc has at least two typos: "−3 represented as 0001" (should be 1101); output binary "110111000" should be "111101110" for 4·(−3·1.5)=−18. Confirmed by the only-9-bit-fitting-interpretation argument: if the output integer were 16·a·b instead of 4·a·b, max would be 16·36=576 > 255 — overflows 9-bit. (Canonical interpretation locked in `code/fp4_spec.py::qi9_encode`.)

---

## 2. Why this matters

This is not a take-home. It informs Alan's actual silicon (Longhorn Silicon tape-out). A gate count win on the FP4 multiplier scales by `N_macs · N_chips` — the per-MAC saving is multiplied by every multiplier instance in the dataflow + every parallel chip across a fab run. **Optimality, not just "good enough", is the target.**

---

## 3. Known facts grounding the approach (with citations)

### 3.1 Format facts
- MX-FP4 / E2M1: 1-sign + 2-exponent + 1-mantissa; subnormal at e=0 (val = 0.5·m). Source: [OCP MX v1.0 spec](https://www.opencompute.org/documents/ocp-microscaling-formats-mx-v1-0-spec-final-pdf), [arXiv 2310.10537](https://arxiv.org/abs/2310.10537).
- Magnitudes: 8 distinct values {0, 0.5, 1, 1.5, 2, 3, 4, 6}. After 4·a·b, the integer-output magnitudes form a 19-value set: {0, 1, 2, 3, 4, 6, 8, 9, 12, 16, 18, 24, 32, 36, 48, 64, 72, 96, 144}. Of these, only 9 has bit-1 set without bit-0 cleared trivially (9 = 1001).

### 3.2 Structural decomposition (E2M1 algebra)
Letting M_i = 2·(e_h_i ∨ e_l_i) + m_i ∈ {0,1,2,3} ("normalized mantissa with implicit leading bit") and shift_i = (e_h_i ? e_l_i : −1):
- 4 · val_a · val_b = M_a · M_b · 2^K, where K = shift_a + shift_b + 2 ∈ {0..4}
- M_a·M_b ∈ {0, 1, 2, 3, 4, 6, 9} (only seven distinct values)
- The output magnitude is therefore "small product, then shift left K" — looks like a 4-bit × 4-bit unsigned mult (in magnitude index space), but in fact much smaller because one operand is in {0..3} and the other in {0..3}.

### 3.3 Lower-bound levers
- **Multiplicative complexity:** any function on n=6 inputs needs ≥ 6 AND gates; for n=8, ≥ 8 ANDs is *not* a tight bound but a starting point. Every output bit that depends non-trivially on at least 2 inputs needs at least one gate. ([Multiplicative complexity 6-var](https://www.researchgate.net/publication/324183258); Knuth TAOCP V4 §7.1.2.)
- **Y[0] truth-count = 16 / 256.** Y[0] = 1 iff both inputs ∈ {±0.5, ±1.5} (proof: only those produce 0.25-, 0.75-, 2.25-magnitude products, which give odd 4·a·b). Under default encoding, Y[0] = (¬e_h_a ∧ m_a) ∧ (¬e_h_b ∧ m_b) — costs 4 gates; with a remap that makes "is half-integer-class" a single bit, it drops to **1 AND**.
- **Y[8] (sign):** truth-count exactly 7·7 + 7·7 = 98 (mixed-sign nonzero pairs). Y[8] = (s_a ⊕ s_b) ∧ (a≠0) ∧ (b≠0) under sign-MSB encoding. With sign-extension via two's-complement +1-carry (Baugh-Wooley), Y[8] folds into the magnitude carry chain — possibly free.
- **Trivial outputs:** for any encoding where 0 has a fixed code C, the row `a=C` and column `b=C` are all-zero output. This is automatically satisfied — but the cost of "zero handling" is what the 7-AND multiplicative-complexity bound is forcing us to pay.

### 3.4 Tooling we will use
- **ABC (`&deepsyn`, `&exact`, `dch`, `map -a`):** state-of-the-art logic synthesis. Our liberty file restricts the cell library to {AND2, OR2, XOR2, NOT1}, all area=1. ([ABC](http://people.eecs.berkeley.edu/~alanmi/abc/abc.htm); [TCAD 2020 SAT exact](https://people.eecs.berkeley.edu/~alanmi/publications/2020/tcad20_exact.pdf)).
- **Cirbo** (IWLS 2024 winner): SAT-based exact synthesis with a database of provably-optimal small (≤3-in × ≤3-out) circuits; supports n ≤ 10 with full SAT. Will use this on sub-blocks. ([arXiv 2412.14933](https://arxiv.org/abs/2412.14933); [GitHub](https://github.com/SPbSAT/cirbo).)
- **eSLIM** (SAT 2024) for SAT-based local-improvement on AIGs. ([SAT 2024](https://drops.dagstuhl.de/entities/document/10.4230/LIPIcs.SAT.2024.23).)
- **mockturtle** (EPFL) for exact_synthesis on small windows. ([GitHub](https://github.com/lsils/mockturtle), [arXiv 1805.05121](https://arxiv.org/abs/1805.05121).)
- **z3 / pysat** for hand-rolled SAT-based exhaustive search when sub-block sizes warrant it.
- **yosys** for read-write Verilog/BLIF and as a wrapper around the embedded ABC.

### 3.5 Why standard ML-accelerator wisdom does NOT apply directly
Most FP4 hardware papers (NVFP4, MXFP4, AxCore, Wonjun-Han DotProduct_FP4) don't publish gate-level minimum counts; they target throughput and silicon area at FinFET nodes. The closest result is [Hardware-Efficient 4-bit Multiplier](https://arxiv.org/abs/2510.21533) (4×4 unsigned, 11 LUT-6 + 2 CARRY4 on FPGA — not directly comparable). And [arXiv 2507.18179](https://arxiv.org/abs/2507.18179) shows ~50% transistor reduction in 4-bit multipliers when you encode internally as sign-magnitude — strong evidence for our remap strategy.

---

## 4. Approach — three concentric loops

### Loop 1 (innermost): single-encoding gate-min synthesis
Given a fixed input encoding (a list of 16 floats, one per 4-bit code), produce the minimum-gate netlist. Done by:
1. Emit per-output truth tables as a 9-output PLA / multi-output Boolean specification.
2. Pipeline: `read_pla → strash → &deepsyn(time-budgeted) → &put → mfs2 → dch → map -a` (ABC area-only mapping under our 4-cell library).
3. Optionally finish with `eSLIM` (SAT-based local improvement) or `Cirbo` exact-synthesis on small sub-windows.
4. Verify by formal equivalence checking (`cec`) against a Python truth-table reference.

Implementation: `code/synth.py::synthesize(values, abc_script, ...)`. Currently parametrized by the ABC script. Initial baseline (default encoding, fast script): **390 gates**; a fuller `&deepsyn -I 12 -T 240` baseline running now.

### Loop 2 (middle): remap search
The bijective remap π is a permutation of 16 codepoints (with the two zeros free to swap). Search space:
- Full bijection: 16! / 2 ≈ 1.05 × 10¹³ (the /2 is for the two zeros being interchangeable).
- Sign-MSB constraint (8 magnitudes mapped to s=0 codes, 7 negatives + one zero to s=1 codes — actually requires one zero per sign region by counting): 8! · 2 ≈ 80 640.
- Further symmetry: the function is symmetric in (a,b), so a remap with magnitude permutation σ on the s=0 region and the same σ on s=1 produces an equivalent circuit up to relabeling — so we can fix one magnitude (say "0 → code 000") wlog. → 7! · 2 = **10 080** sign-symmetric remaps.

Search strategy:
- **Cheap proxy first:** run `resyn2; map -a` (single-pass, ~1 sec / candidate) on each of the 10 080 sign-symmetric remaps. Total ~3 hours single-thread.
- **Strong synth on top-K:** for the top 100 candidates, run `&deepsyn -T 60`. ~2 hours.
- **Exhaustive synth on top-10:** `&deepsyn -T 600` + `eSLIM`. ~2 hours.
- Keep a `results.tsv` ledger.

This loop is embarrassingly parallel — would benefit from a multi-core machine. **Rough compute ask:** a 32-core CPU machine for ~24 hours would let us push the cheap-proxy out to non-sign-symmetric remaps too. **GPU is NOT useful** for symbolic logic synthesis (the SOTA tools are CPU-only, single-process or threaded). If Alan offers compute, prefer many CPU cores over GPU.

### Loop 3 (outermost): Karpathy-autoresearch agent loop
Following [karpathy/autoresearch](https://github.com/karpathy/autoresearch):
- **Single scalar metric:** total gate count (lower is better).
- **Fixed budget per experiment:** ABC `&deepsyn -T 60` per remap candidate (≈ 60 sec wall).
- **Frozen evaluation harness:** `code/fp4_spec.py::reference_truth_table` and `code/verify.py` (formal-equivalence check via z3). The agent is forbidden to touch these.
- **Edits one file:** `code/strategy.py` — proposes remaps and ABC script tweaks.
- **Git-as-ledger:** branch `autoresearch/fp4`, one commit per experiment, advance on improvement, `git reset --hard` on regression. Plus `results.tsv`.
- **`program.md`:** the agent's skill — describes the multiplier spec, the search space, the verification protocol, and the "modify → verify → keep/discard → repeat forever" rule.
- **Simplicity tiebreaker:** prefer designs with fewer levels (delay) or fewer wires when gate count ties.

---

## 5. Hand-derived "structural baseline" (with empirical results)

To verify any synthesis-tool output is in the right ballpark, we keep a hand-derived design as a reference. Sketch:

1. **Sign:** `s_y = s_a ⊕ s_b` — 1 gate. (Sign-MSB remap; produces correct value for two's complement after the magnitude path's +1 carry handles the −0 case automatically.)
2. **Leading-bit / "is-nonzero-class":** `lb_a = e_h_a ∨ e_l_a` (1 gate per side, 2 total). Combined with mantissa: `M_a ∈ {0,1,2,3}` is just (lb_a, m_a) as 2 bits.
3. **2×2 magnitude product** `(2·lb_a + m_a) · (2·lb_b + m_b)` (max 9, fits 4 bits). Folklore optimum: **7 gates** for the 2×2 unsigned mult.
4. **Variable left-shift by K = shift_a + shift_b + 2 ∈ {0..4}.** K depends on (e_h_a, e_l_a, e_h_b, e_l_b). A compact way: K = e_h_a + e_h_a·e_l_a + e_h_b + e_h_b·e_l_b. This is a 3-bit count. The shift takes a 4-bit value and produces an 8-bit value. Implementable as a 5-way mux on the 4-bit unshifted product.
5. **Two's-complement assembly:** XOR each magnitude bit with `s_y`, add `s_y` at the LSB (Baugh-Wooley-style — fold +1 into the multiplier carry chain so it costs ≤ 1 extra gate, not 8).

### Empirical results (default encoding only, 2026-04-25 session)

| starting Verilog        | ABC script         | gates | verified |
|-------------------------|---------------------|-------|----------|
| PLA (256 minterms)      | resyn2 ×3 + dch + map | 390   | ✓        |
| behavioural case-stmt   | yosys + ABC FAST   | 222   | ✓        |
| `fp4_mul_struct.v`      | FAST               | 93    | ✓        |
| `fp4_mul_struct.v`      | MED (resyn2 ×3)    | 92    | ✓        |
| `fp4_mul_struct.v`      | compress2x3        | 90    | ✓        |
| `fp4_mul_struct.v`      | **deepsyn-3s**     | **86**| ✓        |
| `fp4_mul_hand.v` (explicit shift exprs) | MED  | 88    | ✓        |
| `fp4_mul_bw.v` (explicit BW fold)       | FAST | 88    | ✓        |

### Empirical results with input remap (5040-perm wide sweep)

We swept all 5040 sign-symmetric remaps where `code 0 → magnitude 0` is fixed (which is sensible since both zeros must be placed somewhere), then ran deepsyn-3s on the top 30 by FAST gate count. **Four distinct remaps tied at 85 gates**:

| perm σ                  | values at codes 0..7              | gates |
|-------------------------|-----------------------------------|------:|
| (0,1,2,3,6,7,4,5)       | [0, 0.5, 1, 1.5, 4, 6, 2, 3]      | 85    |
| (0,1,6,7,2,3,4,5)       | [0, 0.5, 4, 6, 1, 1.5, 2, 3]      | 85    |
| (0,2,1,3,6,4,7,5)       | [0, 1, 0.5, 1.5, 4, 2, 6, 3]      | 85    |
| (0,2,6,4,1,3,7,5)       | [0, 1, 4, 2, 0.5, 1.5, 6, 3]      | 85    |
| (0,1,2,3,4,5,6,7) (default) | [0, 0.5, 1, 1.5, 2, 3, 4, 6]   | 86    |

The winning σ swaps the e_l interpretation in the e_h=1 region — equivalent to inserting `dec_el_internal = a[1] XOR a[2]` in front of the structural mul. Cell breakdown for σ=(0,1,2,3,6,7,4,5): **41 AND2 + 16 NOT1 + 10 OR2 + 10 XOR2 = 85 gates**. Saved to `current_best/fp4_mul.{v,blif}`.

### Per-output-bit AIG-node counts (no sharing)

Running ABC `&deepsyn -T 5 -I 6` on each of the 9 outputs independently:

| Y[0] | Y[1] | Y[2] | Y[3] | Y[4] | Y[5] | Y[6] | Y[7] | Y[8] | sum |
|-----:|-----:|-----:|-----:|-----:|-----:|-----:|-----:|-----:|----:|
| 3 | 22 | 35 | 44 | 33 | 32 | 23 | 17 | 9 | **218** |

Per-bit AIG-node sum = 218; full-circuit map = 85. So sharing across outputs recovers ~60% of the per-bit cost. Healthy.

### SAT-based exact synthesis (Cirbo)

Cirbo proved **Y[0] minimum = 4 gates** (basis {AND,OR,XOR,NOT}):
```
Y[0] = (m_a AND m_b) AND NOT(eh_a OR eh_b)
```
4 gates is also the AND-only AIG count (3) + 1 NOT, since OR(NOT) requires an explicit NOT.

Multi-output Cirbo search at G=84 is in progress (likely takes hours; SAT problem grows ~G·n_minterms·n_outputs in clauses).

Interesting null result: the *explicit* Baugh-Wooley fold made things worse with deepsyn (94 gates) — deepsyn rearranges from rigid hand structure into worse forms. ABC's optimizer already finds an equivalent BW-style fold from the simpler structural form. **Lesson: give synthesis the right *level* of structure (sign/mag split, 2×2 mul) but don't over-constrain low-level patterns.**

The lit review's 30–40-gate target appears optimistic for our exact gate set (AND2/OR2/XOR2/NOT1, unit-cost, 9-bit two's-comp output). Realistic range with our tooling is 80–90; reaching well below 80 likely requires hours-to-days of SAT solver time or a fundamentally cleverer hand decomposition.

---

## 6. Optimality argument — empirical findings

We attempted to prove a *gate-count lower bound* via SAT-based exact synthesis (Cirbo) and via per-output decomposition. Final state:

(a) **SAT-based per-output minimum (proven):** Cirbo CircuitFinderSat over our basis {AND2, OR2, XOR2, NOT1} on Y[0] (16 ones / 256) returned UNSAT for n ∈ {1,2,3} and SAT for n=4 in 1.6 sec total. Therefore **Y[0] minimum = 4 gates**, achieved by `Y[0] = (m_a AND m_b) AND NOT(eh_a OR eh_b)`. This is exactly the multiplicative complexity (3 AND-only AIG nodes) plus one NOT (since NOT(OR) needs an explicit NOT gate in our basis).

(b) **Multi-output Cirbo SAT — INFEASIBLE on our budget:** at G=84 (one below current best), Cirbo's SAT instance for the full 8-input × 9-output truth table did not return SAT or UNSAT in 5+ minutes (memory grew to ~2 GB). At G=10 (way below physical floor) the SAT solver still timed out at 70 s — the SAT problem is dominated by the 9 output constraints and the 256 minterms. SAT-based optimality proof would need days to weeks of compute; not pursued.

(c) **ABC `&deepsyn` saturation:** running deepsyn at -T 3, 10, 30, 60 s on the same Verilog returns 86, 86, 86, 86 (default) and 85 (best remap). Increasing time budget does NOT improve. Combined with the `compress2` and `resyn3` variants returning ≥ 86, this strongly suggests **85 is a robust local optimum for ABC's reachable structures**.

(d) **Random non-sign-symmetric remap fail:** 50 random bijective remaps that did NOT respect the sign-MSB convention all returned ≥ 140 gates. Confirms that sign-symmetric (sign in MSB, magnitudes permuted in lower 3 bits) is the right family.

(e) **Per-bit AIG-node sum (no sharing) = 218.** Our 85-gate solution shares ~60% — healthy but not extreme. Indicates substantial structure, but no single output dominates.

(f) **Information-theoretic floor:** output integer takes 73 distinct values; ⌈log₂(73)⌉ = 7 bits of entropy. The 9-bit output already meets this. Doesn't bound gate count usefully.

**Bottom line:** with the contest gate library {AND2, OR2, XOR2, NOT1} unit-cost, our **85-gate** netlist is the achievable minimum across:
- 5 040 distinct sign-symmetric input remaps,
- 9 ABC script variants (FAST/MED/STRONG, deepsyn at multiple time budgets, compress2, mfs2-iterations, dch flavors),
- 6 hand-mutated Verilog formulations (struct, hand-explicit-shift, BW-folded, hierarchical, signed-multiplier, mux-shifter),
- 50 random non-sign-symmetric remaps (all ≥ 140).

A provable lower bound below 85 is not in scope on a workstation budget. AlphaEvolve-style verifier-in-the-loop (per [DeepMind 2025](https://deepmind.google/blog/alphaevolve-a-gemini-powered-coding-agent-for-designing-advanced-algorithms/)) is the next escalation, but requires LLM-API budgets and many GPU-hours.

---

## 7. Compute requests (honest)

Alan offered GPU access. **Honest read:** the dominant tools (ABC, Cirbo, eSLIM, mockturtle) are CPU-only single- or few-threaded symbolic solvers. Useful compute:

- **YES:** 32–64 CPU cores. Enables parallel synthesis over the 10 k sign-symmetric remap space. ~24-hour single run.
- **YES:** RAM for SAT solvers. 32 GB suffices.
- **NICE-TO-HAVE:** 1–2 GPUs for AlphaEvolve-style verifier-in-the-loop (LLM proposes Verilog mutation → fast equivalence check → score → keep/discard, à la DeepMind's TPU multiply rewrite). This is the speculative-but-plausible upside.
- **NO BENEFIT:** GPU clusters for the inner SAT/synthesis. The bottleneck is symbolic, not numeric.

**Recommendation for now:** do not need extra compute for v0. Will request CPU cores once the autoresearch loop is up and we want to scale the remap search beyond sign-symmetric.

---

## 8. Milestones

- **M0 (today, 2026-04-25):** truth-table enumerator, synthesis pipeline, lit review, this PRD. **DONE.**
- **M1 (today/tomorrow):** strong synthesis on default encoding (`&deepsyn -T 240` baseline); hand-derived design coded as Verilog and synthesized; both gate counts logged.
- **M2:** sign-symmetric remap search (10 k candidates, ~1 sec each = ~3 CPU-hours single-thread; embarrassingly parallel). Ledger of best 100.
- **M3:** strong-synthesis pass on top 100; SAT-based lower bound on top 10.
- **M4:** Karpathy autoresearch loop running overnight on a chosen remap; LLM-proposed Verilog mutations.
- **M5:** final design + optimality writeup + correctness proof (Python equivalence check + ABC `cec`).

---

## 9. Files / artifacts (current)

```
code/
  fp4_spec.py          # ground-truth truth-table generator + spec
  fp4_mul.v            # behavioral Verilog reference (default encoding)
  contest.lib          # ABC liberty: AND2/OR2/XOR2/NOT1, area=1 each
  abc.rc               # ABC alias definitions (resyn2, etc.)
  synth.py             # PLA → ABC pipeline (parametrized by encoding + script)
  synth_baseline.ys    # yosys script (Verilog → ABC mapping baseline)
  run_deepsyn.py       # one-shot strong synthesis runner
PRD.md                 # this file
MEMORY.md              # chronological journal across sessions
Etched Take-Home Multiplier Assignment - Campus Tours.{pdf,md}  # the problem
```

Pending: `verify.py` (formal-equiv check), `search.py` (remap search driver), `program.md` (autoresearch agent skill), `results.tsv` (ledger).

---

## 10. Risks / known gotchas

- **Spec example 2 typo:** confirmed. Don't use as a test vector.
- **PLA-form synthesis is bad starting point:** ABC's `read_pla` builds an SOP-style AIG that resyn2 doesn't fully recover from. Verilog → yosys → ABC sometimes gives better results than PLA → ABC, depending on whether the hand-Verilog exposes structure. (See current 222 gates from yosys vs 390 from PLA at the same fast script.) Mitigation: run both starting points for each candidate.
- **Liberty-file warnings** ("buffer gate not detected"): harmless; ABC falls back to non-supergate mapping. No correctness impact.
- **Too-aggressive optimizers may produce non-functionally-equivalent netlists in pathological cases.** Always verify with `cec` against the Python reference.

---

## 11. Open questions to resolve in next session

1. What is `&deepsyn -T 240` baseline for default encoding? (Running now in background.)
2. Does the sign-symmetric remap space really collapse to 10 k? (Need to enumerate carefully and verify equivalence under symmetry.)
3. Is exact-synthesis on the magnitude sub-block (6-in × 8-out) tractable in <1 hour? (If yes, that pins a lower bound on the whole circuit's magnitude path.)
4. Confirm: under the standard sign-magnitude internal representation, can the +1 carry of two's-complement negation be folded into the magnitude multiplier without growing the AIG? (Baugh-Wooley says yes for unsigned-times-unsigned with TC inputs; we have something different but likely analogous.)
