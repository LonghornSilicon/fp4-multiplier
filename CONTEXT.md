# CONTEXT

This is a session-handoff document. **A new conversation reads this first** to know exactly where to resume.

---

## What we're building

Etched / Longhorn Silicon take-home: a minimum-gate FP4×FP4 → 9-bit two's complement multiplier. Inputs are two 4-bit FP4 (E2M1) values; output is `int(round(4·a·b))`. Gate library: `{AND2, OR2, XOR2, NOT1}`, each = 1 unit. The 16→16 input remap is free.

**Verifier**: `python3 eval_circuit.py autoresearch/multiplier.py` — runs the candidate over all 256 input pairs.

## Current state (gate counts)

| Track | Best | File | Status |
|---|---|---|---|
| Our independent line | **81** | `autoresearch/multiplier.py` (v4f) | Saturated under all gate-level search |
| LonghornSilicon public | **64** | `longhorn_verify.py` (verified locally 256/256) | Saturated under their eSLIM campaign (~70% they think it's global min) |

**Decision (this session, 2026-04-28):** scrap further work on the 81-gate line; pivot to optimizing the 64-gate Longhorn solution and trying to push it to 63.

## What we did this session

1. Wrote `LONGHORN_STRATEGY.md` (top-level explainer of how Longhorn reached 64).
2. Cloned Longhorn repo into `/tmp/longhorn/fp4-multiplier/`. Read README, SUMMARY, MEMORY, INSTRUCTIONS, src/, mutations/.
3. `longhorn_verify.py` paste-verifies their 64-gate body at 64 gates, 256/256 against our `eval_circuit` harness.
4. Three Explore agents and one Plan agent produced detailed analyses (problem deep dive, netlist gate-by-gate analysis, local toolchain survey). Findings are folded into the plan at `/home/abhiclaude/.claude/plans/ok-i-did-and-zesty-unicorn.md`.
5. **Phase 0 triage gates G1–G4 all ran. ALL returned NO HIT** — confirms the 64-gate netlist is fully saturated under depth-1 substitution + DCE at the bitvector level. See `triage/g1_g3_g4_64gate.py`, `triage/g4_dce_aware.py`, `triage/g2_not65_cone.py` for the actual checks.

Key triage results:
- **G1** (duplicate bitvectors): no two wires share a truth table.
- **G3** (output mux algebra): `AND(w_24, w_52) == w_70` (a topology rewrite, but neither w_24 nor w_52 can be DCE'd).
- **G4** (depth-2 pair resub): 111 candidate substitutions, but DCE-aware pass found zero net reductions.
- **G2** (not_65 cone brute force): minimum is 3 gates, matching the current count.

## Where we are when this session paused

Phase 0 + Phase 1 + G6 preemptive done. Confirmed:
- 64-gate netlist saturated under depth-1 substitution + DCE (Phase 0).
- eSLIM tooling builds and runs (Phase 1: pybind11 + bitarray + cirbo + cmake all via pip; eSLIM compiled at /tmp/eSLIM/src/bindings/build).
- G6 preemptive: eSLIM `--syn-mode sat --size 6` for 20s on the unperturbed 64-gate BLIF returns 64 contest cells (matches Longhorn's reported saturation).

**Phase 2 (yosys + ABC reproduction) skipped intentionally** — we don't need yosys to start Experiment A; eSLIM consumes BLIF directly and we have Longhorn's canonical `fp4_mul.blif`.

## EXACT next step

Resume by reading this file + `PROGRESS.md` + `DECISIONS.md`, then:

**Experiment A — gate-neutral XOR re-association on the canonical 64-gate BLIF.**

1. Enumerate XOR-of-XOR locations in `/tmp/longhorn/fp4-multiplier/src/fp4_mul.blif`. Candidates spotted: `w_25 = XOR(w_42, w_45=XOR(w_65, w_43))`, `w_15 = XOR(w_37, w_25=XOR)`, `w_55 = XOR(w_40=XOR, w_53)`, `w_58 = XOR(w_48=XOR, w_21=XOR)`, `w_21 = XOR(w_25=XOR, w_73)`, `w_26 = XOR(w_37, w_58=XOR)`. Several more once you walk the netlist programmatically.
2. For each XOR-of-XOR location: rewrite `XOR(XOR(a,b),c)` → `XOR(a, XOR(b,c))` (algebraically identical, structurally different). Generate a perturbed BLIF.
3. Flatten each perturbed BLIF via `/tmp/longhorn/fp4-multiplier/experiments_external/eslim/scripts/blif_to_aig.py`.
4. Run eSLIM with 3 sizes (6, 8, 10) × 4 seeds for ~5 min each.
5. Translate output back to contest cells via `eslim_to_gates.py` and count. Any variant landing below 64 = WIN; verify functionally and commit.

```bash
# Working directory layout
/tmp/eslim_work/                    # scratch dir (already exists)
/tmp/longhorn/fp4-multiplier/...    # reference repo
$REPO/experiments/exp_a_xor_reassoc.py  # NEW driver script (TODO write)

# Single eSLIM run pattern (already verified to work):
PYTHONPATH=/tmp/eSLIM/src/bindings/build \
  python3 /tmp/eSLIM/src/reduce.py \
  /tmp/eslim_work/INPUT.blif /tmp/eslim_work/OUT.blif 300 \
  --syn-mode sat --size 8 --seed 7777
```

Time budget: 1 variant × 1 seed × `--size 6` = 20 sec; full sweep of ~10 variants × 4 seeds × 3 sizes ≈ 1 hour total. **Stop and confirm with user before launching the wider campaign if first 5 variants find nothing.**

## Blockers / watch-outs

- **eSLIM build needs `pybind11-dev` headers and may need `apt install python3-dev`** if the bindings link fails. (Should already be installed; verify.)
- **eSLIM runs single-threaded.** Multi-hour budgets can't be parallelized on one laptop. Honest expectation: matching Longhorn's 600+ configs is infeasible locally.
- **The user explicitly wants a preemptive test before any long compute.** Always gate Phase 3 experiments behind their corresponding G6/G7/G8/G9.
- **Don't touch `autoresearch/multiplier.py`** (the 81-gate v4f safe submission) until any new Longhorn-derived solution is fully verified end-to-end.
- The user has GitHub auth set up via `credential.helper store` (this session). Don't re-prompt them.

## Key file paths

| File | Purpose |
|---|---|
| `autoresearch/multiplier.py` | Our 81-gate v4f safe submission. Don't break. |
| `longhorn_verify.py` | Longhorn's 64-gate body, paste-verified through `eval_circuit`. |
| `LONGHORN_STRATEGY.md` | Existing top-level strategy explainer (read first). |
| `LONGHORN_DEEP_EXPLAINER.md` | Pedagogical deep-dive (PLANNED, not yet written — Phase 4). |
| `triage/g1_g3_g4_64gate.py` | Phase 0 triage gates G1, G3, G4. |
| `triage/g4_dce_aware.py` | Phase 0 G4 with DCE post-pass. |
| `triage/g2_not65_cone.py` | Phase 0 G2 brute force. |
| `sa_search.py` | Bit-parallel simulator (used by triage scripts). |
| `sa_resub.py` | Care-set resub that found 81-gate v4f from 82. |
| `eval_circuit.py` | The frozen evaluation harness. |
| `etched_take_home_multiplier_assignment.py` | The official assignment harness. |
| `/tmp/longhorn/fp4-multiplier/` | Cloned reference repo. |
| `/tmp/longhorn/fp4-multiplier/src/fp4_mul.{v,blif,py}` | Their canonical 64-gate sources. |
| `/tmp/longhorn/fp4-multiplier/lib/cirbo_subblocks.py` | Cirbo SAT template for Experiment C. |
| `/tmp/longhorn/fp4-multiplier/experiments_external/eslim/README.md` | eSLIM build + commands. |
| `/home/abhiclaude/.claude/plans/ok-i-did-and-zesty-unicorn.md` | Approved plan (Phase 0–5). |

## Memory files (auto-loaded)

`/home/abhiclaude/.claude/projects/-mnt-c-Users-themo-Desktop-Etched-Multiplier-Assignment/memory/`:
- `MEMORY.md` (index)
- `project_goal.md`
- `project_state.md`
- `longhorn_strategy.md`
- `own_search_history.md`
- `eslim_reference.md`
- `user_role.md`

## Recent commits (master, in chronological order)

```
ce7c782 Add LonghornSilicon 64-gate strategy explainer + local verification
6e39771 Snapshot search infrastructure before pivot to LonghornSilicon approach
1f1272d Reduce gate count 82->81 via care-set resubstitution (v4f)
d485439 Research Checkpoint
```

The triage scripts (`triage/*.py`) are uncommitted at session pause — commit them in the next session along with a Phase 0 result note.
