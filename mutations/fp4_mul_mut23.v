// Mutation 23 — replace flip-detection with running-XOR.
// Observation: y[i] = mag[i] when sy=0, and y[i] = ~mag[i] for i > first-1 when sy=1.
// "First-1 detection" is structurally similar to "running parity until first 1".
// Try: flip_i = sy AND (mag[0..i-1] not all zero) using running OR but
// emitted with NOR-NOT chain (different AIG topology than mut2/mut11).

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

    // Use sy itself as a "carry seed" — propagate via OR chain pre-AND with mag.
    // any_so_far = OR of mag[0..i-1] (a "flip-active" indicator)
    // Using "explicit AOI" form: any_i = any_{i-1} | mag[i-1]
    wire any1 = mag[0];
    wire any2 = any1 | mag[1];
    wire any3 = any2 | mag[2];
    wire any4 = any3 | mag[3];
    wire any5 = any4 | mag[4];
    wire any6 = any5 | mag[5];
    wire any7 = any6 | mag[6];

    // Now y[i] = mag[i] XOR (sy AND any_i)
    assign y[0] = mag[0];
    assign y[1] = mag[1] ^ (sy & any1);
    assign y[2] = mag[2] ^ (sy & any2);
    assign y[3] = mag[3] ^ (sy & any3);
    assign y[4] = mag[4] ^ (sy & any4);
    assign y[5] = mag[5] ^ (sy & any5);
    assign y[6] = mag[6] ^ (sy & any6);
    assign y[7] = mag[7] ^ (sy & any7);
    assign y[8] = sy & (a[0] | a[1] | a[2]) & (b[0] | b[1] | b[2]);
endmodule
