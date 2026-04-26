// Mutation 22 — express magnitude path via "mid-product" intermediate
// instead of P << K. Compute (4·val_a) * (4·val_b) at integer level via the
// raw bits, then shift right by 2.
// Under σ=(0,1,2,3,6,7,4,5):  val · 4 in raw bits:
//   0000 → 0    0001 → 2    0010 → 4    0011 → 6
//   0100 → 16   0101 → 24   0110 → 8    0111 → 12
// As 5-bit unsigned:
//   bit0 = 0 always
//   bit1 = m AND ~lb (= a[0] & ~(a[1]|a[2]) = a[0] & ~a[1] & ~a[2])
//   bit2 = m AND lb_low (depends on remap details)
//   ...
// Full lookup needed. Let yosys do it via case statement.

module fp4_mul (
    input  wire [3:0] a,
    input  wire [3:0] b,
    output wire [8:0] y
);
    // 4*|val| as 5-bit unsigned (under σ=(0,1,2,3,6,7,4,5))
    function [4:0] q4val;
        input [2:0] code;
        case (code)
            3'b000: q4val = 5'd0;     // val=0
            3'b001: q4val = 5'd2;     // val=0.5
            3'b010: q4val = 5'd4;     // val=1
            3'b011: q4val = 5'd6;     // val=1.5
            3'b100: q4val = 5'd16;    // val=4
            3'b101: q4val = 5'd24;    // val=6
            3'b110: q4val = 5'd8;     // val=2
            3'b111: q4val = 5'd12;    // val=3
        endcase
    endfunction
    wire [4:0] qa = q4val(a[2:0]);
    wire [4:0] qb = q4val(b[2:0]);
    // (4*|val_a|) * (4*|val_b|) = 16 * |val_a| * |val_b|, fits in 10 bits
    // Output we want = 4 * val_a * val_b, signed, 9 bits.
    // |output| = product / 4
    wire [9:0] qprod = qa * qb;
    wire [7:0] mag = qprod[9:2];

    wire sy = a[3] ^ b[3];

    // mut2 NAND-chain
    wire below1 = ~mag[0];
    wire below2 = below1 & ~mag[1];
    wire below3 = below2 & ~mag[2];
    wire below4 = below3 & ~mag[3];
    wire below5 = below4 & ~mag[4];
    wire below6 = below5 & ~mag[5];
    wire below7 = below6 & ~mag[6];

    assign y[0] = mag[0];
    assign y[1] = mag[1] ^ (sy & ~below1);
    assign y[2] = mag[2] ^ (sy & ~below2);
    assign y[3] = mag[3] ^ (sy & ~below3);
    assign y[4] = mag[4] ^ (sy & ~below4);
    assign y[5] = mag[5] ^ (sy & ~below5);
    assign y[6] = mag[6] ^ (sy & ~below6);
    assign y[7] = mag[7] ^ (sy & ~below7);
    assign y[8] = sy & (a[0] | a[1] | a[2]) & (b[0] | b[1] | b[2]);
endmodule
