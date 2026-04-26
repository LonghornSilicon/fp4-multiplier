// Mutation 18 — pre-mask-by-sy formulation: precompute mask_i = sy & mag[i],
// then flip_i = OR running of mask values. Compresses sy & ~below_i into a
// running-OR over masked bits.

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

    // mask_i = sy & mag[i]; flip_i = OR of mask[0..i-1]
    wire m0_s = sy & mag[0];
    wire m1_s = sy & mag[1];
    wire m2_s = sy & mag[2];
    wire m3_s = sy & mag[3];
    wire m4_s = sy & mag[4];
    wire m5_s = sy & mag[5];
    wire m6_s = sy & mag[6];

    wire f1 = m0_s;
    wire f2 = f1 | m1_s;
    wire f3 = f2 | m2_s;
    wire f4 = f3 | m3_s;
    wire f5 = f4 | m4_s;
    wire f6 = f5 | m5_s;
    wire f7 = f6 | m6_s;

    assign y[0] = mag[0];
    assign y[1] = mag[1] ^ f1;
    assign y[2] = mag[2] ^ f2;
    assign y[3] = mag[3] ^ f3;
    assign y[4] = mag[4] ^ f4;
    assign y[5] = mag[5] ^ f5;
    assign y[6] = mag[6] ^ f6;
    assign y[7] = mag[7] ^ f7;
    assign y[8] = sy & (a[0] | a[1] | a[2]) & (b[0] | b[1] | b[2]);
endmodule
