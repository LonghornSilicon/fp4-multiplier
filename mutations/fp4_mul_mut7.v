// Mutation 7 — Hardcode each y[i] as a direct expression of (P, sy, any1_below).
// Use mut2's NAND-chain "below" structure (which won) but skip the [7:0] mag wire,
// folding directly into the conditional negate.

module fp4_mul (
    input  wire [3:0] a,
    input  wire [3:0] b,
    output wire [8:0] y
);
    wire sa = a[3], sb = b[3];
    wire ma = a[0], mb = b[0];
    wire lb_a = a[1] | a[2];
    wire lb_b = b[1] | b[2];
    wire el_a = a[1] ^ a[2];
    wire el_b = b[1] ^ b[2];

    wire pp_aml = lb_a & mb;
    wire pp_alb = ma & lb_b;
    wire pp_lll = lb_a & lb_b;
    wire P0 = ma & mb;
    wire P1 = pp_aml ^ pp_alb;
    wire c1 = pp_aml & pp_alb;
    wire P2 = pp_lll ^ c1;
    wire P3 = pp_lll & c1;

    wire [1:0] sa1 = {a[2] & el_a, a[2] & ~el_a};
    wire [1:0] sb1 = {b[2] & el_b, b[2] & ~el_b};
    wire [2:0] K = sa1 + sb1;
    wire [3:0] P = {P3, P2, P1, P0};
    wire [7:0] mag = P << K;
    wire sy = sa ^ sb;

    // mut2 below detection (NAND-chain — won the bake-off)
    wire below1 = ~mag[0];
    wire below2 = below1 & ~mag[1];
    wire below3 = below2 & ~mag[2];
    wire below4 = below3 & ~mag[3];
    wire below5 = below4 & ~mag[4];
    wire below6 = below5 & ~mag[5];
    wire below7 = below6 & ~mag[6];

    // flip_i = sy & ~below_i.  Note: mut2's below_i = NAND of mag[0..i-1] = "all zero so far",
    // so ~below_i = "any 1 below i". flip_i = sy AND "any 1 below i".
    // Compute the "non-zero magnitude" predicate cheaply:
    wire mag_any = mag[0] | mag[1] | mag[2] | mag[3] | mag[4] | mag[5] | mag[6] | mag[7];

    assign y[0] = mag[0];
    assign y[1] = mag[1] ^ (sy & ~below1);
    assign y[2] = mag[2] ^ (sy & ~below2);
    assign y[3] = mag[3] ^ (sy & ~below3);
    assign y[4] = mag[4] ^ (sy & ~below4);
    assign y[5] = mag[5] ^ (sy & ~below5);
    assign y[6] = mag[6] ^ (sy & ~below6);
    assign y[7] = mag[7] ^ (sy & ~below7);
    assign y[8] = sy & mag_any;
endmodule
