# DECISIONS

Architectural / technical choices and their rationale. Most recent first.

---

## 2026-04-28 — Pivot from 81-gate independent line to optimizing Longhorn 64-gate

**Chose:** Stop optimizing our own 81-gate v4f netlist. Pivot to studying and trying to push below the public 64-gate LonghornSilicon solution.

**Rejected:** Continuing simulated annealing / 3-perturbation random search on the 81-gate netlist.

**Why:** We exhaustively scanned all 4489 depth-2 perturbation pairs and 67×100 single perturbations from 81; all returned no improvement. The decomposition itself (`1.5^M × 2^E` with one-hot S decoder) puts us 17 gates above where Longhorn's `(2·lb + ma) × 2^class` decomposition reaches naturally. Local optimization can't recover that gap. User confirmation: "scrap what we have been doing, let's turn our focus to the 64 gates and work on optimizing it."

---

## 2026-04-28 — Use cheap preemptive tests to gate every long compute

**Chose:** Phase 0 triage gates G1–G4 (pure Python over bitvectors, ~30 min total). Then Phase 1 install + G5/G6 quick checks (~30 min). Multi-hour eSLIM campaigns only happen if those gates greenlight.

**Rejected:** Going straight from "install eSLIM" to "run 600+ configurations overnight."

**Why:** User explicit constraint: "I want to do full pipeline but it takes so long, can we run premeptive test to see if its a direction worth pursuing?" Each preemptive test is cheap and falsifies the next compute step before we spend hours on it. The triage gates are designed so that ANY hit immediately yields a 63-gate result without needing the toolchain at all.

---

## 2026-04-28 — Run optimization first, write explainer in parallel

**Chose:** Lead with the optimization campaign. The deep explainer (`LONGHORN_DEEP_EXPLAINER.md`) is written concurrently while eSLIM jobs run in background.

**Rejected:** Write explainer first → user verifies understanding → then start optimization.

**Why:** User chose this directly via AskUserQuestion. Concrete progress signals are more valuable to the user than a long writeup; they want optimization momentum. eSLIM single-thread runs don't compete with markdown writing CPU.

---

## 2026-04-28 — Keep `autoresearch/multiplier.py` as the safe submission

**Chose:** Don't overwrite our 81-gate v4f file. Any new Longhorn-derived solution lands in a separate file (e.g., `longhorn_64.py` or a new `multiplier_v5.py`) and is only promoted to `multiplier.py` after passing both `eval_circuit.py` AND `etched_take_home_multiplier_assignment.py`.

**Rejected:** Immediately replace `multiplier.py` with the 64-gate body.

**Why:** Rollback safety. The 81-gate solution is guaranteed correct on our harness; the Longhorn body uses a different INPUT_REMAP and was developed against their harness, not the official Etched notebook. Verify end-to-end before swapping.

---

## 2026-04-28 — Reproduce the 64-gate baseline locally instead of skipping straight to perturbation experiments

**Chose:** Phase 2 reproduces the full yosys + ABC + eSLIM trajectory from their `fp4_mul.v` source. Costs ~2 hours of single-thread compute.

**Rejected:** Take their `colab_paste.py` body as ground truth and only run experiments on top of it.

**Why:** We need to confirm our local toolchain produces the same 64-gate result they did. If our yosys/ABC/eSLIM versions diverge, we'd waste compute on Experiment A perturbations that can't be valid on a different baseline. Reproduction is the calibration step.

---

## 2026-04-28 — Use eSLIM `--syn-mode sat`, NOT `--aig`

**Chose:** All eSLIM runs use `--syn-mode sat` per Longhorn's experiment_external/eslim/README.

**Rejected:** AIG mode (the eSLIM default in some examples).

**Why:** AIG mode forces our 21 XOR2 gates to expand to 3 ANDs each (~63 extra AIG nodes). After eSLIM compresses the AIG, the post-synthesis re-mapping back to {AND2, OR2, XOR2, NOT1} can't recover XOR-friendly patterns → Longhorn's AIG-mode runs gave 91-94 gates vs SAT-mode's 70. Documented in `experiments_external/eslim/README.md` "Critical configuration" section.

---

## 2026-04-28 — Skip yosys / Phase 2 reproduction; go straight to Experiment A on canonical BLIF

**Chose:** Use Longhorn's `fp4_mul.blif` (64 contest cells) directly as the starting point for Experiment A perturbations. Don't reproduce the 74-gate yosys+ABC baseline first.

**Rejected:** Install yosys + ABC, run `yosys synth.ys` to regenerate 74 gates, then walk the entire eSLIM trajectory (74 → 70 → 65 → 64) from scratch.

**Why:** yosys requires sudo apt install (user offered to run sudo but it's a dependency we'd block on). The reproduction is a calibration step — not strictly required for the perturbation campaign. We'd burn ~2 hours of compute reaching exactly the 64-gate netlist Longhorn already published. By starting from the canonical BLIF, we save those 2 hours and immediately attack the new question (can we push 64 → 63 via gate-neutral perturbation, untried at this depth).

**Trade-off:** if our local eSLIM build behaves differently than Longhorn's, we wouldn't know. Mitigation: G6 preemptive eSLIM run on the canonical BLIF returned 64 contest cells — same as Longhorn. So our toolchain is calibrated.

---

## 2026-04-28 — Use pip with `--break-system-packages` instead of venv

**Chose:** `pip3 install --user --break-system-packages pybind11 bitarray cirbo cmake`.

**Rejected:** Set up a venv (`python3 -m venv` needs python3-venv apt package, requires sudo); use the existing `.venv/` (broken — missing pip).

**Why:** WSL is a research environment, not production. The system Python isn't at risk for a few extra `--user` site-packages installs. Avoids sudo, avoids fixing the broken existing venv, avoids `pipx` overhead.

---

## 2026-04-28 — Track contest cells, not eSLIM internal gates

**Chose:** The "official" gate count for our purposes is the count after `eslim_to_gates.py` translation (the contest cell count). All comparisons in `exp_a_ledger.tsv` use this number.

**Rejected:** Use eSLIM's "internal gate count" as the metric. Tempting because eSLIM logs it directly.

**Why:** eSLIM's internal representation includes compound primitives (NAND, NOR, XNOR, ANDN_A = `~A & B`, ANDN_B = `A & ~B`) that count as 1 internal gate but expand to 2 contest cells (1 AND/OR/XOR + 1 NOT). Empirical observation from first 4 Experiment A runs: 58 internal gates can produce contest counts of 64, 65, or 66 depending on seed. The contest count is what wins the assignment, not the internal count.

---

## 2026-04-28 — Parallelize eSLIM sweep with multiprocessing.Pool

**Chose:** Run 8 eSLIM workers concurrently via `concurrent.futures.ProcessPoolExecutor`. System has 12 cores; reserved 4 for the OS / Cirbo / Claude Code itself.

**Rejected:** Stick with sequential single-process driver.

**Why:** eSLIM is single-threaded (verified via `top` — one process at 100% CPU). 144 runs sequentially would take ~3 hours; parallel with 8 workers takes ~22 min. Same results, 8x throughput. The sweep was burning compute that could be parallel.

---

## 2026-04-28 — Cirbo cone runs need don't-care support; defer until that's solved

**Chose:** Note the don't-care issue in Experiment B's small cones (B.1, B.2, B.3); don't trust those UNSAT results. B.4 (all minterms reachable from primary inputs) is valid.

**Rejected:** Trust Cirbo's UNSAT results on cones with reachable subset of minterms.

**Why:** When sub-cone inputs are derived from earlier wires, only some minterm patterns are reachable. The current `bv_to_truth_rows` fills unreachable minterms with False, over-constraining the function. Cirbo TruthTableModel doesn't support don't-cares directly. To fix: either restrict to reachable minterms (need n-input function on m≤2^n combinations — Cirbo can't do that natively), or try multiple don't-care fills, or use Cirbo's relation-based search if available. Punt for now.

---

## 2026-04-28 — Save full session context across multiple files (CONTEXT.md, PROGRESS.md, DECISIONS.md)

**Chose:** Three separate handoff files, each with a single purpose. Memory entries also saved in `~/.claude/projects/.../memory/`.

**Rejected:** One giant catch-all file.

**Why:** User explicit request. CONTEXT.md is the resume-here; PROGRESS.md is the running log; DECISIONS.md is the architecture-decisions ledger. Separation makes each file maintainable and skimmable.
