# 74-gate canonical (prior best)

Achieved by `mut11` Verilog form + ABC `&deepsyn -T 3 -I 4`. **74 gates** verified.

Cell breakdown: 37 AND2 + 18 OR2 + 11 XOR2 + 8 NOT1 = 74.

This was the canonical answer before eSLIM's 70-gate result superseded it.
Files preserved here for reference and reproducibility.

See `experiments_external/eslim/` for the result that beat it (70 gates).
