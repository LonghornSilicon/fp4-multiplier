# PROGRESS LOG

Append-only running log of work sessions on the FP4 multiplier project. Most recent first.

---

## 2026-04-28 (afternoon → evening) — Pivot to LonghornSilicon 64-gate approach

**Session summary**

We hit a hard plateau at 81 gates on our independent line (gate-level SA, resub, depth-2 pair search all saturated; sub-64 not reachable from this decomposition). User pointed at https://github.com/LonghornSilicon/fp4-multiplier (public 64-gate solution) and asked to (a) understand it deeply and (b) try to push it below 64.

**What was accomplished**

- Cloned Longhorn repo, read README/SUMMARY/MEMORY/INSTRUCTIONS/src/mutations end-to-end (~10k lines of docs).
- Wrote `LONGHORN_STRATEGY.md` (top-level pedagogical explainer of the four key differences: decomposition, σ remap, eSLIM, gate-neutral XOR re-association).
- Wrote `longhorn_verify.py` — paste of their 64-gate body wired to our `eval_circuit` harness. **Verified: 64 gates, 256/256 correct.**
- Saved 6 memory entries so a fresh conversation has full context (`/home/abhiclaude/.claude/projects/.../memory/`).
- Committed and pushed everything to `origin/master` on GitHub.
- Designed a sub-64 optimization plan with cheap-first triage gates before any multi-hour compute. Plan approved by user; saved at `/home/abhiclaude/.claude/plans/ok-i-did-and-zesty-unicorn.md`.
- Ran **Phase 0 triage gates G1–G4** (no installs, pure Python over the 256-input bitvector domain):
  - **G1**: no duplicate truth tables among the 64 wires. eSLIM-level saturation confirmed.
  - **G2**: brute force on the not_65 cone (`{w_43, w_58, w_65} → {y0, w_69}`). Minimum is 3 gates, matching current. No 2-gate alternative exists.
  - **G3**: `AND(w_24, w_52) == w_70` is a topology rewrite but neither input can be DCE'd; no gate saved.
  - **G4**: 111 candidate single-gate substitutions found by bitvector match; DCE-aware pass found zero net reductions.
- All four gates returned **NO HIT** — the 64-gate netlist is fully saturated under depth-1 substitution + DCE at the bitvector level.

**What was NOT finished**

- **Phase 1 toolchain install** — yosys, cmake, eSLIM build, cirbo. Skipped this session because user wanted to pause and write context-handoff docs.
- **Phase 2** — reproduce the 64-gate baseline locally via yosys + ABC + eSLIM.
- **Phase 3** — Experiments A–E (gate-neutral perturbations on 64, Cirbo on subblocks, etc.).
- **Phase 4** — `LONGHORN_DEEP_EXPLAINER.md` (the pedagogical deep dive the user asked for). Still on the todo list.
- **Triage scripts not committed** — `triage/g1_g3_g4_64gate.py`, `triage/g4_dce_aware.py`, `triage/g2_not65_cone.py`. Commit them next session.

**Single most important thing to do next**

Run Experiment A: enumerate gate-neutral XOR re-associations on the canonical 64-gate BLIF, run eSLIM on each with multiple seeds, look for any variant that drops below 64 contest cells.

**Updates after CONTEXT.md write-out (still 2026-04-28):**
- Phase 1 install: pybind11, bitarray, cirbo via pip `--break-system-packages`. cmake via pip. eSLIM cloned + built (`/tmp/eSLIM/src/bindings/build/*.so`). All bindings import cleanly. **yosys / system-cmake skipped — eSLIM consumes BLIF directly, no yosys needed for the Experiment A path.**
- G6 preemptive eSLIM run on canonical 64-gate flat BLIF: **eSLIM `--syn-mode sat --size 6` for 20s returns 58 internal gates → 64 contest cells (25 AND2 + 12 OR2 + 21 XOR2 + 6 NOT1)**. Confirms Longhorn's published saturation at the unperturbed 64-gate netlist. No immediate sub-64 hit.
- Next concrete step: write `experiments/exp_a_xor_reassoc.py` that enumerates XOR(XOR(a,b),c) → XOR(a,XOR(b,c)) variants on `/tmp/longhorn/fp4-multiplier/src/fp4_mul.blif`, runs eSLIM with 3 sizes × 4 seeds × N variants. Budget ~30 min for first sweep.

**Updates while Experiment A runs (still 2026-04-28):**
- `experiments_eslim/exp_a_xor_reassoc.py` written and running in background (PID tracked). Sweep config: 12 XOR-of-XOR variants × 2 sizes (6, 8) × 4 seeds × 60s budget = ~24 min wall time.
- Ledger: `experiments_eslim/exp_a_ledger.tsv` (tab-separated, append-only).
- **Early observation (first 4 runs on loc#0):** eSLIM produces 58 internal gates consistently, but contest cell count after `eslim_to_gates.py` translation varies 64–66 across seeds. The *internal* count is invariant; the *contest* count depends on how many compound gates (NAND, NOR, XNOR, ANDN_A, ANDN_B) get expanded to AND+NOT pairs. Hypothesis: a sub-64 contest result requires eSLIM to land in a low-compound-gate basin where ≤5 NOTs are needed.
- `LONGHORN_DEEP_EXPLAINER.md` written in parallel (~430 lines): line-by-line walk-through of 64-gate body, decomposition derivation, lower-bound table, verification recipes.
- **PARALLELIZATION:** killed sequential sweep, rewrote as `experiments_eslim/exp_a_parallel.py` with multiprocessing.Pool (8 workers; system has 12 cores). New sweep config: 12 variants × 2 sizes × 6 seeds = 144 runs, ~18 min wall time. Pushed to GitHub.
- **Verifier:** `experiments_eslim/blif_verify.py` parses any .gate-form BLIF, topo-sorts, builds a Python multiplier function, runs through `eval_circuit.evaluate_fast` on the σ remap. Smoke-tested on canonical: 64 cells, 256/256 correct. Ready for any sub-64 candidate that comes back.
- **Experiment B launched concurrently:** `experiments_eslim/exp_b_cirbo_cones.py` runs Cirbo SAT on small sub-cones. B.1/B.2/B.3 ran in seconds (small cones). B.4 (all 6 NOTs from raw a,b inputs → 6 NOT outputs) running, walks G upward UNSAT G=1..9 so far. **Caveat: don't-care handling — bv_to_truth_rows fills unreachable minterms with False, which over-constrains. Reachable-only sub-cone results may be misleading. B.4 has all 256 minterms reachable so its results are valid.**
- **Sweep progress at 5 min:** 30/144 runs done, contest cells range {64, 65, 66, 67}, no sub-64 seen yet. ~13 more minutes for full sweep.
- **Sweep progress at 10 min (~63/144):** still no sub-64. Wrote `experiments_eslim/analyze_results.py` to scan all `par_*_gates.blif` outputs for cell breakdowns + NOT counts.

**🎯 BREAKTHROUGH (2026-04-28, ~10 min into sweep):**
Analyzer flagged `par_004_s6_seed7777_gates.blif` as a **5-NOT 64-gate solution**. Cell breakdown:
```
NOT1: 5  (vs canonical 6)
AND2: 24 (vs canonical 25)
OR2:  12 (matches)
XOR2: 23 (vs canonical 21)
Total: 64
```
This contradicts Longhorn's "all 124 known 64-gate solutions have 6 NOTs" empirical invariant. The eSLIM landed in a basin trading 1 NOT + 1 AND for 2 XORs. **NOT YET VERIFIED** — `blif_verify.py` is broken on the `.names X Y\n1 1` BUF aliases that `eslim_to_gates.py` emits in this output. Needs ~10 min fix to parse BUFs.

This 5-NOT BLIF is a high-value seed for Round 2 perturbation:
1. Verify correctness (extend blif_verify.py).
2. Use as seed for `exp_a2_pair_perturb.py` (paired XOR re-associations).
3. If a 5-NOT 64-gate variant exists, a 4-NOT might too — and a 4-NOT solution could plausibly compress to 63 cells via further inverter-sharing.

**Single most important thing to do next** (revised): fix `blif_verify.py` to handle `.names BUF` lines, verify `par_004_s6_seed7777_gates.blif` is 256/256 correct, then perturb it for Round 2.

**ROUND 1 FINAL (2026-04-28, 22.75 min wall):**
- 144 jobs, 100 BLIFs translated (44 size=8 timeouts at 60s budget — known issue).
- Cell counts: 64 (×20), 65 (×49), 66 (×22), 67 (×7), 68 (×2).
- NOT distribution: 5 (×1), 6 (×46), 7 (×38), 8 (×13), 9 (×2).
- **No sub-64.** **One 5-NOT 64-gate variant** verified (commit `0edda3d`).

**ROUND 2 LAUNCHED:** seeded from `experiments_eslim/fp4_64gate_5NOT_clean.blif`, 192 jobs × 4 workers = ~72 min wall. Ledger: `experiments_eslim/exp_a_round2_ledger.tsv`. In flight.

---

(no prior entries — this is the first PROGRESS.md write.)
