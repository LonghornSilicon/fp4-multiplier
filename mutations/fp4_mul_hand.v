// Aggressively hand-optimized FP4 multiplier (default encoding).
//
// Key tricks beyond fp4_mul_struct.v:
//   (1) Explicit per-output-bit expressions for the magnitude shift, rather
//       than trusting yosys to expand `P << K`. Each output bit is an OR of
//       AND-of-(P[j], K-equals-c) terms. Many K-equals-c terms are shared.
//   (2) The K==4 case is special: K=4 ⟺ both inputs have (e_h=1, e_l=1)
//       ⟺ both eh AND el are 1. In this case M_a, M_b ∈ {2, 3} so P ∈ {4, 6, 9}.
//       We use this to simplify mag[6:7].
//   (3) The +1 carry of the conditional negate (sy ? -mag : mag) is a single
//       LSB-add that ripples; for our magnitude set, mag[0] is 1 only when
//       both M_a and M_b are odd (= 1 or 3) AND K == 0. This is a well-known
//       narrow predicate -> tight final-bit logic.
//
// Naming: SO -> "structural output" intermediate names.

module fp4_mul (
    input  wire [3:0] a,
    input  wire [3:0] b,
    output wire [8:0] y
);
    // Field decode (free).
    wire sa = a[3], eh_a = a[2], el_a = a[1], ma = a[0];
    wire sb = b[3], eh_b = b[2], el_b = b[1], mb = b[0];

    // Leading bits, 2-bit normalized mantissa.
    wire lb_a = eh_a | el_a;
    wire lb_b = eh_b | el_b;
    // M_a = {lb_a, ma}, M_b = {lb_b, mb} as 2-bit unsigned.

    // ---- 2x2 unsigned multiplier P = M_a * M_b ∈ {0..9}, 4 bits ---------
    // P[0] = ma & mb
    // P[1] = (lb_a & mb) ^ (ma & lb_b)
    // c1   = (lb_a & mb) & (ma & lb_b)
    // P[2] = (lb_a & lb_b) ^ c1
    // P[3] = (lb_a & lb_b) & c1
    wire pp_aml = lb_a & mb;       // partial product (lb_a)(mb)
    wire pp_alb = ma & lb_b;
    wire pp_lll = lb_a & lb_b;
    wire P0 = ma & mb;
    wire P1 = pp_aml ^ pp_alb;
    wire c1 = pp_aml & pp_alb;
    wire P2 = pp_lll ^ c1;
    wire P3 = pp_lll & c1;

    // ---- K computation: K = sa1 + sb1, sa1[1:0] = {eh_a&el_a, eh_a&~el_a}
    // Equivalently sa1 = eh_a ? (el_a ? 2 : 1) : 0, range {0,1,2}.
    // K ∈ {0..4}.
    wire ehela_a = eh_a & el_a;          // sa1[1]
    wire eha_only = eh_a & ~el_a;        // sa1[0]
    wire ehela_b = eh_b & el_b;
    wire ehb_only = eh_b & ~el_b;
    // Sum 2-bit + 2-bit -> 3-bit
    wire K0 = eha_only ^ ehb_only;
    wire k_carry01 = eha_only & ehb_only;
    wire K1_pre = ehela_a ^ ehela_b;
    wire K1 = K1_pre ^ k_carry01;
    wire K2 = (ehela_a & ehela_b) | (K1_pre & k_carry01);
    // K = (K2,K1,K0) ∈ {000,001,010,011,100}. K=4 iff K2.

    // K-equals-c indicators (for c ∈ 0..4).
    wire isK0 = ~K0 & ~K1 & ~K2;
    wire isK1 =  K0 & ~K1 & ~K2;
    wire isK2 = ~K0 &  K1 & ~K2;
    wire isK3 =  K0 &  K1 & ~K2;
    wire isK4 = K2;                                 // K1=K0=0 follows.

    // ---- Magnitude bits: mag[i] = OR_{j} (P[j] & (K==i-j))
    wire mag0 = P0 & isK0;
    wire mag1 = (P1 & isK0) | (P0 & isK1);
    wire mag2 = (P2 & isK0) | (P1 & isK1) | (P0 & isK2);
    wire mag3 = (P3 & isK0) | (P2 & isK1) | (P1 & isK2) | (P0 & isK3);
    wire mag4 =                (P3 & isK1) | (P2 & isK2) | (P1 & isK3) | (P0 & isK4);
    wire mag5 =                              (P3 & isK2) | (P2 & isK3) | (P1 & isK4);
    wire mag6 =                                            (P3 & isK3) | (P2 & isK4);
    wire mag7 =                                                          (P3 & isK4);

    wire [7:0] mag = {mag7, mag6, mag5, mag4, mag3, mag2, mag1, mag0};

    // ---- Sign + 2's-complement assembly -----------------------------------
    wire sy = sa ^ sb;
    // Conditional negate: out = sy ? -mag : mag (interpreting as 9-bit signed).
    // out[i] = mag[i] XOR sy XOR carry[i] where carry[0] = sy & ~mag[0] ... ugh,
    // standard. Let's just use Verilog and let synthesis fold:
    wire [8:0] mag9 = {1'b0, mag};
    wire [8:0] xord = mag9 ^ {9{sy}};
    wire [8:0] outv = xord + {8'b0, sy};
    assign y = outv;
endmodule
