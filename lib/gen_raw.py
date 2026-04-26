"""Auto-generate a 'raw-bit' Verilog for any sign-symmetric remap.

Strategy: given the remap, compute the per-output-bit Boolean expression for
each of (sign, eh, el, m). Then emit Verilog that uses those expressions
directly inline rather than naming intermediate `dec_*` wires. This lets
yosys' opt collapse algebraic identities like a | (a^b) → a|b.
"""
from __future__ import annotations
from gen_struct import fields_for_values, _simplify_4to1


def emit_raw_verilog(values: list[float]) -> str:
    """Emit a raw-bit Verilog for a sign-symmetric remap.

    The structural body uses raw input bits; only the decoder for (sign, eh,
    el, m) is per-remap.
    """
    fields = fields_for_values(values)
    out_names = ["s", "eh", "el", "m"]
    # Build truth tables
    tts = [[fields[code][k] for code in range(16)] for k in range(4)]
    # Express each as a string (single bit / NOT / XOR / AND / OR pattern)
    expr_a = [_simplify_4to1(tt, "a") for tt in tts]
    expr_b = [_simplify_4to1(tt, "b") for tt in tts]
    s_a, eh_a, el_a, m_a = expr_a
    s_b, eh_b, el_b, m_b = expr_b
    return f"""
module fp4_mul (
    input  wire [3:0] a,
    input  wire [3:0] b,
    output wire [8:0] y
);
    // Raw-bit decode (per-remap minimal expressions)
    wire sa = {s_a};
    wire sb = {s_b};
    wire eh_a = {eh_a};
    wire el_a = {el_a};
    wire ma  = {m_a};
    wire eh_b = {eh_b};
    wire el_b = {el_b};
    wire mb  = {m_b};

    // Structural multiplier (sign-magnitude / 2x2 / variable shift / negate)
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
    wire [3:0] P = {{P3, P2, P1, P0}};

    wire [1:0] sa1 = {{eh_a & el_a, eh_a & ~el_a}};
    wire [1:0] sb1 = {{eh_b & el_b, eh_b & ~el_b}};
    wire [2:0] K = sa1 + sb1;

    wire [7:0] mag = P << K;
    wire sy = sa ^ sb;
    wire [8:0] mag9 = {{1'b0, mag}};
    wire [8:0] xord = mag9 ^ {{9{{sy}}}};
    wire [8:0] outv = xord + {{8'b0, sy}};
    assign y = outv;
endmodule
"""


if __name__ == "__main__":
    from remap import encoding_from_magnitude_perm
    perm = (0, 1, 2, 3, 6, 7, 4, 5)
    v = encoding_from_magnitude_perm(perm)
    print(emit_raw_verilog(v))
