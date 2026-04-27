// Mutation 32 — Sklansky / Brent-Kung parallel-prefix below-detector.
//
// Structural innovation: the canonical NAND-ripple
//   below_{i+1} = below_i & ~mag[i]
// is a depth-7 serial chain. Replace it with a depth-3 parallel prefix
// AND (Sklansky-style) over the inverted mag bits. Total AND count is
// the same (7 prefix ANDs vs 7 ripple ANDs) but the structural pattern
// is fundamentally different — fewer cascaded ANDs let dch/refactor see
// XOR/AOI factorings that the chain hides.
//
// Sklansky prefix on z[0..6] = ~mag[0..6]:
//   level 1 (pairs):    p01 = z0&z1   p23 = z2&z3   p45 = z4&z5
//   level 2 (group of 4): p03 = p01 & p23
//   level 3 (group of 6/7): p05 = p03 & p45,  p06 = p05 & z6
// below_i = AND of z[0..i-1]:
//   below1 = z0
//   below2 = p01
//   below3 = p01 & z2
//   below4 = p03
//   below5 = p03 & z4
//   below6 = p05
//   below7 = p05 & z6 = p06

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
    wire P3 = c1;
    wire [3:0] P = {P3, P2, P1, P0};

    wire [1:0] sa1 = {a[2] & el_a, a[2] & ~el_a};
    wire [1:0] sb1 = {b[2] & el_b, b[2] & ~el_b};
    wire [2:0] K = sa1 + sb1;
    wire [7:0] mag = P << K;
    wire sy = sa ^ sb;

    // ~mag[0..6] feed prefix ANDs.
    wire z0 = ~mag[0];
    wire z1 = ~mag[1];
    wire z2 = ~mag[2];
    wire z3 = ~mag[3];
    wire z4 = ~mag[4];
    wire z5 = ~mag[5];
    wire z6 = ~mag[6];

    // Sklansky parallel-prefix: depth ~3 vs 7 in ripple.
    wire p01 = z0 & z1;
    wire p23 = z2 & z3;
    wire p45 = z4 & z5;
    wire p03 = p01 & p23;
    wire p05 = p03 & p45;

    wire below1 = z0;
    wire below2 = p01;
    wire below3 = p01 & z2;
    wire below4 = p03;
    wire below5 = p03 & z4;
    wire below6 = p05;
    wire below7 = p05 & z6;

    assign y[0] = mag[0];
    assign y[1] = mag[1] ^ (sy & ~below1);
    assign y[2] = mag[2] ^ (sy & ~below2);
    assign y[3] = mag[3] ^ (sy & ~below3);
    assign y[4] = mag[4] ^ (sy & ~below4);
    assign y[5] = mag[5] ^ (sy & ~below5);
    assign y[6] = mag[6] ^ (sy & ~below6);
    assign y[7] = mag[7] ^ (sy & ~below7);
    assign y[8] = sy & (a[0] | a[1] | a[2]) & (b[0] | b[1] | b[2]);
endmodule
