# Etched Submission — Colab Paste Blocks

This directory holds the two cells you paste into Etched's Colab test notebook
(https://colab.research.google.com/drive/1wzVixtYtFbxafuuih49Lif2twmWzYDNC) to
verify the 64-gate solution.

**Verified:** 256/256 input pairs pass the notebook's official assertion loop
(2026-04-28). The `-0.0` vs `0.0` lines printed by the notebook are cosmetic —
both encode to the same QI9 bitstring `0b000000000` and the assertion compares
QI9 ints, not float strings.

## File

- [`colab_paste.py`](./colab_paste.py) — both paste blocks, clearly delimited
  with `# PASTE-IN BLOCK 1` and `# PASTE-IN BLOCK 2` headers

## How to paste

**Block 1 (lines 7–24 of `colab_paste.py`):** replaces the `INPUT_REMAP = { ... }`
dict in the notebook's "Example remapping" cell. Leave everything above it
(the `pip install`, imports, and the `NOT/OR/AND/XOR` lambdas) untouched.

**Block 2 (lines 32–105 of `colab_paste.py`):** replaces the entire
`def write_your_multiplier_here(...)` placeholder in the next cell — from `def`
through the closing `return`.

Then run the test cell at the bottom. All 256 assertions pass silently.

## Sanity check (optional)

If the test fails on `0.5 * 2`, the new `INPUT_REMAP` dict didn't take effect.
Add a fresh cell with:

```python
print(INPUT_REMAP[float4_e2m1fn(2.0)])
```

If it prints `6` → new remap is live. If it prints `4` → re-run the
`INPUT_REMAP` cell so it actually re-defines the dict.

## Source of truth

These blocks are auto-generated from the canonical netlist at
[`../src/fp4_mul.blif`](../src/fp4_mul.blif) — a topo-sorted 1:1 translation
into Python AND/OR/XOR/NOT calls. The Verilog source is at
[`../src/fp4_mul.v`](../src/fp4_mul.v).
