// Mutation 34 — Shannon-expand the whole output on sy (sign).
//
// Structural innovation: the canonical form derives mag, then conditionally
// negates. Here we Shannon-expand each y[i] on sy itself:
//   y[i] = (~sy & mag[i]) | (sy & negmag[i])
// where negmag = -mag (mod 2^9). We give ABC both halves explicitly and
// let it find the shared cube structure between mag and negmag — which is
// surprisingly large because mag is sparse (only some K-shifts populate
// each bit) and negmag = ~mag + 1 has a closed-form per bit:
//   negmag[i] = mag[i] XOR above_i, with above_0 = 0
// where above_i = OR of mag[0..i-1]. The Shannon mux on sy then becomes
//   y[i] = mag[i] XOR (sy & above_i)
// SAME algebra as before — but the key structural twist is that we ALSO
// give Y[8] (the sign-overflow bit) as the same Shannon form:
//   y[8] = (~sy & 0) | (sy & (mag != 0)) = sy & above_8
// AND we name above_8 = above_7 | mag[7] explicitly, sharing the OR ladder
// with all the y[i] toggles. So the OR chain feeds 8 consumers (y[1..8])
// instead of 7, which is a different fanout topology than mut1-29.
//
// Additionally, we use a depth-2 OR tree on (a[0]|a[1]|a[2]) and
// (b[0]|b[1]|b[2]) and explicitly name a_nz / b_nz wires so that ABC can
// reuse them with the K-detector lb_a|ma, lb_b|mb cones.

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

    // Shared "operand is nonzero" wires (also = lb|m).
    wire a_nz = a[0] | lb_a;       // = a[0]|a[1]|a[2]
    wire b_nz = b[0] | lb_b;

    // 7-gate 2x2.
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

    // OR-prefix "above" detector — feeds 8 consumers (y[1..8]).
    wire above1 = mag[0];
    wire above2 = above1 | mag[1];
    wire above3 = above2 | mag[2];
    wire above4 = above3 | mag[3];
    wire above5 = above4 | mag[4];
    wire above6 = above5 | mag[5];
    wire above7 = above6 | mag[6];
    wire above8 = above7 | mag[7];   // = (mag != 0) = a_nz & b_nz

    // Shannon-expanded y[i] in unified form: y[i] = mag[i] XOR (sy & above_i).
    assign y[0] = mag[0];
    assign y[1] = mag[1] ^ (sy & above1);
    assign y[2] = mag[2] ^ (sy & above2);
    assign y[3] = mag[3] ^ (sy & above3);
    assign y[4] = mag[4] ^ (sy & above4);
    assign y[5] = mag[5] ^ (sy & above5);
    assign y[6] = mag[6] ^ (sy & above6);
    assign y[7] = mag[7] ^ (sy & above7);
    // Y[8]: same OR-prefix ladder. Note above8 = a_nz & b_nz logically;
    // give ABC BOTH expressions and let it pick whichever shares more.
    assign y[8] = sy & a_nz & b_nz;
endmodule
