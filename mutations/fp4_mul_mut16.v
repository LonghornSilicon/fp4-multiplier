// Mutation 16 — alternative formulation: store ~below_i directly (= "any bit
// below i is 1") rather than below_i. This may give ABC a different starting
// AIG that synthesizes tighter.

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

    // any_i = mag[0] | ... | mag[i-1] (running OR)
    // Not used directly for y[i]; instead use ~below.
    // flip_i = sy & ~below_i = sy & any_i
    // This is equivalent to mut2 with running-OR formulation.
    // Try: store flip_i precomputed (with sy AND-ed in already).
    wire f1 = sy & mag[0];
    wire f2 = f1 | (sy & mag[1]);
    wire f3 = f2 | (sy & mag[2]);
    wire f4 = f3 | (sy & mag[3]);
    wire f5 = f4 | (sy & mag[4]);
    wire f6 = f5 | (sy & mag[5]);
    wire f7 = f6 | (sy & mag[6]);
    wire f8 = f7 | (sy & mag[7]);

    assign y[0] = mag[0];
    assign y[1] = mag[1] ^ f1;
    assign y[2] = mag[2] ^ f2;
    assign y[3] = mag[3] ^ f3;
    assign y[4] = mag[4] ^ f4;
    assign y[5] = mag[5] ^ f5;
    assign y[6] = mag[6] ^ f6;
    assign y[7] = mag[7] ^ f7;
    assign y[8] = f8;
endmodule
