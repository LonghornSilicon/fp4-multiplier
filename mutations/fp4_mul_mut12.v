// Mutation 12 — also hardcode Y[7] when achievable.
// mag[7] = 1 only when K=4 AND P=8or9 ... actually K=4 AND P[3]=1 means P=8 or 9.
// P=8 needs M_a*M_b=8 — impossible (max M_a*M_b=9, P=8 not in our set {0,1,2,3,4,6,9}).
// So mag[7]=1 ⟺ K=4 AND P=9.
// P=9 ⟺ M_a=M_b=3 ⟺ both inputs have lb=1 AND m=1
// K=4 ⟺ both inputs have eh=1 AND el=1
// ⟹ both inputs have all 3 lower bits =1 in the *encoded* sense (lb,eh,el,m all 1)
// Under remap σ: this means both inputs have lb=1 AND m=1 AND eh=1 AND el=1.
// In raw bits for σ=(0,1,2,3,6,7,4,5):
//   lb=1: a[1]|a[2]=1
//   m=1: a[0]=1
//   eh=1: a[2]=1
//   el=1: a[1]^a[2]=1, with a[2]=1, this means a[1]=0
//   Combined: a[0]=1 AND a[1]=0 AND a[2]=1
// So mag[7]=1 ⟺ a[0]&~a[1]&a[2] AND b[0]&~b[1]&b[2].
// y[7] = mag[7] XOR flip[7] under conditional negate. flip[7] = sy & ~below7.

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
    // Y[8]: raw-bit P_nonzero
    assign y[8] = sy & (a[0] | a[1] | a[2]) & (b[0] | b[1] | b[2]);
endmodule
