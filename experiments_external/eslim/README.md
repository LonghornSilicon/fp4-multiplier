# eSLIM Experiment

eSLIM (SAT 2024 paper "eSLIM: Circuit Minimization with SAT-Based Local Improvement"
by Reichl/Slivovsky) was run on our 74-gate AIG with a 600-second budget.

**Result:** 100 gates after re-mapping back to {AND2, OR2, XOR2, NOT1}.

## Why worse than 74?

eSLIM operates on AIG (no native XOR2). Our 74-gate netlist has 11 XOR2's,
each of which expands to ~3 ANDs in AIG. eSLIM tried to compress the 176-AND
input AIG to 168 ANDs, but ABC's `dch -f` couldn't fully recover the XOR
patterns when re-mapping to our 4-cell library.

## Files (if present)

- `fp4_reduced.aig`: eSLIM's optimized AIG output
- `blif_to_aig.py`: utility to convert our BLIF to AIG for eSLIM input

## Lesson

SAT-based local-improvement on AIG is the wrong basis for our problem because
our cell library natively supports XOR2 (cost 1). Tools that work on XAG
(XOR-AIG) like mockturtle are a closer fit, but mockturtle also gave 75-78
on this particular benchmark.
