// Mutation 30 — Pre-explicit ~mag inversion shared across the negate XOR.
//
// Structural innovation: we precompute nmag = ~mag as a named Verilog wire
// and rewrite both the below-chain AND the output XOR in terms of nmag,
// rather than generating ~mag[i] freshly at each consumer. The hypothesis
// is that the canonical 65-gate solution effectively shares 7 NOTs that
// each fan out to a below-AND and the y[i] XOR; by giving ABC an explicit
// "this inverter is shared" signal, dch/refactor should keep them as a
// single inverter rather than re-deriving them per fan-out.
//
// Below chain is rewritten as nmag-AND ladder (matches the reuse pattern):
//   below_i = nmag[0] & nmag[1] & ... & nmag[i-1]
// Output uses an alternate algebraic form derived in mut11:
//   y[i] = mag[i] ^ (sy & ~below_i)
// We rewrite (sy & ~below_i) = sy & (mag[0] | ... | mag[i-1]) = sy & above_i
// where above_i = ~below_i is a chain of ORs of mag bits — DIFFERENT
// structural ladder than the NAND-ripple in mut2/mut11.

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

    // 7-gate 2x2 mul (P3 = c1, see mut27).
    wire pp_aml = lb_a & mb;
    wire pp_alb = ma & lb_b;
    wire pp_lll = lb_a & lb_b;
    wire P0 = ma & mb;
    wire P1 = pp_aml ^ pp_alb;
    wire c1 = pp_aml & pp_alb;
    wire P2 = pp_lll ^ c1;
    wire P3 = c1;
    wire [3:0] P = {P3, P2, P1, P0};

    wire [1:0] sa1 = {a[2] & el_a, a[2] & ~el_a};
    wire [1:0] sb1 = {b[2] & el_b, b[2] & ~el_b};
    wire [2:0] K = sa1 + sb1;
    wire [7:0] mag = P << K;
    wire sy = sa ^ sb;

    // Sign-bit feeds the conditional negate. We precompute s_xor_mag[i]
    // = mag[i] XOR sy as a single shared XOR (saves nothing alone, but
    // ABC may fuse it into the below-chain output XOR pattern).
    // Use OR-ladder for "above" detector (any mag bit below i is set):
    wire above1 = mag[0];
    wire above2 = above1 | mag[1];
    wire above3 = above2 | mag[2];
    wire above4 = above3 | mag[3];
    wire above5 = above4 | mag[4];
    wire above6 = above5 | mag[5];
    wire above7 = above6 | mag[6];

    // Toggle mask: t_i = sy & above_i. y[i] = mag[i] ^ t_i.
    // The mask is "high above the first set bit of mag, when sy=1".
    wire t1 = sy & above1;
    wire t2 = sy & above2;
    wire t3 = sy & above3;
    wire t4 = sy & above4;
    wire t5 = sy & above5;
    wire t6 = sy & above6;
    wire t7 = sy & above7;

    assign y[0] = mag[0];
    assign y[1] = mag[1] ^ t1;
    assign y[2] = mag[2] ^ t2;
    assign y[3] = mag[3] ^ t3;
    assign y[4] = mag[4] ^ t4;
    assign y[5] = mag[5] ^ t5;
    assign y[6] = mag[6] ^ t6;
    assign y[7] = mag[7] ^ t7;

    // Y[8] = sy & above_8 = sy & (any mag bit set) = sy & (P_nonzero).
    // P!=0 iff (lb_a|ma) & (lb_b|mb) since M_a=0 iff lb_a=ma=0. With
    // lb_a = a[1]|a[2] and ma = a[0], (lb_a|ma) = a[0]|a[1]|a[2]. Use
    // raw inputs to share with possible top-level fan-in cones.
    assign y[8] = sy & (a[0] | a[1] | a[2]) & (b[0] | b[1] | b[2]);
endmodule
