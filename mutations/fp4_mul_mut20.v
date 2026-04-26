// Mutation 20 — share (sy & ~below_i) computation differently.
// Since sy is a single bit, all flip_i = sy & ~below_i can share through:
//   flip_i = ~(below_i | ~sy)  (DeMorgan, same gates but different structure)
// Try all-NAND form to see if ABC's AIG canonicalization compresses better.

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
    wire [3:0] P = {P3, P2, P1, P0};

    wire [1:0] sa1 = {a[2] & el_a, a[2] & ~el_a};
    wire [1:0] sb1 = {b[2] & el_b, b[2] & ~el_b};
    wire [2:0] K = sa1 + sb1;
    wire [7:0] mag = P << K;
    wire sy = sa ^ sb;

    // Build inverted-flip directly: flip_i = sy AND OR(mag[0..i-1])
    // Express as NAND-tree:
    wire nsy = ~sy;
    wire below1 = ~mag[0];
    wire below2 = below1 & ~mag[1];
    wire below3 = below2 & ~mag[2];
    wire below4 = below3 & ~mag[3];
    wire below5 = below4 & ~mag[4];
    wire below6 = below5 & ~mag[5];
    wire below7 = below6 & ~mag[6];
    wire below8 = below7 & ~mag[7];

    // flip_i = sy & ~below_i = NOT(nsy OR below_i)
    wire flip1 = ~(nsy | below1);
    wire flip2 = ~(nsy | below2);
    wire flip3 = ~(nsy | below3);
    wire flip4 = ~(nsy | below4);
    wire flip5 = ~(nsy | below5);
    wire flip6 = ~(nsy | below6);
    wire flip7 = ~(nsy | below7);

    assign y[0] = mag[0];
    assign y[1] = mag[1] ^ flip1;
    assign y[2] = mag[2] ^ flip2;
    assign y[3] = mag[3] ^ flip3;
    assign y[4] = mag[4] ^ flip4;
    assign y[5] = mag[5] ^ flip5;
    assign y[6] = mag[6] ^ flip6;
    assign y[7] = mag[7] ^ flip7;
    assign y[8] = sy & (a[0] | a[1] | a[2]) & (b[0] | b[1] | b[2]);
endmodule
