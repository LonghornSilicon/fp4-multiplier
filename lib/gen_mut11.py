"""Emit a mut11-style Verilog (mut2 + raw P_nonzero for Y[8]) parameterized
by a sign-symmetric remap. The P_nonzero expression must adapt to the remap
since `(a[0]|a[1]|a[2])` is "all 3 lower raw bits" — which equals "M_a != 0"
ONLY for sign-symmetric remaps where lower 3 raw bits = magnitude code (any
permutation thereof, since OR is symmetric). So P_nonzero = OR of all 3 lower
bits is universal across sign-symmetric remaps."""
from gen_struct import fields_for_values, _simplify_4to1


def _derived_truth_table(fields, predicate):
    return [predicate(fields[code]) for code in range(16)]


def emit_mut11_verilog(values: list[float]) -> str:
    fields = fields_for_values(values)
    tts = [[fields[code][k] for code in range(16)] for k in range(4)]
    expr_a = [_simplify_4to1(tt, "a") for tt in tts]
    expr_b = [_simplify_4to1(tt, "b") for tt in tts]
    s_a, eh_a_e, el_a_e, m_a_e = expr_a
    s_b, eh_b_e, el_b_e, m_b_e = expr_b

    lb_tt_a = _derived_truth_table(fields, lambda f: int(f[1] or f[2]))
    lb_a_e = _simplify_4to1(lb_tt_a, "a")
    lb_b_e = _simplify_4to1(lb_tt_a, "b")
    # M_nonzero = (eh OR el OR m) — for sign-symmetric remaps this is OR of
    # the 3 lower raw input bits regardless of which is which.
    nz_tt = _derived_truth_table(fields, lambda f: int(f[1] or f[2] or f[3]))
    nz_a_e = _simplify_4to1(nz_tt, "a")
    nz_b_e = _simplify_4to1(nz_tt, "b")

    return f"""
module fp4_mul (
    input  wire [3:0] a,
    input  wire [3:0] b,
    output wire [8:0] y
);
    wire sa = {s_a};
    wire sb = {s_b};
    wire eh_a = {eh_a_e};
    wire el_a = {el_a_e};
    wire ma  = {m_a_e};
    wire eh_b = {eh_b_e};
    wire el_b = {el_b_e};
    wire mb  = {m_b_e};
    wire lb_a = {lb_a_e};
    wire lb_b = {lb_b_e};

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

    wire below1 = ~mag[0];
    wire below2 = below1 & ~mag[1];
    wire below3 = below2 & ~mag[2];
    wire below4 = below3 & ~mag[3];
    wire below5 = below4 & ~mag[4];
    wire below6 = below5 & ~mag[5];
    wire below7 = below6 & ~mag[6];

    assign y[0] = mag[0];
    assign y[1] = mag[1] ^ (sy & ~below1);
    assign y[2] = mag[2] ^ (sy & ~below2);
    assign y[3] = mag[3] ^ (sy & ~below3);
    assign y[4] = mag[4] ^ (sy & ~below4);
    assign y[5] = mag[5] ^ (sy & ~below5);
    assign y[6] = mag[6] ^ (sy & ~below6);
    assign y[7] = mag[7] ^ (sy & ~below7);
    assign y[8] = sy & ({nz_a_e}) & ({nz_b_e});
endmodule
"""
