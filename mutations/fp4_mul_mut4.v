// Mutation 4 — Combine sign carry into K-shift's last column.
// Standard trick: when computing -mag (2's comp), we need NOT(mag) + 1.
// The +1 ripples through trailing zeros until the first 1-bit.
// Since mag = P << K, the lowest bit of mag is mag[0] = m_a AND m_b AND ~lb_a AND ~lb_b.
// For sy=0: out=mag. For sy=1: out=NOT(mag)+1.
// Bit 0: out[0]=mag[0] always. Bit 1: out[1] = (sy=0 ? mag[1] : ~mag[1] XOR (mag[0]==0))
// Direct implementation: out[i] = mag[i] XOR (sy AND OR(mag[i-1:0]))
// "OR(mag below) = mag is nonzero up to bit i-1" — note this is NOT the
// "below" of mut2; it's the complement.

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

    // "Bit i has any prior 1" running-OR
    wire below1_or = mag[0];
    wire below2_or = below1_or | mag[1];
    wire below3_or = below2_or | mag[2];
    wire below4_or = below3_or | mag[3];
    wire below5_or = below4_or | mag[4];
    wire below6_or = below5_or | mag[5];
    wire below7_or = below6_or | mag[6];
    wire below8_or = below7_or | mag[7];

    // out[i] = mag[i] XOR (sy AND below_i_or)
    // out[0] = mag[0] (no prior bits)
    assign y[0] = mag[0];
    assign y[1] = mag[1] ^ (sy & below1_or);
    assign y[2] = mag[2] ^ (sy & below2_or);
    assign y[3] = mag[3] ^ (sy & below3_or);
    assign y[4] = mag[4] ^ (sy & below4_or);
    assign y[5] = mag[5] ^ (sy & below5_or);
    assign y[6] = mag[6] ^ (sy & below6_or);
    assign y[7] = mag[7] ^ (sy & below7_or);
    assign y[8] = sy & below8_or;
endmodule
