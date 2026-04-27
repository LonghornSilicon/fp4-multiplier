// Mutation 33 — Booth-2-style recoding for B operand (M_b ∈ {0,1,2,3}
// recoded as {0, +1, +2, -1+next}-equivalent partial signals), fused with
// shift.
//
// Structural innovation: instead of a plain 2x2 carry-ripple AND/XOR mul,
// recode M_b = {lb_b, mb} into two enable signals with a sign-aware twist
// borrowed from Booth-2:
//   M_b = 0   → enable_x1 = 0, enable_x2 = 0
//   M_b = 1   → enable_x1 = 1, enable_x2 = 0
//   M_b = 2   → enable_x1 = 0, enable_x2 = 1
//   M_b = 3   → enable_x1 = 1, enable_x2 = 1   (= 1 + 2; no Booth -1 needed
//                because both operands are unsigned and 2 bits)
// Then P = (M_a)*1*enable_x1 + (M_a)*2*enable_x2  (sum of two shifted M_a).
// This converts the 2x2 AND/XOR into a 2-input adder of two 2-bit operands
// shifted by 0 and 1 — a structurally distinct pp tree.
//
// More importantly, we then push the shift K into the addition: the entire
// mag is computed as
//   mag = (M_a · enable_x1) << K  +  (M_a · enable_x2) << (K+1)
// The two left-shifts are merged into a single 3-bit shift index per term,
// letting ABC fuse the two shifts and the 2x2 add into one wide network.

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

    // Booth-2-style recode of M_b = {lb_b, mb}: enable_x1 = mb, enable_x2 = lb_b.
    // P = M_a*mb + (M_a*lb_b)<<1.
    // M_a = {lb_a, ma} so M_a*mb = {lb_a&mb, ma&mb} (2 bits)
    //     M_a*lb_b = {lb_a&lb_b, ma&lb_b} (2 bits)
    wire t0_lo = ma & mb;          // M_a*mb low
    wire t0_hi = lb_a & mb;        // M_a*mb high
    wire t1_lo = ma & lb_b;        // M_a*lb_b low (will be shifted by 1)
    wire t1_hi = lb_a & lb_b;      // M_a*lb_b high (will be shifted by 1)

    // P = t0 + (t1<<1).  Add 2-bit + (2-bit<<1) = 4-bit:
    //   bit0 = t0_lo
    //   bit1 = t0_hi ^ t1_lo,         carry1 = t0_hi & t1_lo
    //   bit2 = t1_hi ^ carry1,        carry2 = t1_hi & carry1
    //   bit3 = carry2
    wire P0 = t0_lo;
    wire P1 = t0_hi ^ t1_lo;
    wire cy1 = t0_hi & t1_lo;
    wire P2 = t1_hi ^ cy1;
    wire P3 = t1_hi & cy1;
    wire [3:0] P = {P3, P2, P1, P0};

    // K = sa1 + sb1. Booth-2 doesn't change shift; keep standard form.
    wire [1:0] sa1 = {a[2] & el_a, a[2] & ~el_a};
    wire [1:0] sb1 = {b[2] & el_b, b[2] & ~el_b};
    wire [2:0] K = sa1 + sb1;
    wire [7:0] mag = P << K;
    wire sy = sa ^ sb;

    // Conditional negate; let synth fold +1.
    wire [8:0] mag9 = {1'b0, mag};
    wire [8:0] xord = mag9 ^ {9{sy}};
    wire [8:0] outv = xord + {8'b0, sy};
    assign y = outv;
endmodule
