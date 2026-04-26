# Autoresearch Skill — FP4 Multiplier Minimum-Gate Search

> This file is a **skill** (per Karpathy autoresearch convention). It tells the
> AI agent how to run the inner research loop. The HUMAN iterates on this file;
> the AGENT iterates on `code/strategy.py`.

## Mission

Find the minimum-gate-count netlist for the Etched FP4 (E2M1) multiplier whose
output is the 9-bit two's-complement integer `4 · val(a) · val(b)`. Allowed
gates: AND2, OR2, XOR2, NOT1 (each cost 1). Constants free. One bijective input
remap (same on both ports) free.

## What you can edit

- **`code/strategy.py`** — your only mutable file. Define `propose()` which
  returns a list of `(name, values, abc_script)` candidates. Each candidate is
  one synthesis experiment.
- **NOTHING ELSE.** The verifier (`verify.py`), spec (`fp4_spec.py`), search
  driver (`search.py`), liberty file (`contest.lib`), and ABC alias file
  (`abc.rc`) are FROZEN. If you think any of them is wrong, write a note in
  `MEMORY.md` and STOP — do not modify them.

## The metric

Single scalar: total gate count of the synthesized netlist that passes
`verify_blif`. **Lower is better.** Tiebreaker (only when gate counts equal):
fewer logic levels, then fewer wires.

## The fixed budget

Each experiment runs ABC for at most **60 seconds** of wall-clock. If your ABC
script takes longer, the search driver kills the run and records a `timeout`.
This is the integrity barrier — don't try to circumvent it.

## The loop (run forever until human interrupts)

```
LOOP FOREVER:
  1. Read MEMORY.md and `results.tsv` to see what's been tried.
  2. Look at the top-K best results so far. What patterns work?
  3. Propose 1–10 new candidates by editing `strategy.py::propose()`.
     Candidates are (name, values, abc_script) tuples.
  4. Run: `python3 code/search.py --candidates from-strategy`
  5. Read the new rows in `results.tsv`. Did any beat the prior best?
  6. If yes: git commit `strategy.py` + `results.tsv`. Update MEMORY.md.
  7. If no: git reset --hard the strategy file. Try a different idea.
  8. Repeat.
```

**NEVER STOP.** Do not pause to ask the human if you should continue. The loop
is autonomous. The loop runs until the human interrupts you, period.

## Crash policy

- Trivial bug (typo, syntax error in strategy.py): fix it inline, re-run.
- Conceptually broken idea (synthesizer rejects, verifier fails): record as
  `crash` in `results.tsv`, revert that experiment, move on.
- ABC takes >2× budget (>120s): kill, record `timeout`, move on.
- Verifier mismatch on the synthesized BLIF: record `WRONG` in `results.tsv`.
  This is a HARD FAIL — do not advance even if gate count is lower.

## Things to try (start here, then improvise)

1. **Sign-symmetric magnitude permutations.** 40320 of them. Try the obvious:
   identity, reversed, Gray-code ordered, "magnitude-as-binary" (where bits map
   directly to numerical magnitude bits).
2. **Stronger ABC scripts.** `&deepsyn -T 30 -I 8` is a solid default; try
   `-I 16`, longer `-T`, multiple `&deepsyn` invocations interleaved with
   `mfs2`, `dch -f`, etc.
3. **Non-sign-symmetric remaps.** A remap where the sign bit isn't the MSB
   may save gates by encoding "is nonzero" or "is half-integer" cleanly.
4. **Two-stage synthesis.** First synthesize the magnitude path (3-in × 3-in →
   8-out subblock), then bolt on the sign + zero handling.
5. **Cirbo / eSLIM.** When a strong ABC result is in hand, try to further
   optimize via SAT-based local improvement.

## Simplicity tiebreaker

A 1-gate improvement that adds 50 lines of strategy code is worse than a
0-gate improvement that DELETES 50 lines of strategy code. Prefer cleaner
strategy code at equal score.

## What to write to MEMORY.md when you stop (if interrupted by the human)

- Last-tried candidate batch + their scores.
- Best result so far (gate count + the (name, values, abc_script) triple).
- Hypotheses you formed that didn't pan out.
- Hypotheses you formed that DID pan out.
- Next-action when resumed.
