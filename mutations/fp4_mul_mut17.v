// Mutation 17 — explicit 1-hot isK indicators + direct mag bit expression.
// Bypasses the P<<K shifter; each mag[i] is OR of P[j] AND isK[i-j].
// Under σ=(0,1,2,3,6,7,4,5):
//   sa1 = a[2]*(1+el_a) where el_a = a[1]^a[2]
//   sa1=0: ~a[2]   sa1=1: a[2]&a[1]   sa1=2: a[2]&~a[1]
// Similarly for b.

module fp4_mul (
    input  wire [3:0] a,
    input  wire [3:0] b,
    output wire [8:0] y
);
    wire sa = a[3], sb = b[3];
    wire ma = a[0], mb = b[0];
    wire lb_a = a[1] | a[2];
    wire lb_b = b[1] | b[2];

    // Partial sa1, sb1 indicators (1-hot, mutually exclusive).
    wire sa1_0 = ~a[2];
    wire sa1_1 = a[2] & a[1];     // = eh & ~el under σ
    wire sa1_2 = a[2] & ~a[1];    // = eh & el under σ
    wire sb1_0 = ~b[2];
    wire sb1_1 = b[2] & b[1];
    wire sb1_2 = b[2] & ~b[1];

    // 1-hot K-equals-c indicators
    wire isK0 = sa1_0 & sb1_0;
    wire isK1 = (sa1_1 & sb1_0) | (sa1_0 & sb1_1);
    wire isK2 = (sa1_2 & sb1_0) | (sa1_1 & sb1_1) | (sa1_0 & sb1_2);
    wire isK3 = (sa1_2 & sb1_1) | (sa1_1 & sb1_2);
    wire isK4 = sa1_2 & sb1_2;

    // 2x2 mantissa product (same as before)
    wire pp_aml = lb_a & mb;
    wire pp_alb = ma & lb_b;
    wire pp_lll = lb_a & lb_b;
    wire P0 = ma & mb;
    wire P1 = pp_aml ^ pp_alb;
    wire c1 = pp_aml & pp_alb;
    wire P2 = pp_lll ^ c1;
    wire P3 = pp_lll & c1;

    // Direct mag bits: mag[i] = OR_j (P[j] AND isK[i-j])
    wire mag0 = P0 & isK0;
    wire mag1 = (P1 & isK0) | (P0 & isK1);
    wire mag2 = (P2 & isK0) | (P1 & isK1) | (P0 & isK2);
    wire mag3 = (P3 & isK0) | (P2 & isK1) | (P1 & isK2) | (P0 & isK3);
    wire mag4 = (P3 & isK1) | (P2 & isK2) | (P1 & isK3) | (P0 & isK4);
    wire mag5 = (P3 & isK2) | (P2 & isK3) | (P1 & isK4);
    wire mag6 = (P3 & isK3) | (P2 & isK4);
    wire mag7 = P3 & isK4;
    wire [7:0] mag = {mag7, mag6, mag5, mag4, mag3, mag2, mag1, mag0};

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
