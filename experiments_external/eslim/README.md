# eSLIM Experiment — 65 Gates [best]

eSLIM ([SAT 2024 paper "eSLIM: Circuit Minimization with SAT-Based Local Improvement"](https://drops.dagstuhl.de/entities/document/10.4230/LIPIcs.SAT.2024.23) by Reichl/Slivovsky, [GitHub](https://github.com/fxreichl/eSLIM)) was run **iteratively** on our ABC-deepsyn output. Two passes: first reduced 74 -> 70 with default `--size 6` windows; second pass reduced 70 -> **65** with `--size 8` windows. Verified-OK on all 256 input pairs.

This is the canonical result. See `../../src/fp4_mul.blif` for the promoted version. Prior 70-gate snapshot preserved at `fp4_mul_70gate.blif`.

## Result

**65 gates** = 25 AND2 + 12 OR2 + 21 XOR2 + 7 NOT1.

Two independent eSLIM runs from the 70-gate input converged on 65 contest cells with slightly different cell mixes:
- `--syn-mode sat` (default size 6) for 1200s: 26 AND, 11 OR, 21 XOR, 7 NOT
- `--syn-mode sat --size 8` for 900s: 25 AND, 12 OR, 21 XOR, 7 NOT [promoted]

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
# Stage the starting BLIF (use the .gate or .subckt form; flattener handles both)
cd /tmp/eslim_work
python3 blif_flatten.py fp4_mul.blif fp4_flat.blif

# Pass 1: 74-gate -> 70 gates (default size 6, ~240s)
PYTHONPATH=/tmp/eSLIM/src/bindings/build python3 /tmp/eSLIM/src/reduce.py \
  fp4_flat.blif fp4_pass1.blif 240 --syn-mode sat

# Pass 2: 70-gate -> 65 gates (size 8, ~900s)
python3 blif_flatten.py fp4_pass1_gates.blif fp4_pass1_flat.blif
PYTHONPATH=/tmp/eSLIM/src/bindings/build python3 /tmp/eSLIM/src/reduce.py \
  fp4_pass1_flat.blif fp4_pass2.blif 900 --syn-mode sat --size 8

# Translate eSLIM internal back to {AND2, OR2, XOR2, NOT1}
python3 eslim_to_gates.py fp4_pass2.blif fp4_mul.blif

# Verify
cd "$REPO/lib" && python3 -c "
from verify import verify_blif
from remap import encoding_from_magnitude_perm
v = encoding_from_magnitude_perm((0,1,2,3,6,7,4,5))
ok, _ = verify_blif('../experiments_external/eslim/fp4_mul.blif', values=v)
print('verify:', 'OK' if ok else 'FAIL')
"
```

## Lessons learned

1. For our specific contest cost metric (XOR2 = 1 unit, same as AND2/OR2/NOT1), **non-AIG SAT-based windowed minimization beats heuristic AIG-based deepsyn** by ~5% per pass. Generalizes: if your gate library has a primitive XOR (true for most ASICs at standard-cell level), don't reduce to AIG before optimizing.

2. **Iterating eSLIM with progressively larger windows compounds gains.** Pass 1 with default size 6 took 74 -> 70. Pass 2 with size 8 on the 70-gate output took it to 65. Each pass exposes structures the previous pass couldn't see at its window size. The trade-off: window size 8 costs roughly 4-5x more SAT solver time per query than size 6, but the larger window can prove non-local replacements.

3. **Starting topology matters.** When eSLIM was applied to a 67-gate intermediate, it stayed at 67-68. Applied directly to the 70-gate it found 65. The 70-gate input had structural slack the 67-gate (which was also a result of eSLIM compression) had already eaten.

## Files

- `fp4_mul.blif` — the 65-gate verified netlist (now also in `../../src/fp4_mul.blif`)
- `fp4_mul_70gate.blif` — prior 70-gate snapshot (preserved for reference)
