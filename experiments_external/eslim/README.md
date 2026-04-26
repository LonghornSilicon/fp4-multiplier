# eSLIM Experiment — 70 Gates [best]

eSLIM ([SAT 2024 paper "eSLIM: Circuit Minimization with SAT-Based Local Improvement"](https://drops.dagstuhl.de/entities/document/10.4230/LIPIcs.SAT.2024.23) by Reichl/Slivovsky, [GitHub](https://github.com/fxreichl/eSLIM)) was run on our 74-gate ABC-deepsyn output and **reduced it to 70 gates verified-OK on all 256 input pairs.**

This is the canonical result. See `../../src/fp4_mul.blif` for the promoted version.

## Result

**70 gates** = 30 AND2 + 10 OR2 + 21 XOR2 + 9 NOT1.

## Why eSLIM beat ABC's `&deepsyn` here

ABC's `&deepsyn` is heuristic and converges to a deterministic local optimum (74 gates was a fixed point — we re-fed the BLIF back through and got 74 again).

eSLIM is fundamentally different: it does **SAT-proven local improvement on small windows**. For each window of size ≤ k gates, it asks SAT "is there a smaller equivalent sub-circuit?" — and if yes, replaces it. Iterates until no further improvement exists. This is exactly the "creative non-deterministic search" that breaks deterministic local optima.

## Critical configuration

The decisive choice was `--syn-mode sat` (and **NOT** `--aig`). Reasoning:

- AIG mode treats the netlist as AND/NOT only. Our 11 XOR2 gates must expand to 3 ANDs each, inflating the working AIG by ~22 nodes. eSLIM then does great work shrinking the AIG, but `dch -f; map -a -B 0` re-mapping back to {AND2, OR2, XOR2, NOT1} can't recover the XOR patterns and we lose the gain. AIG-mode runs gave 91–94 gates, worse than 74.
- SAT mode (non-AIG) preserves XOR2 as a primitive in the working representation. eSLIM's windowed SAT replacements then find improvements that respect the XOR-friendly cost.

## Build

```bash
git clone https://github.com/fxreichl/eSLIM.git /tmp/eSLIM
cd /tmp/eSLIM
pip install pybind11 bitarray
# macOS APFS hack: rename uppercase header-shadowing files in aiger/
for f in VERSION FORMAT LICENSE README TODO; do
 mv aiger/$f aiger/${f}.txt
done
# Build
cd src/bindings && cmake -B build && cmake --build build -j
```

## Run

```bash
# Convert our subckt-style BLIF to flat .names BLIF (eSLIM doesn't grok .subckt)
cd /tmp/eslim_work
python3 blif_to_aig.py fp4_mul.blif fp4_flat.blif
# Run eSLIM
PYTHONPATH=/tmp/eSLIM/src/bindings/build python3 /tmp/eSLIM/src/reduce.py \
 fp4_flat.blif fp4_reduced.blif 240 --syn-mode sat
# Translate eSLIM output back to {AND2, OR2, XOR2, NOT1} contest cells
python3 eslim_to_gates.py fp4_reduced.blif fp4_mul.blif
# Verify
cd "$REPO/lib" && python3 -c "
from verify import verify_blif
from remap import encoding_from_magnitude_perm
v = encoding_from_magnitude_perm((0,1,2,3,6,7,4,5))
ok, _ = verify_blif('../experiments_external/eslim/fp4_mul.blif', values=v)
print('verify:', 'OK' if ok else 'FAIL')
"
```

## Lesson learned

For our specific contest cost metric (XOR2 = 1 unit, same as AND2/OR2/NOT1), **non-AIG SAT-based windowed minimization beats heuristic AIG-based deepsyn** by ~5%. This generalizes: if your gate library has a primitive XOR (true for most ASICs at standard-cell level), don't reduce to AIG before optimizing.

## Files

- `fp4_mul.blif` — the 70-gate verified netlist (now also in `../../src/fp4_mul.blif`)
