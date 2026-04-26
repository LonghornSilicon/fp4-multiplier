// Structurally-explicit FP4 multiplier (default encoding).
//
// This Verilog exposes the sign-magnitude / leading-bit / 2x2 mantissa-product
// / variable-shift / two's-complement structure that an behaviorial case-stmt
// description hides from the synthesizer.
//
// Encoding (default Etched MX-FP4 / E2M1):
//   bit 3 = sign
//   bits[2:1] = exponent (00,01 = subnormal/normal-1; 10 = normal-2; 11 = norm-3)
//   bit 0 = mantissa
//
// Magnitude: val = (e==0 ? m : 2+m) * 2^(e==0 ? -1 : e-2)
// 4*|val|*4*|val| = M_a * M_b * 2^K   where
//   M_i  = (e_i!=0 ? 2 : 0) + m_i ∈ {0,1,2,3}
//   K    = shift_a + shift_b + 2; shift_i = e_i!=0 ? e_i-2 : -1
//          K = 0 (both subnormal/e=1)..4 (both e=3)
//
// Output magnitude = M_a*M_b shifted left by K, in [0..144].
// Sign = sign_a XOR sign_b (zero result is invariant under sign flip via the
// two's-complement +1 carry trick — handled automatically below).

module fp4_mul (
    input  wire [3:0] a,
    input  wire [3:0] b,
    output wire [8:0] y
);
    // Decode fields.
    wire sa = a[3];
    wire eh_a = a[2];
    wire el_a = a[1];
    wire ma = a[0];
    wire sb = b[3];
    wire eh_b = b[2];
    wire el_b = b[1];
    wire mb = b[0];

    // Leading bits (== "is normal" == "is val ≥ 1 in magnitude")
    wire lb_a = eh_a | el_a;
    wire lb_b = eh_b | el_b;

    // 2-bit normalized mantissa: M_i = {lb_i, m_i} ∈ {0,1,2,3}
    // Magnitude product M_a*M_b ∈ {0,1,2,3,4,6,9}: a 2x2 unsigned multiplier.
    // Output P[3:0] = M_a * M_b
    wire [1:0] Ma = {lb_a, ma};
    wire [1:0] Mb = {lb_b, mb};
    wire [3:0] P = Ma * Mb;     // 4-bit product (max 9)

    // Variable left-shift K = shift_a + shift_b + 2 ∈ {0..4}.
    // shift_i = eh_i ? el_i : -1, so shift_i + 1 = eh_i ? (el_i+1) : 0
    //   eh=0,el=0 -> 0
    //   eh=0,el=1 -> 0
    //   eh=1,el=0 -> 1
    //   eh=1,el=1 -> 2
    // i.e. (shift_i+1)[1:0] = {eh_i & el_i, eh_i & ~el_i}.
    wire [1:0] sa1 = {eh_a & el_a, eh_a & ~el_a};
    wire [1:0] sb1 = {eh_b & el_b, eh_b & ~el_b};
    wire [2:0] K = sa1 + sb1;   // K ∈ {0..4}, fits in 3 bits

    // Shift the 4-bit product left by K. Result is at most 9*16 = 144,
    // which fits in 8 bits.
    wire [7:0] mag = P << K;

    // Sign of result.
    wire sy = sa ^ sb;

    // Output: 9-bit two's complement = sy ? -mag : mag.
    // Implementation: zero-extend mag to 9 bits, XOR every bit with sy, add sy.
    wire [8:0] mag9 = {1'b0, mag};
    wire [8:0] xord = mag9 ^ {9{sy}};
    wire [8:0] outv = xord + {8'b0, sy};   // +sy at LSB
    assign y = outv;
endmodule
