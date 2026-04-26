// Mutation 2 — Explicit +1 fold via XOR of mag-zero detection.
// out = sy ? -mag : mag = mag XOR rep(sy AND (mag != 0))   for bits except 0
// out[0] = mag[0] always
// Y[8] = sy AND (mag != 0)
// This avoids the explicit +1 carry chain.

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

    // "mag is nonzero" = OR of all mag bits. With P being 0 iff M_a*M_b=0,
    // and shift preserving zero, mag != 0 iff P != 0.
    wire P_nonzero = P0 | P1 | P2 | P3;
    // (Equivalently: pp_aml | pp_alb | pp_lll | P0, since P_i are derived from these.)

    // Conditional negate using the "complement-from-first-1" rule.
    // For sy=0: out = mag, padded with zero
    // For sy=1: out[i] = mag[i] for i ≤ first-1; out[i] = ~mag[i] for i > first-1
    // Implemented via: keep lowest "set" bit and below; flip above.
    // For our specific magnitudes, mag[0] is the only "always-LSB"; the
    // first-1 detection is: below_i = AND_{j<i} ~mag[j]
    wire below1 = ~mag[0];
    wire below2 = below1 & ~mag[1];
    wire below3 = below2 & ~mag[2];
    wire below4 = below3 & ~mag[3];
    wire below5 = below4 & ~mag[4];
    wire below6 = below5 & ~mag[5];
    wire below7 = below6 & ~mag[6];

    // out[i] = mag[i] for sy=0; mag[i] XOR sy for sy=1 if some bit < i is set; mag[i] otherwise.
    //        = mag[i] XOR (sy AND ~below_i)   for i ≥ 1
    // out[0] = mag[0] always
    assign y[0] = mag[0];
    assign y[1] = mag[1] ^ (sy & ~below1);
    assign y[2] = mag[2] ^ (sy & ~below2);
    assign y[3] = mag[3] ^ (sy & ~below3);
    assign y[4] = mag[4] ^ (sy & ~below4);
    assign y[5] = mag[5] ^ (sy & ~below5);
    assign y[6] = mag[6] ^ (sy & ~below6);
    assign y[7] = mag[7] ^ (sy & ~below7);
    assign y[8] = sy & P_nonzero;          // = sy AND (mag != 0); for sy=0 -> 0; for sy=1 with mag=0 -> 0; mag>0 -> 1
endmodule
