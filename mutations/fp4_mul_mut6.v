// Mutation 6 — mut2 + force flip = sy AND ~below in alternate form.
// Try expressing ~below_i (the active flip indicator) directly via running ORs
// of mag[0..i-1], but using NAND/AND-NOT pattern instead of plain OR.
// Specifically: ~below_i+1 = ~(below_i & ~mag[i]) = ~below_i | mag[i]
// Express recursively: flip_active_{i+1} = flip_active_i | mag[i].

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

    // flip_i = sy AND (mag[0..i-1] has any 1)  =  sy AND OR-chain
    // Build OR-chain via running OR
    wire any1_at1 = mag[0];
    wire any1_at2 = any1_at1 | mag[1];
    wire any1_at3 = any1_at2 | mag[2];
    wire any1_at4 = any1_at3 | mag[3];
    wire any1_at5 = any1_at4 | mag[4];
    wire any1_at6 = any1_at5 | mag[5];
    wire any1_at7 = any1_at6 | mag[6];
    wire any1_at8 = any1_at7 | mag[7];

    assign y[0] = mag[0];
    assign y[1] = mag[1] ^ (sy & any1_at1);
    assign y[2] = mag[2] ^ (sy & any1_at2);
    assign y[3] = mag[3] ^ (sy & any1_at3);
    assign y[4] = mag[4] ^ (sy & any1_at4);
    assign y[5] = mag[5] ^ (sy & any1_at5);
    assign y[6] = mag[6] ^ (sy & any1_at6);
    assign y[7] = mag[7] ^ (sy & any1_at7);
    assign y[8] = sy & any1_at8;
endmodule
