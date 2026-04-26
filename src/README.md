# Canonical FP4 Multiplier — 74 Gates

Best verified FP4 multiplier netlist found so far. Verified correct on all 256 input pairs.

## Result

| Metric | Value |
|---|---|
| **Total gate count** | **74** |
| AND2 | 37 |
| OR2  | 18 |
| XOR2 | 11 |
| NOT1 | 8 |
| Verified on all 256 input pairs | ✅ |
| Synthesis flow | yosys 0.64 → ABC `&deepsyn -T 3 -I 4` |
| Wall time | ~13 sec |

## Trajectory (this session)

| Stage | Gates | Win |
|---|---:|---|
| PLA + ABC FAST | 390 | — |
| Behavioral Verilog (case-stmt) | 222 | yosys structural elaboration |
| Structural Verilog (default encoding) + deepsyn-3s | 86 | sign-mag split exposed to ABC |
| Structural + best remap σ + deepsyn-3s | 85 | XOR-decoded el reduces decoder |
| Raw-bit Verilog (lb collapsed) | 81 | algebraic identity `a\|(a^b)=a\|b` |
| mut2 (NAND-chain "below" detector) | 75 | replaces +1 carry chain |
| **mut11 (mut2 + raw P_nonzero for Y[8])** | **74** | bypasses long below-chain for sign-bit |

5.3× reduction from naïve PLA baseline; **13.5% reduction over the 85-gate prior result.**

## Input Remap σ = (0,1,2,3,6,7,4,5)

Applied identically to both ports. Sign symmetric (sign at MSB):

| 4-bit code | value | | 4-bit code | value |
|:---:|:---:|---|:---:|:---:|
| 0000 | +0   | | 1000 | -0   |
| 0001 | +0.5 | | 1001 | -0.5 |
| 0010 | +1   | | 1010 | -1   |
| 0011 | +1.5 | | 1011 | -1.5 |
| 0100 | +4   | | 1100 | -4   |
| 0101 | +6   | | 1101 | -6   |
| 0110 | +2   | | 1110 | -2   |
| 0111 | +3   | | 1111 | -3   |

Two distinct sign-symmetric remaps tie at 74 with mut11 form.

## Key design tricks

1. **Sign-magnitude internal representation** (sign at MSB, raw magnitude path)
2. **Input remap σ** — XOR-decoded `el = a[1] XOR a[2]` lets `lb = a[1] | a[2]` (no decoder XOR for the leading-bit OR; saved by algebraic identity `a OR (a XOR b) = a OR b`)
3. **2×2 mantissa multiplier** — provably optimal at 7 gates (Cirbo SAT-confirmed: G=6 UNSAT, G=7 SAT)
4. **Variable shift** — `mag = P << K`, K ∈ {0..4}, where K = sa1 + sb1 with sa1, sb1 ∈ {0,1,2}
5. **mut2 NAND-chain conditional negate** — `below_i = below_{i-1} & ~mag[i-1]`, then `y[i] = mag[i] XOR (sy & ~below_i)`. Replaces standard 2's-comp +1 ripple-carry. **Saved 6 gates** vs `xord + sy`.
6. **mut11 raw-bit Y[8] route** — `y[8] = sy & (a[0]\|a[1]\|a[2]) & (b[0]\|b[1]\|b[2])` directly from inputs. Avoids the long below-chain reaching y[8]. **Saved 1 more gate.**

## Files

- `fp4_mul.v` — Verilog source (mut11 form)
- `fp4_mul.blif` — synthesized BLIF (74 cells, contest gate library)
- `contest.lib` — Liberty: AND2/OR2/XOR2/NOT1 area=1
- `synth.ys` — yosys synthesis script

## Reproduction

```bash
cd "/Users/alanschwartz/Downloads/Projects/FP4 Mul"
python3 code/run_mutations.py fp4_mul_mut11.v
```

Should output `fp4_mul_mut11.v   deepsyn-3   74   ~13s  OK`.
