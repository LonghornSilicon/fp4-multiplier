"""Emit a mut2-style Verilog (with NAND-chain below detector) parameterized
by an arbitrary sign-symmetric remap. Pre-collapses derived signals like
lb = eh | el and the K partial-sum bits to their simplest raw-bit Boolean
forms (using _simplify_4to1 on the appropriate truth table)."""
from gen_struct import fields_for_values, _simplify_4to1


def _derived_truth_table(fields, predicate):
    """Build a 16-row tt by applying `predicate` to fields[code]."""
    return [predicate(fields[code]) for code in range(16)]


def emit_mut2_verilog(values: list[float]) -> str:
    fields = fields_for_values(values)
    tts = [[fields[code][k] for code in range(16)] for k in range(4)]
    expr_a = [_simplify_4to1(tt, "a") for tt in tts]
    expr_b = [_simplify_4to1(tt, "b") for tt in tts]
    s_a, eh_a_e, el_a_e, m_a_e = expr_a
    s_b, eh_b_e, el_b_e, m_b_e = expr_b

    # Pre-compute simplified raw-bit expressions for lb, sa1_hi, sa1_lo.
    # lb = eh | el
    lb_tt_a = _derived_truth_table(fields, lambda f: int(f[1] or f[2]))
    lb_tt_b = lb_tt_a  # same function on b
    lb_a_e = _simplify_4to1(lb_tt_a, "a")
    lb_b_e = _simplify_4to1(lb_tt_b, "b")
    # sa1[1] = eh & el
    s1_hi_tt = _derived_truth_table(fields, lambda f: int(f[1] and f[2]))
    s1_hi_a = _simplify_4to1(s1_hi_tt, "a")
    s1_hi_b = _simplify_4to1(s1_hi_tt, "b")
    # sa1[0] = eh & ~el
    s1_lo_tt = _derived_truth_table(fields, lambda f: int(f[1] and not f[2]))
    s1_lo_a = _simplify_4to1(s1_lo_tt, "a")
    s1_lo_b = _simplify_4to1(s1_lo_tt, "b")
    # Explicit-XOR form (matches what gave 75 by hand for best1).
    # Keep el_a, el_b as named XOR signals so ABC can use them as shared
    # entry points; pre-collapse only lb (the OR identity).
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

    // Use eh & el / eh & ~el form (forces explicit XOR signal — ABC's friend)
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
    wire below8 = below7 & ~mag[7];

    assign y[0] = mag[0];
    assign y[1] = mag[1] ^ (sy & ~below1);
    assign y[2] = mag[2] ^ (sy & ~below2);
    assign y[3] = mag[3] ^ (sy & ~below3);
    assign y[4] = mag[4] ^ (sy & ~below4);
    assign y[5] = mag[5] ^ (sy & ~below5);
    assign y[6] = mag[6] ^ (sy & ~below6);
    assign y[7] = mag[7] ^ (sy & ~below7);
    assign y[8] = sy & ~below8;
endmodule
"""
