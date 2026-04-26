// Mutation 21 — kill the mag[0..7] vector, work directly with shifted mag bits.
// Since mag = P << K, each mag[i] = P[i-K] when i ≥ K. Express directly.

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

    // K-equals-c indicators (1-hot)
    wire sa1_0 = ~a[2];
    wire sa1_1 = a[2] & a[1];
    wire sa1_2 = a[2] & ~a[1];
    wire sb1_0 = ~b[2];
    wire sb1_1 = b[2] & b[1];
    wire sb1_2 = b[2] & ~b[1];
    wire isK0 = sa1_0 & sb1_0;
    wire isK1 = (sa1_1 & sb1_0) | (sa1_0 & sb1_1);
    wire isK2 = (sa1_2 & sb1_0) | (sa1_1 & sb1_1) | (sa1_0 & sb1_2);
    wire isK3 = (sa1_2 & sb1_1) | (sa1_1 & sb1_2);
    wire isK4 = sa1_2 & sb1_2;

    wire mag0 = P0 & isK0;
    wire mag1 = (P1 & isK0) | (P0 & isK1);
    wire mag2 = (P2 & isK0) | (P1 & isK1) | (P0 & isK2);
    wire mag3 = (P3 & isK0) | (P2 & isK1) | (P1 & isK2) | (P0 & isK3);
    wire mag4 = (P3 & isK1) | (P2 & isK2) | (P1 & isK3) | (P0 & isK4);
    wire mag5 = (P3 & isK2) | (P2 & isK3) | (P1 & isK4);
    wire mag6 = (P3 & isK3) | (P2 & isK4);
    wire mag7 = P3 & isK4;

    wire sy = sa ^ sb;

    wire below1 = ~mag0;
    wire below2 = below1 & ~mag1;
    wire below3 = below2 & ~mag2;
    wire below4 = below3 & ~mag3;
    wire below5 = below4 & ~mag4;
    wire below6 = below5 & ~mag5;
    wire below7 = below6 & ~mag6;

    assign y[0] = mag0;
    assign y[1] = mag1 ^ (sy & ~below1);
    assign y[2] = mag2 ^ (sy & ~below2);
    assign y[3] = mag3 ^ (sy & ~below3);
    assign y[4] = mag4 ^ (sy & ~below4);
    assign y[5] = mag5 ^ (sy & ~below5);
    assign y[6] = mag6 ^ (sy & ~below6);
    assign y[7] = mag7 ^ (sy & ~below7);
    assign y[8] = sy & (a[0] | a[1] | a[2]) & (b[0] | b[1] | b[2]);
endmodule
