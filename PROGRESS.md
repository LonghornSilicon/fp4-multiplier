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

Install the toolchain (`sudo apt-get install -y yosys cmake build-essential; pip3 install --user pybind11 bitarray cirbo; clone+build eSLIM`), run G5 (verify yosys+ABC reproduces 74 gates from `fp4_mul.v`), then G6 (run eSLIM `--syn-mode sat --size 8` once on the unperturbed 64-gate netlist to calibrate). **Confirm with user before any multi-hour eSLIM campaign** — that's the Phase 3 Experiment A trigger.

---

(no prior entries — this is the first PROGRESS.md write.)
