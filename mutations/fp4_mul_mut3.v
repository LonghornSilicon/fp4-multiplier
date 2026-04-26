// Mutation 3 — Booth-recoded sign-magnitude.
// Idea: compute (sa ? -val_a : val_a) × (sb ? -val_b : val_b) directly using
// signed multiplication of small operands. yosys/ABC will emit a Booth-style
// signed multiplier which may be tighter than the unsigned-then-negate path.

module fp4_mul (
    input  wire [3:0] a,
    input  wire [3:0] b,
    output wire [8:0] y
);
    // Magnitude (4·|val|) as 5-bit unsigned
    // 4·|val| ∈ {0, 2, 4, 6, 8, 12, 16, 24} encoded:
    // (eh, el, m) -> 4·|val|
    // Under remap σ=(0,1,2,3,6,7,4,5):
    // codes  001:0.5  →2,  010:1→4,  011:1.5→6
    // 100:2→8 — wait, here perm[4]=6 so codes 100 has val=4, so 4·val=16
    // Actually let me enumerate via fields:
    //   code 000: val=0,   4|val|=0
    //   code 001: val=0.5, 4|val|=2
    //   code 010: val=1,   4|val|=4
    //   code 011: val=1.5, 4|val|=6
    //   code 100: val=4,   4|val|=16
    //   code 101: val=6,   4|val|=24
    //   code 110: val=2,   4|val|=8
    //   code 111: val=3,   4|val|=12

    // Decode 4·|val_a| as 5-bit unsigned via SOP
    wire [4:0] mag_a, mag_b;
    // mag[0]=0 always; mag[1]=1 iff 4|val|∈{2,6} i.e. codes 001,011 i.e. m=1, lb=lb_a (since lb=0,m=1 or lb=1,m=1 for those)... let me just use case
    // For elegance, do raw assignment:
    function [4:0] decode_mag;
        input [2:0] code;
        case (code)
            3'b000: decode_mag = 5'd0;
            3'b001: decode_mag = 5'd2;
            3'b010: decode_mag = 5'd4;
            3'b011: decode_mag = 5'd6;
            3'b100: decode_mag = 5'd16;
            3'b101: decode_mag = 5'd24;
            3'b110: decode_mag = 5'd8;
            3'b111: decode_mag = 5'd12;
        endcase
    endfunction
    assign mag_a = decode_mag(a[2:0]);
    assign mag_b = decode_mag(b[2:0]);

    // Sign-extend & conditional negate to 6-bit signed
    wire signed [5:0] sval_a = a[3] ? -{1'b0, mag_a} : {1'b0, mag_a};
    wire signed [5:0] sval_b = b[3] ? -{1'b0, mag_b} : {1'b0, mag_b};

    // Signed multiplication: 6-bit × 6-bit = 12-bit signed
    wire signed [11:0] prod = sval_a * sval_b;
    // We multiplied 4·val_a × 4·val_b = 16·val_a·val_b. Output should be 4·val_a·val_b = prod / 4.
    wire signed [9:0] shifted = prod >>> 2;
    assign y = shifted[8:0];
endmodule
