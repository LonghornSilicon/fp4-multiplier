// FP4 multiplier — Baugh-Wooley-style folded conditional negate.
//
// Trick: the conditional negate "out = sy ? -mag : mag" requires a +1 ripple
// when sy = 1. We fold this into the structure as follows.
//
// Let sy = sa ^ sb. Define z[i] = mag[i] XOR sy. We want
//     out[i] = z[i] XOR carry[i],   carry[0] = sy.
// Note that for sy=0, all carries vanish and out = mag. For sy=1,
// carry[i] = AND_{j<i} ~mag[j] = 1 iff mag[0..i-1] are all zero, i.e., the
// "first nonzero bit hasn't happened yet".
//
// Equivalently:
//   out[i] = mag[i] XOR sy XOR (sy AND (mag[0..i-1] all zero))
//          = mag[i] XOR (sy AND (mag[0..i] not all zero))   ... when sy=1
//   AND for sy=0, out[i] = mag[i].
//
// Simpler equivalent (this IS the standard "negation by complement-up-to-and-
// including-the-lowest-set-bit" rule):
//   out[i] = mag[i] when i ≤ first-set-bit, else NOT(mag[i]).
//
// We compute "is-last-zero[i] = NOR(mag[0..i-1])" iteratively. Sharing across
// bits keeps the gate count tight.
//
// Default encoding only.

module fp4_mul (
    input  wire [3:0] a,
    input  wire [3:0] b,
    output wire [8:0] y
);
    wire sa = a[3], eh_a = a[2], el_a = a[1], ma = a[0];
    wire sb = b[3], eh_b = b[2], el_b = b[1], mb = b[0];
    wire lb_a = eh_a | el_a;
    wire lb_b = eh_b | el_b;

    // 2x2 unsigned mul P = M_a * M_b ∈ {0..9}
    wire pp_aml = lb_a & mb;
    wire pp_alb = ma & lb_b;
    wire pp_lll = lb_a & lb_b;
    wire P0 = ma & mb;
    wire P1 = pp_aml ^ pp_alb;
    wire c1 = pp_aml & pp_alb;
    wire P2 = pp_lll ^ c1;
    wire P3 = pp_lll & c1;

    // K = sa1 + sb1 (2-bit values in {0,1,2}); range {0..4}.
    wire ehela_a = eh_a & el_a;
    wire eha_only = eh_a & ~el_a;
    wire ehela_b = eh_b & el_b;
    wire ehb_only = eh_b & ~el_b;
    wire K0 = eha_only ^ ehb_only;
    wire k_carry01 = eha_only & ehb_only;
    wire K1_pre = ehela_a ^ ehela_b;
    wire K1 = K1_pre ^ k_carry01;
    wire K2 = (ehela_a & ehela_b) | (K1_pre & k_carry01);

    wire isK0 = ~K0 & ~K1 & ~K2;
    wire isK1 =  K0 & ~K1 & ~K2;
    wire isK2 = ~K0 &  K1 & ~K2;
    wire isK3 =  K0 &  K1 & ~K2;
    wire isK4 = K2;

    // Magnitude bits 0..7 (mag[i] = sum of P[j] AND (K==i-j)).
    wire mag0 = P0 & isK0;
    wire mag1 = (P1 & isK0) | (P0 & isK1);
    wire mag2 = (P2 & isK0) | (P1 & isK1) | (P0 & isK2);
    wire mag3 = (P3 & isK0) | (P2 & isK1) | (P1 & isK2) | (P0 & isK3);
    wire mag4 = (P3 & isK1) | (P2 & isK2) | (P1 & isK3) | (P0 & isK4);
    wire mag5 = (P3 & isK2) | (P2 & isK3) | (P1 & isK4);
    wire mag6 = (P3 & isK3) | (P2 & isK4);
    wire mag7 =  P3 & isK4;

    wire sy = sa ^ sb;

    // Baugh-Wooley-folded conditional negate.
    //
    // For sy = 0:  out[i] = mag[i]  (i = 0..7),  out[8] = 0
    // For sy = 1:  invert mag bits ABOVE the lowest 1, keep at-and-below.
    //              out[8] = 1 iff mag != 0.
    //
    // Encode "all bits below i are zero" iteratively.
    wire below0 = 1'b1;                      // trivially: no bits below 0
    wire below1 = ~mag0;                     // mag[0] is zero
    wire below2 = ~mag0 & ~mag1;
    wire below3 = below2 & ~mag2;
    wire below4 = below3 & ~mag3;
    wire below5 = below4 & ~mag4;
    wire below6 = below5 & ~mag5;
    wire below7 = below6 & ~mag6;
    wire below8 = below7 & ~mag7;            // = 1 iff mag == 0

    // out[i] = sy ? (below_i ? mag[i] : ~mag[i]) : mag[i]
    //        = mag[i] XOR (sy AND ~below_i)
    //
    // For i = 0: below0 = 1 -> out[0] = mag[0] always
    // For i ≥ 1: out[i] = mag[i] XOR (sy AND ~below_i)
    wire flip1 = sy & ~below1;
    wire flip2 = sy & ~below2;
    wire flip3 = sy & ~below3;
    wire flip4 = sy & ~below4;
    wire flip5 = sy & ~below5;
    wire flip6 = sy & ~below6;
    wire flip7 = sy & ~below7;
    wire flip8 = sy & ~below8;        // = sy AND (mag != 0)

    assign y[0] = mag0;
    assign y[1] = mag1 ^ flip1;
    assign y[2] = mag2 ^ flip2;
    assign y[3] = mag3 ^ flip3;
    assign y[4] = mag4 ^ flip4;
    assign y[5] = mag5 ^ flip5;
    assign y[6] = mag6 ^ flip6;
    assign y[7] = mag7 ^ flip7;
    assign y[8] = flip8;     // = sy AND (mag != 0); for sy=0 -> 0, for sy=1 -> 1 iff mag != 0
endmodule
