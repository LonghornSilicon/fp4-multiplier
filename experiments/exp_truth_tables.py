"""
Generate truth tables for all FP4 sub-functions and export in PLA format.

Functions exported:
  tt_full_8in9out.pla   — full signed circuit (8 inputs → 9 outputs)
  tt_mag_6in8out.pla    — magnitude only (a1..a3, b1..b3 → m0..m7)
  tt_sdec_3in7out.pla   — S decoder (s0,s1,s2 → sh0..sh6)
  tt_esumdec_4in7out.pla — E-sum + S decoder (a2,a3,b2,b3 → sh0..sh6)
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from eval_circuit import FP4_TABLE

OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                   "experiments", "data")
os.makedirs(OUT, exist_ok=True)

# ── Helper: write PLA file ─────────────────────────────────────────────────────
def write_pla(path, n_in, n_out, rows):
    """rows: list of (input_int, output_int) pairs (both as integers)"""
    with open(path, "w") as f:
        f.write(f".i {n_in}\n.o {n_out}\n.p {len(rows)}\n")
        for inp, out in rows:
            ibits = "".join(str((inp >> (n_in-1-k)) & 1) for k in range(n_in))
            obits = "".join(str((out >> (n_out-1-k)) & 1) for k in range(n_out))
            f.write(f"{ibits} {obits}\n")
        f.write(".e\n")
    print(f"  Wrote {path} ({len(rows)} rows)")

# ── Remapping (v4c encoding) ───────────────────────────────────────────────────
_mag_to_code = {
    0.0: 0b000, 1.5: 0b001, 3.0: 0b010, 6.0: 0b011,
    0.5: 0b100, 1.0: 0b101, 2.0: 0b110, 4.0: 0b111,
}
REMAP = []
for _v in FP4_TABLE:
    _sign = 1 if _v < 0 else 0
    REMAP.append((_sign << 3) | _mag_to_code[abs(_v)])

# ── 1. Full signed circuit: 8-in 9-out ────────────────────────────────────────
def build_full_tt():
    """All 256 FP4×FP4 pairs → 9-bit QI9 (bit 0 = MSB = sign)"""
    rows = []
    for a_orig in range(16):
        for b_orig in range(16):
            a_code = REMAP[a_orig]
            b_code = REMAP[b_orig]
            a_val = FP4_TABLE[a_orig]
            b_val = FP4_TABLE[b_orig]
            qi9 = int(round(a_val * b_val * 4))
            qi9_9bit = qi9 & 0x1FF
            # encode: bit0=MSB (sign), bit8=LSB
            # PLA output: bit 0 of PLA word = res0 (MSB of QI9) ... bit 8 = res8 (LSB)
            inp = (a_code << 4) | b_code
            out = qi9_9bit  # 9 bits, bit 8 = sign (MSB), bit 0 = LSB
            # Reverse: PLA output bit 0 = res0 (sign/MSB of QI9) = bit 8 of qi9_9bit
            pla_out = 0
            for bit in range(9):
                pla_out = (pla_out << 1) | ((qi9_9bit >> (8 - bit)) & 1)
            rows.append((inp, pla_out))
    # Remove duplicate rows (same input → same output, no ambiguity)
    rows_dedup = list(dict.fromkeys(rows))
    write_pla(os.path.join(OUT, "tt_full_8in9out.pla"), 8, 9, rows_dedup)

# ── 2. Magnitude circuit: 6-in 8-out ──────────────────────────────────────────
def build_mag_tt():
    """
    Inputs: a1 a2 a3 b1 b2 b3 (6 bits)
    Outputs: m7 m6 m5 m4 m3 m2 m1 m0 (8 bits, m7=MSB)

    The magnitude is the absolute value of the product × 4, as an 8-bit integer.
    When either input is zero (code 000), output is 0.
    """
    rows = []
    seen = {}
    for a_orig in range(16):
        for b_orig in range(16):
            a_code = REMAP[a_orig]
            b_code = REMAP[b_orig]
            a_mag3 = a_code & 0x7  # a1 a2 a3
            b_mag3 = b_code & 0x7  # b1 b2 b3
            inp = (a_mag3 << 3) | b_mag3

            a_val = abs(FP4_TABLE[a_orig])
            b_val = abs(FP4_TABLE[b_orig])
            mag = int(round(a_val * b_val * 4))  # 0..144, fits in 8 bits
            assert 0 <= mag <= 255

            if inp in seen:
                assert seen[inp] == mag, f"Conflict for input {inp:06b}: {seen[inp]} vs {mag}"
            seen[inp] = mag

    for inp, out in sorted(seen.items()):
        rows.append((inp, out))
    write_pla(os.path.join(OUT, "tt_mag_6in8out.pla"), 6, 8, rows)

    # Print the distinct non-zero output patterns
    nonzero = sorted(set(v for v in seen.values() if v > 0))
    print(f"  Distinct non-zero magnitude values: {len(nonzero)}: {[hex(v) for v in nonzero]}")

# ── 3. S decoder: 3-in 7-out ──────────────────────────────────────────────────
def build_sdec_tt():
    """
    Inputs: s2 s1 s0 (3 bits, S = 4*s2 + 2*s1 + s0, range 0..6)
    Outputs: sh0 sh1 sh2 sh3 sh4 sh5 sh6 (one-hot, sh_j=1 iff S=j)

    S=7 is impossible (because max E'=3+3=6), so that input combination gives 0.
    """
    rows = []
    for s in range(8):
        inp = s  # s2=bit2, s1=bit1, s0=bit0
        if s <= 6:
            out = 1 << (6 - s)  # sh0=bit6, sh6=bit0
        else:
            out = 0  # don't-care input (S=7 impossible)
        rows.append((inp, out))
    write_pla(os.path.join(OUT, "tt_sdec_3in7out.pla"), 3, 7, rows)

# ── 4. E-sum + S decoder: 4-in 7-out ──────────────────────────────────────────
def build_esumdec_tt():
    """
    Inputs: a2 a3 b2 b3 (4 bits)
    Outputs: sh0..sh6 (one-hot encoding of S = (a2,a3)_bin + (b2,b3)_bin)

    S = 2*a2 + a3 + 2*b2 + b3, range 0..6.
    Currently implemented in 7+13=20 gates.
    """
    rows = []
    for a2 in range(2):
        for a3 in range(2):
            for b2 in range(2):
                for b3 in range(2):
                    s = 2*a2 + a3 + 2*b2 + b3  # S value, 0..6
                    inp = (a2 << 3) | (a3 << 2) | (b2 << 1) | b3
                    out = 1 << (6 - s)  # sh0=bit6 of out
                    rows.append((inp, out))
    rows.sort()
    write_pla(os.path.join(OUT, "tt_esumdec_4in7out.pla"), 4, 7, rows)
    print(f"  E-sum+decoder: S range 0..6 (max sum = 2+1+2+1=6, confirmed)")

# ── 5. Per-bit factored analysis ───────────────────────────────────────────────
def analyze_mag_bits():
    """Print how many 1-minterms each magnitude output bit has."""
    seen = {}
    for a_orig in range(16):
        for b_orig in range(16):
            a_code = REMAP[a_orig]
            b_code = REMAP[b_orig]
            a_mag3 = a_code & 0x7
            b_mag3 = b_code & 0x7
            inp = (a_mag3 << 3) | b_mag3
            a_val = abs(FP4_TABLE[a_orig])
            b_val = abs(FP4_TABLE[b_orig])
            mag = int(round(a_val * b_val * 4))
            seen[inp] = mag

    print("\nMagnitude bit analysis (6-in 8-out):")
    for bit in range(7, -1, -1):
        ones = [inp for inp, out in seen.items() if (out >> bit) & 1]
        zeros = [inp for inp, out in seen.items() if not ((out >> bit) & 1)]
        print(f"  m{bit}: {len(ones)} ones, {len(zeros)} zeros")

if __name__ == "__main__":
    print("Generating truth tables...")
    build_full_tt()
    build_mag_tt()
    build_sdec_tt()
    build_esumdec_tt()
    analyze_mag_bits()
    print(f"\nAll truth tables written to: {OUT}/")
