// Mutation 1 — Y[0] direct passthrough.
// Observation: out[0] = mag[0] always (negation of an integer doesn't change LSB).
// And mag[0] = m_a AND m_b AND ~lb_a AND ~lb_b under our encoding.
// Hardcoding y[0] separately may free ABC to optimize the rest.

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

    // 2x2 mul partial products
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

    // y[0] passthrough — does not need conditional negate (LSB invariant under negation)
    assign y[0] = mag[0];

    // Bits 1..7: conditional negate
    wire [7:1] mag_hi = mag[7:1];
    wire [7:1] xord = mag_hi ^ {7{sy}};
    // Add sy at position 0 of the magnitude — but bit 0 already = mag[0],
    // so the carry into bit 1 is (mag[0] AND sy)? No — we're computing
    // 9-bit two's complement of (sign-extended mag). Standard form:
    //   out[i] = (mag[i] ^ sy) ^ carry[i]
    //   carry[i+1] = (mag[i] ^ sy) & carry[i]
    //   carry[0] = sy
    // We don't expose this directly; just trust the synthesizer:
    wire [8:0] mag9 = {1'b0, mag};
    wire [8:0] xord9 = mag9 ^ {9{sy}};
    wire [8:0] outv = xord9 + {8'b0, sy};
    assign y[8:1] = outv[8:1];
endmodule
