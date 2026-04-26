// Mutation 24 — eliminate the dedicated `el` XOR signal by inlining only where needed.
// el is used 4 times: (a[2] & el_a, a[2] & ~el_a) twice. Maybe ABC handles this
// more cleanly with `el_a` as a shared XOR than with inlined `(a[1] ^ a[2])`.
// But what about FULLY inlined raw bits?
//   sa1[1] = a[2] & ~a[1]   (= eh & el under σ — collapses)
//   sa1[0] = a[1] & a[2]    (= eh & ~el under σ — collapses)
// Skip the el XOR computation entirely.

module fp4_mul (
    input  wire [3:0] a,
    input  wire [3:0] b,
    output wire [8:0] y
);
    wire sa = a[3], sb = b[3];
    wire ma = a[0], mb = b[0];
    wire lb_a = a[1] | a[2];
    wire lb_b = b[1] | b[2];

    wire pp_aml = lb_a & mb;
    wire pp_alb = ma & lb_b;
    wire pp_lll = lb_a & lb_b;
    wire P0 = ma & mb;
    wire P1 = pp_aml ^ pp_alb;
    wire c1 = pp_aml & pp_alb;
    wire P2 = pp_lll ^ c1;
    wire P3 = pp_lll & c1;
    wire [3:0] P = {P3, P2, P1, P0};

    // Direct K-bit computation, no `el` intermediate.
    // sa1[1] = eh & el = a[2] & (a[1]^a[2]) = a[2] & ~a[1]
    // sa1[0] = eh & ~el = a[2] & ~(a[1]^a[2]) = a[2] & a[1]
    wire sa1_hi = a[2] & ~a[1];
    wire sa1_lo = a[2] & a[1];
    wire sb1_hi = b[2] & ~b[1];
    wire sb1_lo = b[2] & b[1];
    wire [1:0] sa1 = {sa1_hi, sa1_lo};
    wire [1:0] sb1 = {sb1_hi, sb1_lo};
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
    assign y[8] = sy & (a[0] | a[1] | a[2]) & (b[0] | b[1] | b[2]);
endmodule
