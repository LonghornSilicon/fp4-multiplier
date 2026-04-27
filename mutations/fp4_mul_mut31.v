// Mutation 31 — One-hot K + direct SOP magnitude bits (no shifter, no
// below-chain). Shannon-expand the entire output on (K==0..4) instead
// of building mag and then post-processing.
//
// Structural innovation: the canonical form computes mag = P << K then
// ripples the negate. Here we expand each y[i] as a 5-way Shannon mux on
// K, where for each K-case the magnitude bits are shifted P bits and the
// 2's-complement negate is folded into the SAME cube SOP. This gives ABC
// one big SOP per output bit, which lets dch/dch -f find very different
// shared cubes than the canonical mag-then-negate layering.
//
// In each K-case we know which mag bits could be set, so the negate ladder
// per case has at most 4 nonzero bits — much shallower NAND than 7-deep.

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

    // 2x2 mul (7 gates, mut27 form).
    wire pp_aml = lb_a & mb;
    wire pp_alb = ma & lb_b;
    wire pp_lll = lb_a & lb_b;
    wire P0 = ma & mb;
    wire P1 = pp_aml ^ pp_alb;
    wire c1 = pp_aml & pp_alb;
    wire P2 = pp_lll ^ c1;
    wire P3 = c1;

    // K = sa1 + sb1, but instead of a 3-bit sum we build one-hot K.
    wire ehel_a = a[2] & el_a;     // sa1 = 2  (eh=1, el=1)
    wire eh_only_a = a[2] & ~el_a; // sa1 = 1  (eh=1, el=0)
    wire ehel_b = b[2] & el_b;
    wire eh_only_b = b[2] & ~el_b;
    wire saZ = ~a[2];              // sa1 = 0
    wire sbZ = ~b[2];

    // One-hot K (K=0..4). K = sa1 + sb1.
    //   K0 ⇔ saZ & sbZ
    //   K1 ⇔ (saZ & eh_only_b) | (eh_only_a & sbZ)
    //   K2 ⇔ (saZ & ehel_b) | (eh_only_a & eh_only_b) | (ehel_a & sbZ)
    //   K3 ⇔ (eh_only_a & ehel_b) | (ehel_a & eh_only_b)
    //   K4 ⇔ ehel_a & ehel_b
    wire K0 = saZ & sbZ;
    wire K1 = (saZ & eh_only_b) | (eh_only_a & sbZ);
    wire K2 = (saZ & ehel_b) | (eh_only_a & eh_only_b) | (ehel_a & sbZ);
    wire K3 = (eh_only_a & ehel_b) | (ehel_a & eh_only_b);
    wire K4 = ehel_a & ehel_b;

    // Magnitude bits as direct SOPs: mag[i] = OR_j (P_j & K_{i-j})
    // with P_j absent where j>i or i-j>4.
    wire mag0 = P0 & K0;
    wire mag1 = (P1 & K0) | (P0 & K1);
    wire mag2 = (P2 & K0) | (P1 & K1) | (P0 & K2);
    wire mag3 = (P3 & K0) | (P2 & K1) | (P1 & K2) | (P0 & K3);
    wire mag4 =             (P3 & K1) | (P2 & K2) | (P1 & K3) | (P0 & K4);
    wire mag5 =                         (P3 & K2) | (P2 & K3) | (P1 & K4);
    wire mag6 =                                     (P3 & K3) | (P2 & K4);
    wire mag7 =                                                 (P3 & K4);

    wire [7:0] mag = {mag7, mag6, mag5, mag4, mag3, mag2, mag1, mag0};

    // Conditional negate via standard XOR + LSB-add. Let synthesis fold
    // the +1 ripple into the SOP cubes — gives ABC freedom to pick a
    // very different gate set than the NAND-chain form.
    wire sy = sa ^ sb;
    wire [8:0] mag9 = {1'b0, mag};
    wire [8:0] xord = mag9 ^ {9{sy}};
    wire [8:0] outv = xord + {8'b0, sy};
    assign y = outv;
endmodule
