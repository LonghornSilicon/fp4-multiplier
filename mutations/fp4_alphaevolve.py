"""AlphaEvolve-style verifier-in-the-loop search over Verilog mutations of the
default-encoding FP4 multiplier. Each candidate is a hand-mutated structural
Verilog string. We synthesize each, verify, and rank by gate count.
"""
from __future__ import annotations
import re
import shutil
import subprocess
import tempfile
import time
from pathlib import Path

from verify import verify_blif

CODE = Path(__file__).resolve().parent
LIB = CODE / "contest.lib"

RESYN2 = "balance; rewrite; refactor; balance; rewrite; rewrite -z; balance; refactor -z; rewrite -z; balance"
DEEP_SCRIPT = (
    f"strash; ifraig; scorr; dc2; strash; "
    f"{RESYN2}; "
    f"&get -n; &deepsyn -T 3 -I 4; &put; "
    f"logic; mfs2; strash; "
    f"dch -f; map -a -B 0"
)


# ----- Building blocks -------------------------------------------------------
# Each candidate Verilog must define module fp4_mul(input [3:0] a, b, output [8:0] y).
# We focus on the default encoding here; remap orthogonal to AlphaEvolve search.

CAND_BASE = """
module fp4_mul (
    input  wire [3:0] a, b,
    output wire [8:0] y
);
    wire sa = a[3], eh_a = a[2], el_a = a[1], ma = a[0];
    wire sb = b[3], eh_b = b[2], el_b = b[1], mb = b[0];
    {body}
endmodule
"""

# Variant 1: standard struct
V1_BODY = """
    wire lb_a = eh_a | el_a;
    wire lb_b = eh_b | el_b;
    wire [1:0] Ma = {lb_a, ma};
    wire [1:0] Mb = {lb_b, mb};
    wire [3:0] P = Ma * Mb;
    wire [1:0] sa1 = {eh_a & el_a, eh_a & ~el_a};
    wire [1:0] sb1 = {eh_b & el_b, eh_b & ~el_b};
    wire [2:0] K = sa1 + sb1;
    wire [7:0] mag = P << K;
    wire sy = sa ^ sb;
    wire [8:0] mag9 = {1'b0, mag};
    wire [8:0] xord = mag9 ^ {9{sy}};
    wire [8:0] outv = xord + {8'b0, sy};
    assign y = outv;
"""

# Variant 2: K computed as 1-hot, then explicit shift
V2_BODY = """
    wire lb_a = eh_a | el_a;
    wire lb_b = eh_b | el_b;
    wire pp_aml = lb_a & mb;
    wire pp_alb = ma & lb_b;
    wire pp_lll = lb_a & lb_b;
    wire P0 = ma & mb;
    wire P1 = pp_aml ^ pp_alb;
    wire c1 = pp_aml & pp_alb;
    wire P2 = pp_lll ^ c1;
    wire P3 = pp_lll & c1;
    // 1-hot K indicators by ANDing partial K bits
    wire A2 = eh_a & el_a;
    wire A1 = eh_a & ~el_a;
    wire A0 = ~eh_a;
    wire B2 = eh_b & el_b;
    wire B1 = eh_b & ~el_b;
    wire B0 = ~eh_b;
    wire isK0 = A0 & B0;
    wire isK1 = (A1 & B0) | (A0 & B1);
    wire isK2 = (A2 & B0) | (A1 & B1) | (A0 & B2);
    wire isK3 = (A2 & B1) | (A1 & B2);
    wire isK4 = A2 & B2;
    wire mag0 = P0 & isK0;
    wire mag1 = (P1 & isK0) | (P0 & isK1);
    wire mag2 = (P2 & isK0) | (P1 & isK1) | (P0 & isK2);
    wire mag3 = (P3 & isK0) | (P2 & isK1) | (P1 & isK2) | (P0 & isK3);
    wire mag4 = (P3 & isK1) | (P2 & isK2) | (P1 & isK3) | (P0 & isK4);
    wire mag5 = (P3 & isK2) | (P2 & isK3) | (P1 & isK4);
    wire mag6 = (P3 & isK3) | (P2 & isK4);
    wire mag7 = P3 & isK4;
    wire [7:0] mag = {mag7, mag6, mag5, mag4, mag3, mag2, mag1, mag0};
    wire sy = sa ^ sb;
    wire [8:0] mag9 = {1'b0, mag};
    wire [8:0] xord = mag9 ^ {9{sy}};
    wire [8:0] outv = xord + {8'b0, sy};
    assign y = outv;
"""

# Variant 3: signed-multiply approach using shifted FP4 to integer
# val_a × 2 ∈ {0,1,2,3,4,6,8,12} -> 4-bit unsigned. With sign that's 5-bit signed.
# (2·val_a) × (2·val_b) = 4·val_a·val_b, which is what we want!
V3_BODY = """
    // Compute X = 2·val (4-bit unsigned magnitude) -> signed 5-bit value.
    wire [3:0] xa_mag, xb_mag;
    // 2·|val| bit 0: m AND ~eh
    // 2·|val| bit 1: (~eh AND el) OR (eh AND ~el AND m)
    // 2·|val| bit 2: eh AND (m OR ~el)
    // 2·|val| bit 3: eh AND el
    assign xa_mag[0] = ma & ~eh_a;
    assign xa_mag[1] = (~eh_a & el_a) | (eh_a & ~el_a & ma);
    assign xa_mag[2] = eh_a & (ma | ~el_a);
    assign xa_mag[3] = eh_a & el_a;
    assign xb_mag[0] = mb & ~eh_b;
    assign xb_mag[1] = (~eh_b & el_b) | (eh_b & ~el_b & mb);
    assign xb_mag[2] = eh_b & (mb | ~el_b);
    assign xb_mag[3] = eh_b & el_b;
    // Sign-extend to 5-bit, conditional negate before multiply
    wire signed [4:0] xa_s = sa ? -{1'b0, xa_mag} : {1'b0, xa_mag};
    wire signed [4:0] xb_s = sb ? -{1'b0, xb_mag} : {1'b0, xb_mag};
    wire signed [9:0] prod = xa_s * xb_s;
    assign y = prod[8:0];
"""

# Variant 4: K via OR-of-pairs decomposition
V4_BODY = """
    wire lb_a = eh_a | el_a;
    wire lb_b = eh_b | el_b;
    wire [1:0] Ma = {lb_a, ma};
    wire [1:0] Mb = {lb_b, mb};
    wire [3:0] P = Ma * Mb;
    // Compute K differently: K = (eh_a*2 + ~el_a*eh_a) ... no, try
    // K = eh_a + eh_b + (eh_a&el_a) + (eh_b&el_b) - 0   (sum of 4 1-bit values)
    wire [2:0] K = eh_a + eh_b + (eh_a & el_a) + (eh_b & el_b);
    wire [7:0] mag = P << K;
    wire sy = sa ^ sb;
    wire [8:0] mag9 = {1'b0, mag};
    wire [8:0] xord = mag9 ^ {9{sy}};
    wire [8:0] outv = xord + {8'b0, sy};
    assign y = outv;
"""


# Variant 5: muxed shift
V5_BODY = """
    wire lb_a = eh_a | el_a;
    wire lb_b = eh_b | el_b;
    wire [1:0] Ma = {lb_a, ma};
    wire [1:0] Mb = {lb_b, mb};
    wire [3:0] P = Ma * Mb;
    // Direct case-stmt mux for the shift instead of barrel.
    wire [1:0] sa1 = {eh_a & el_a, eh_a & ~el_a};
    wire [1:0] sb1 = {eh_b & el_b, eh_b & ~el_b};
    wire [2:0] K = sa1 + sb1;
    reg [7:0] mag;
    always @* begin
        case (K)
            3'd0: mag = {4'b0, P};
            3'd1: mag = {3'b0, P, 1'b0};
            3'd2: mag = {2'b0, P, 2'b0};
            3'd3: mag = {1'b0, P, 3'b0};
            3'd4: mag =        {P, 4'b0};
            default: mag = 8'b0;
        endcase
    end
    wire sy = sa ^ sb;
    wire [8:0] mag9 = {1'b0, mag};
    wire [8:0] xord = mag9 ^ {9{sy}};
    wire [8:0] outv = xord + {8'b0, sy};
    assign y = outv;
"""


# Variant 6: Use signed multiply with NO conditional negate (sign baked in)
# This avoids the +1 carry.
V6_BODY = """
    // 4·val (signed integer): sign-extend |val|·2 to 6 bits with conditional negate
    // BUT do so BEFORE multiplication so the multiplier handles signs natively.
    wire [3:0] xa_mag;
    assign xa_mag[0] = ma & ~eh_a;
    assign xa_mag[1] = (~eh_a & el_a) | (eh_a & ~el_a & ma);
    assign xa_mag[2] = eh_a & (ma | ~el_a);
    assign xa_mag[3] = eh_a & el_a;
    wire [3:0] xb_mag;
    assign xb_mag[0] = mb & ~eh_b;
    assign xb_mag[1] = (~eh_b & el_b) | (eh_b & ~el_b & mb);
    assign xb_mag[2] = eh_b & (mb | ~el_b);
    assign xb_mag[3] = eh_b & el_b;
    // 5-bit signed: sa ? -xa_mag : xa_mag (via XOR + add)
    wire [4:0] xa_xor = {1'b0, xa_mag} ^ {5{sa}};
    wire signed [4:0] xa_s = xa_xor + {4'b0, sa};
    wire [4:0] xb_xor = {1'b0, xb_mag} ^ {5{sb}};
    wire signed [4:0] xb_s = xb_xor + {4'b0, sb};
    wire signed [9:0] prod = xa_s * xb_s;
    assign y = prod[8:0];
"""


CANDIDATES = {
    "v1_struct":       V1_BODY,
    "v2_explicit_isK": V2_BODY,
    "v3_signed_2x":    V3_BODY,
    "v4_K_sum_OR":     V4_BODY,
    "v5_muxed_shift":  V5_BODY,
    "v6_signed_2x_xor":V6_BODY,
}


def synth_one(body: str, abc_script: str = DEEP_SCRIPT, timeout: int = 30):
    verilog = CAND_BASE.format(body=body)
    with tempfile.TemporaryDirectory(prefix="ae_", dir="/tmp") as td:
        td = Path(td)
        v_path = td / "fp4_mul.v"
        v_path.write_text(verilog)
        shutil.copy(LIB, td / "contest.lib")
        yscr = "+" + abc_script.strip().replace(" ", ",")
        (td / "synth.ys").write_text(
            f"read_verilog {v_path}\n"
            f"hierarchy -top fp4_mul\n"
            f"proc; opt; memory; opt; flatten; opt -full; techmap; opt\n"
            f"abc -liberty {td}/contest.lib -script {yscr}\n"
            f"write_blif {td}/out.blif\n"
            f"stat -liberty {td}/contest.lib\n"
        )
        t0 = time.time()
        try:
            r = subprocess.run(
                ["yosys", str(td / "synth.ys")],
                capture_output=True, text=True, cwd=str(td), timeout=timeout,
            )
        except subprocess.TimeoutExpired:
            return {"gates": None, "verify": False, "wall": timeout, "log": "TIMEOUT"}
        m = re.findall(r"Chip area for module '\\?fp4_mul':\s*([0-9.]+)", r.stdout)
        gates = int(round(float(m[-1]))) if m else None
        blif = td / "out.blif"
        ok, mism = verify_blif(blif) if blif.exists() else (False, [])
        return {"gates": gates, "verify": ok, "wall": time.time() - t0,
                "log_tail": "\n".join(r.stdout.splitlines()[-10:])}


def main():
    print(f"{'name':22s} {'gates':>6}  {'wall':>5}", flush=True)
    print("-" * 50, flush=True)
    results = []
    for name, body in CANDIDATES.items():
        r = synth_one(body)
        v = "OK" if r["verify"] else "FAIL"
        print(f"{name:22s} {r['gates']!s:>6}  {r['wall']:>5.1f}  {v}", flush=True)
        results.append((name, r))
    ok = [(n, r) for n, r in results if r["verify"] and r["gates"]]
    if ok:
        ok.sort(key=lambda x: x[1]["gates"])
        print(f"\nBest: {ok[0][1]['gates']} gates  ({ok[0][0]})")


if __name__ == "__main__":
    main()
