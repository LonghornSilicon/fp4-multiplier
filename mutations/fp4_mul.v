// Behavioural reference: FP4 (E2M1, no inf/NaN, ignore signed zero) multiplier.
// Output: 9-bit two's-complement integer = 4 * val(a) * val(b).
// LSB of output represents 0.25 (this is the QI9 format).
// IMPORTANT: this file uses the DEFAULT input encoding from the Etched spec.
// Synthesis runs may also feed remapped encodings; those are produced at the
// Python level by re-ordering the case-statement entries before invoking yosys.

module fp4_mul (
    input  wire [3:0] a,
    input  wire [3:0] b,
    output wire [8:0] y
);
    // Decode each FP4 code to its represented value scaled by 4 so we stay in
    // integer arithmetic. We then compute 4*val_a*val_b = (4*val_a)*(4*val_b)/4
    // — but synthesizers will collapse this to the truth table anyway.
    reg signed [3:0] sa, sb;        // 4*val_a fits in 4 signed bits (range -24..+24 ... actually +24=0b11000=-8 in 4-bit; need 6 bits)
    reg signed [5:0] xa, xb;        // safe width for 4*val (range -24..+24)

    always @* begin
        case (a)
            4'b0000: xa = 6'sd0;     // 0
            4'b0001: xa = 6'sd2;     // 0.5  -> 4*0.5 = 2
            4'b0010: xa = 6'sd4;     // 1    -> 4
            4'b0011: xa = 6'sd6;     // 1.5  -> 6
            4'b0100: xa = 6'sd8;     // 2    -> 8
            4'b0101: xa = 6'sd12;    // 3    -> 12
            4'b0110: xa = 6'sd16;    // 4    -> 16
            4'b0111: xa = 6'sd24;    // 6    -> 24
            4'b1000: xa = 6'sd0;     // -0
            4'b1001: xa = -6'sd2;
            4'b1010: xa = -6'sd4;
            4'b1011: xa = -6'sd6;
            4'b1100: xa = -6'sd8;
            4'b1101: xa = -6'sd12;
            4'b1110: xa = -6'sd16;
            4'b1111: xa = -6'sd24;
            default: xa = 6'sd0;
        endcase
        case (b)
            4'b0000: xb = 6'sd0;
            4'b0001: xb = 6'sd2;
            4'b0010: xb = 6'sd4;
            4'b0011: xb = 6'sd6;
            4'b0100: xb = 6'sd8;
            4'b0101: xb = 6'sd12;
            4'b0110: xb = 6'sd16;
            4'b0111: xb = 6'sd24;
            4'b1000: xb = 6'sd0;
            4'b1001: xb = -6'sd2;
            4'b1010: xb = -6'sd4;
            4'b1011: xb = -6'sd6;
            4'b1100: xb = -6'sd8;
            4'b1101: xb = -6'sd12;
            4'b1110: xb = -6'sd16;
            4'b1111: xb = -6'sd24;
            default: xb = 6'sd0;
        endcase
    end

    wire signed [11:0] prod = xa * xb;          // (4*val_a)*(4*val_b) = 16*val_a*val_b
    // Output we want is 4*val_a*val_b = prod / 4. prod is always divisible by 4
    // (since at least one factor of 4 per side multiplied them by ≥ 4 already).
    wire signed [9:0] shifted = prod >>> 2;     // arithmetic right shift by 2
    assign y = shifted[8:0];
endmodule
