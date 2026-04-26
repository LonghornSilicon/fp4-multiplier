// Mutation 8 — explicit Y[7], Y[8] direct expressions + mut2 for the rest.
// mag[7] = 1 only when K=4 AND P=9, i.e., both inputs have val=6 (in remap σ).
// y[7]: positive case is mag[7]=1; negative case is sign-extension.
// Specifically: y[7] = mag[7] XOR flip[7] under our mut2 rule.
// But mag[7] truth table is much simpler than a generic shift bit.

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

    // Use explicit Y[7] expression (simpler than full shift)
    // mag[7] = P[3] AND (K==4) = (lb_a & lb_b & m_a & m_b) AND (eh_a&el_a) AND (eh_b&el_b)
    // For our remap, eh_a&el_a = a[2]&~a[1] (after collapse).
    // Algebraic: lb_a AND (a[2]&~a[1]) = (a[1]|a[2]) AND a[2] AND ~a[1] = a[2] AND ~a[1].
    // So mag[7] = a[2]&~a[1]&a[0] AND b[2]&~b[1]&b[0].
    // We let ABC find this anyway via the standard shifter.

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
    // For y[7]: mag[7] is rare (only 2 of 256 inputs make it 1).
    // Standard formulation:
    assign y[7] = mag[7] ^ (sy & ~below7);
    assign y[8] = sy & ~below8;
endmodule
