"""
Direct-signed topology experiment: feed the FP4xFP4->QI9 truth table to ABC
without the sign-magnitude / conditional-negate split, and see what ABC
synthesizes.

Builds .pla / .blif / .v files for the 8-in 9-out function using the SAME
remap as autoresearch/multiplier.py (mag codes 000=0, 001=1.5, 010=3.0,
011=6.0, 100=0.5, 101=1.0, 110=2.0, 111=4.0; sign bit is MSB).

Then drives ABC with a battery of synthesis sequences and reports the
best AND-count and 2-LUT count.

Run: python3 experiments/exp_direct_signed_topology.py
"""
import os
import re
import sys
import shutil
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DATA = os.path.join(HERE, "data")
os.makedirs(DATA, exist_ok=True)

ABC_BIN = "/home/tit/abc/abc"
ABC_CWD = "/home/tit/abc"  # must run from here for abc.rc to load

# FP4 table (matches eval_circuit.FP4_TABLE)
FP4_TABLE = [0.0, 0.5, 1.0, 1.5, 2.0, 3.0, 4.0, 6.0,
             0.0, -0.5, -1.0, -1.5, -2.0, -3.0, -4.0, -6.0]

# Same magnitude encoding the production multiplier uses.
_MAG_TO_CODE = {0.0: 0b000, 1.5: 0b001, 3.0: 0b010, 6.0: 0b011,
                0.5: 0b100, 1.0: 0b101, 2.0: 0b110, 4.0: 0b111}


def remap(orig_idx):
    v = FP4_TABLE[orig_idx]
    sign = 1 if v < 0 else 0
    return (sign << 3) | _MAG_TO_CODE[abs(v)]


def build_truth_table():
    """
    Returns dict: 8-bit input code -> 9-bit QI9 output (sign|mag bits).

    The remap uses 15 of 16 codes per nibble (code 0b1000 = -0 is unused),
    so 225 of 256 input combinations are 'cared'; the other 31 are
    don't-cares.
    """
    rows = {}
    for a_orig in range(16):
        for b_orig in range(16):
            a_code = remap(a_orig)
            b_code = remap(b_orig)
            inp = (a_code << 4) | b_code
            qi9 = int(round(FP4_TABLE[a_orig] * FP4_TABLE[b_orig] * 4)) & 0x1FF
            # Convention: when product is zero, both sign-of-zero conventions
            # give result 0, so qi9 == 0 already. No don't-cares needed.
            rows[inp] = qi9
    return rows


def dc_inputs(rows):
    """Input combinations not in rows -> don't-cares."""
    return [inp for inp in range(256) if inp not in rows]


def write_pla(rows, path, dc_mode="explicit"):
    """
    Write 8-in 9-out PLA. Output bit ordering: res0 (sign/MSB) ... res8 (LSB).
    dc_mode:
      'explicit'  -- emit don't-care input rows with all-'-' outputs (uses .type fd)
      'fill_zero' -- fill DC inputs with output 0 (no DCs, simpler)
      'fill_dc'   -- DCs only via missing rows (.type f); ABC treats unspec as 0
    """
    care_inputs = sorted(rows.keys())
    if dc_mode == "fill_zero":
        with open(path, "w") as f:
            f.write(".i 8\n.o 9\n")
            f.write(".ilb a0 a1 a2 a3 b0 b1 b2 b3\n")
            f.write(".ob r0 r1 r2 r3 r4 r5 r6 r7 r8\n")
            f.write(".type fr\n")
            f.write(".p 256\n")
            for inp in range(256):
                qi9 = rows.get(inp, 0)
                in_bits = "".join(str((inp >> (7 - i)) & 1) for i in range(8))
                out_bits = "".join(str((qi9 >> (8 - i)) & 1) for i in range(9))
                f.write(f"{in_bits} {out_bits}\n")
            f.write(".e\n")
    else:
        # 'explicit' don't-care rows
        dcs = dc_inputs(rows)
        with open(path, "w") as f:
            f.write(".i 8\n.o 9\n")
            f.write(".ilb a0 a1 a2 a3 b0 b1 b2 b3\n")
            f.write(".ob r0 r1 r2 r3 r4 r5 r6 r7 r8\n")
            # 'fd' = on-set + don't-care set
            f.write(".type fd\n")
            f.write(f".p {len(care_inputs) + len(dcs)}\n")
            for inp in care_inputs:
                qi9 = rows[inp]
                in_bits = "".join(str((inp >> (7 - i)) & 1) for i in range(8))
                out_bits = "".join(str((qi9 >> (8 - i)) & 1) for i in range(9))
                f.write(f"{in_bits} {out_bits}\n")
            for inp in dcs:
                in_bits = "".join(str((inp >> (7 - i)) & 1) for i in range(8))
                f.write(f"{in_bits} {'-' * 9}\n")
            f.write(".e\n")


def write_blif(rows, path):
    """Sum-of-minterms BLIF. DC inputs simply omitted (treated as 0 by ABC)."""
    with open(path, "w") as f:
        f.write(".model fp4mul\n")
        f.write(".inputs a0 a1 a2 a3 b0 b1 b2 b3\n")
        f.write(".outputs r0 r1 r2 r3 r4 r5 r6 r7 r8\n")
        for bit in range(9):
            ones = []
            for inp, qi9 in rows.items():
                if (qi9 >> (8 - bit)) & 1:
                    bits = "".join(str((inp >> (7 - i)) & 1) for i in range(8))
                    ones.append(bits)
            f.write(f".names a0 a1 a2 a3 b0 b1 b2 b3 r{bit}\n")
            for o in ones:
                f.write(f"{o} 1\n")
        f.write(".end\n")


def write_verilog(rows, path):
    """Behavioral Verilog (case statement). Useful for yosys/abc round-trip."""
    with open(path, "w") as f:
        f.write("module fp4mul (\n")
        f.write("  input  a0,a1,a2,a3,b0,b1,b2,b3,\n")
        f.write("  output reg r0,r1,r2,r3,r4,r5,r6,r7,r8\n")
        f.write(");\n")
        f.write("  wire [7:0] in = {a0,a1,a2,a3,b0,b1,b2,b3};\n")
        f.write("  always @(*) begin\n")
        f.write("    case (in)\n")
        for inp in sorted(rows.keys()):
            qi9 = rows[inp]
            f.write(f"      8'd{inp}: {{r0,r1,r2,r3,r4,r5,r6,r7,r8}} = 9'b")
            f.write("".join(str((qi9 >> (8 - i)) & 1) for i in range(9)))
            f.write(";\n")
        f.write("      default: {r0,r1,r2,r3,r4,r5,r6,r7,r8} = 9'b0;\n")
        f.write("    endcase\n")
        f.write("  end\n")
        f.write("endmodule\n")


def run_abc(script):
    """Run ABC with given script, return stdout+stderr."""
    proc = subprocess.run(
        [ABC_BIN, "-c", script],
        cwd=ABC_CWD,
        capture_output=True, text=True, timeout=180,
    )
    out = proc.stdout + proc.stderr
    if "usage: read_pla" in out and "ABC command line" in out and out.count("usage:") > 0 \
            and "and =" not in out:
        # ABC bailed out parsing the file path (likely due to spaces or invalid PLA)
        return None
    return out


def parse_stats(output):
    """
    Parse 'print_stats' output. Returns dict with the FINAL stats
    (the last print_stats call in the script).
    Looks for lines like:
      'i/o = ...  and = N  lev = L'  (AIG)
      'nd = N  ...  lat = ...'        (mapped network)
      'nd = N  edge = E  ...'         (LUT mapped)
    """
    res = {"and": None, "lev": None, "nd": None, "edge": None, "lut": None}

    # AIG style: "and = N"
    for m in re.finditer(r"and\s*=\s*(\d+)", output):
        res["and"] = int(m.group(1))
    for m in re.finditer(r"lev\s*=\s*(\d+)", output):
        res["lev"] = int(m.group(1))
    # Generic node count
    for m in re.finditer(r"\bnd\s*=\s*(\d+)", output):
        res["nd"] = int(m.group(1))
    for m in re.finditer(r"edge\s*=\s*(\d+)", output):
        res["edge"] = int(m.group(1))
    return res


def parse_all_stats(output):
    """Return all (label, and|nd, lev) tuples from all print_stats lines, in order."""
    tuples = []
    # Split into print_stats calls; each leaves a header line like
    # "fp4mul              : i/o =   8/   9  lat = 0  and = N  lev = L"
    lines = output.splitlines()
    for line in lines:
        m = re.search(r"and\s*=\s*(\d+).*lev\s*=\s*(\d+)", line)
        if m:
            tuples.append(("aig", int(m.group(1)), int(m.group(2))))
            continue
        m = re.search(r"\bnd\s*=\s*(\d+).*edge\s*=\s*(\d+).*lev\s*=\s*(\d+)", line)
        if m:
            tuples.append(("net", int(m.group(1)), int(m.group(3)), int(m.group(2))))
    return tuples


def synth_attempts(path):
    """A battery of ABC synthesis sequences. Returns list of (label, result_dict)."""
    if path.endswith(".blif"):
        rd = f"read_blif {path}"
    else:
        rd = f"read_pla {path}"
    attempts = []

    # Attempt 1: standard resyn2 + variants
    sc1 = (
        f"{rd}; strash; print_stats; "
        "resyn2; print_stats; "
        "resyn2rs; print_stats; "
        "compress2rs; compress2rs; compress2rs; print_stats; "
        "if -K 2; print_stats;"
    )
    attempts.append(("resyn2+compress2rs+if-K2", sc1))

    # Attempt 2: dch + iterated compress2rs + resyn2
    sc2 = (
        f"{rd}; strash; "
        "compress2rs; compress2rs; compress2rs; compress2rs; "
        "dch; resyn2; resyn2rs; "
        "compress2rs; compress2rs; "
        "print_stats; if -K 2; print_stats;"
    )
    attempts.append(("dch+resyn2+compress2rs", sc2))

    # Attempt 3: BDD collapse + dc2
    sc3 = (
        f"{rd}; collapse; print_stats; "
        "strash; dc2; print_stats; "
        "resyn2; resyn2rs; print_stats; "
        "if -K 2; print_stats;"
    )
    attempts.append(("collapse+dc2+resyn2", sc3))

    # Attempt 4: deepsyn-style (heavier &-flow)
    sc4 = (
        f"{rd}; strash; "
        "&get; &dch; &syn2; &dc2; &put; print_stats; "
        "resyn2; resyn2rs; print_stats; "
        "if -K 2; print_stats;"
    )
    attempts.append(("&dch+&syn2+&dc2", sc4))

    # Attempt 5: many iterations
    sc5 = f"{rd}; strash; "
    for _ in range(4):
        sc5 += "compress2rs; "
    sc5 += "dch; "
    for _ in range(3):
        sc5 += "resyn2; resyn2rs; "
    for _ in range(3):
        sc5 += "compress2rs; "
    sc5 += "print_stats; if -K 2; print_stats;"
    attempts.append(("iterated-compress+dch+resyn2x3", sc5))

    # Attempt 6: deepsyn (state of art black-box)
    sc6 = (
        f"{rd}; strash; "
        "&get; &deepsyn -T 30; &put; print_stats; "
        "if -K 2; print_stats;"
    )
    attempts.append(("&deepsyn-30s", sc6))

    # Attempt 7: longer deepsyn with extra polishing
    sc7 = (
        f"{rd}; strash; "
        "&get; &deepsyn -T 90; &put; "
        "compress2rs; resyn2; resyn2rs; compress2rs; "
        "&get; &deepsyn -T 30; &put; "
        "print_stats; if -K 2; print_stats;"
    )
    attempts.append(("&deepsyn-90s+polish+30s", sc7))

    # Attempt 8: BDD-aware via collapse + multi-layer rewriting
    sc8 = (
        f"{rd}; collapse; strash; "
        "rewrite -z; refactor -z; rewrite -z; resub; "
        "compress2rs; compress2rs; "
        "&get; &dch -f; &syn3; &dc2; &put; "
        "print_stats; if -K 2; print_stats;"
    )
    attempts.append(("collapse+rewrite-z+&dch+&syn3", sc8))

    results = []
    for label, script in attempts:
        out = run_abc(script)
        if out is None:
            results.append({"label": label, "min_and": None, "min_nd": None,
                            "min_lev": None, "raw_tail": "(read failed)"})
            continue
        # Find best AIG 'and = N' and best LUT 'nd = N' across the script
        ands = [int(m.group(1)) for m in re.finditer(r"and\s*=\s*(\d+)", out)]
        nds = [int(m.group(1)) for m in re.finditer(r"\bnd\s*=\s*(\d+)", out)]
        levs = [int(m.group(1)) for m in re.finditer(r"lev\s*=\s*(\d+)", out)]
        results.append({
            "label": label,
            "min_and": min(ands) if ands else None,
            "min_nd": min(nds) if nds else None,
            "min_lev": min(levs) if levs else None,
            "raw_tail": out[-1500:],
        })
    return results


def alternative_onehot_encoding(rows):
    """
    Alternative encoding: instead of binary 9-bit output, use one-hot of distinct
    QI9 values. Number of distinct values determines one-hot width.
    """
    distinct = sorted(set(rows.values()))
    k = len(distinct)
    val_to_idx = {v: i for i, v in enumerate(distinct)}
    pla_path = os.path.join(DATA, "tt_onehot.pla")
    dcs = dc_inputs(rows)
    with open(pla_path, "w") as f:
        f.write(f".i 8\n.o {k}\n.type fd\n.p {len(rows) + len(dcs)}\n")
        for inp in sorted(rows.keys()):
            in_bits = "".join(str((inp >> (7 - i)) & 1) for i in range(8))
            v = rows[inp]
            out_bits = ["0"] * k
            out_bits[val_to_idx[v]] = "1"
            f.write(f"{in_bits} {''.join(out_bits)}\n")
        for inp in dcs:
            in_bits = "".join(str((inp >> (7 - i)) & 1) for i in range(8))
            f.write(f"{in_bits} {'-' * k}\n")
        f.write(".e\n")
    return pla_path, k


def main():
    print("Building 8-in 9-out signed truth table (production remap)...")
    rows = build_truth_table()
    print(f"  rows: {len(rows)} (expected 256)")
    distinct_outs = sorted(set(rows.values()))
    print(f"  distinct QI9 outputs: {len(distinct_outs)}")

    pla_dc = os.path.join(DATA, "tt_direct_signed_8in9out_dc.pla")
    pla_z = os.path.join(DATA, "tt_direct_signed_8in9out_zerofill.pla")
    blif = os.path.join(DATA, "tt_direct_signed_8in9out.blif")
    vlog = os.path.join(DATA, "tt_direct_signed_8in9out.v")
    write_pla(rows, pla_dc, dc_mode="explicit")
    write_pla(rows, pla_z, dc_mode="fill_zero")
    write_blif(rows, blif)
    write_verilog(rows, vlog)

    # Copy to /tmp (space-free) for ABC -- ABC's argv parser chokes on spaces.
    pla_dc_tmp = "/tmp/ds_dc.pla"
    pla_z_tmp = "/tmp/ds_zero.pla"
    blif_tmp = "/tmp/ds.blif"
    shutil.copy(pla_dc, pla_dc_tmp)
    shutil.copy(pla_z, pla_z_tmp)
    shutil.copy(blif, blif_tmp)
    print(f"  wrote {pla_dc} (with don't-cares)")
    print(f"  wrote {pla_z}  (DCs filled to 0)")
    print(f"  wrote {blif}")
    print(f"  wrote {vlog}")

    print("\n=== ABC synthesis battery: direct-signed 8->9 (DCs explicit) ===")
    results_dc = synth_attempts(pla_dc_tmp)
    for r in results_dc:
        print(f"  [{r['label']:36s}]  best_AIG_and={r['min_and']}  "
              f"best_LUT2_nd={r['min_nd']}  min_lev={r['min_lev']}")

    print("\n=== ABC synthesis battery: direct-signed 8->9 (DCs filled to 0) ===")
    results_z = synth_attempts(pla_z_tmp)
    for r in results_z:
        print(f"  [{r['label']:36s}]  best_AIG_and={r['min_and']}  "
              f"best_LUT2_nd={r['min_nd']}  min_lev={r['min_lev']}")

    print("\n=== ABC synthesis battery: direct-signed 8->9 (BLIF, no DCs) ===")
    # Use 'read' which auto-detects format and handles BLIF natively
    results_b = synth_attempts(blif_tmp)
    for r in results_b:
        print(f"  [{r['label']:36s}]  best_AIG_and={r['min_and']}  "
              f"best_LUT2_nd={r['min_nd']}  min_lev={r['min_lev']}")
    results = results_dc + results_z + results_b

    print("\n--- Detailed tail of best attempt ---")
    best = min(results, key=lambda r: (r["min_and"] if r["min_and"] is not None else 1e9))
    print(f"BEST sequence: {best['label']}")
    print(best["raw_tail"])

    # Alternative: one-hot output encoding
    print("\n=== Alternative: one-hot output encoding ===")
    oh_pla, k = alternative_onehot_encoding(rows)
    print(f"  one-hot width: {k}, file: {oh_pla}")
    oh_pla_tmp = "/tmp/ds_onehot.pla"
    shutil.copy(oh_pla, oh_pla_tmp)
    oh_results = synth_attempts(oh_pla_tmp)
    for r in oh_results:
        print(f"  [{r['label']:36s}]  best_AIG_and={r['min_and']}  "
              f"best_LUT2_nd={r['min_nd']}")

    print("\n=== Summary ===")
    best_and = min((r["min_and"] for r in results if r["min_and"] is not None), default=None)
    best_lut = min((r["min_nd"] for r in results if r["min_nd"] is not None), default=None)
    print(f"Direct-signed 8->9 best AIG AND-nodes: {best_and}")
    print(f"Direct-signed 8->9 best 2-LUT nodes:   {best_lut}")
    best_oh_and = min((r["min_and"] for r in oh_results if r["min_and"] is not None), default=None)
    print(f"One-hot 8->{k}     best AIG AND-nodes: {best_oh_and}")
    print(f"\nReference: hand-crafted multi-level (with XOR/NOT) = 84 gates.")
    print(f"Note: ABC counts AIG ANDs only (XOR=3 AIG ANDs); pure-AND comparison.")


if __name__ == "__main__":
    main()
