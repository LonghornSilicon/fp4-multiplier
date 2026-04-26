// FP4 multiplier — hierarchical decomposition (magnitude submodule, negate at top).
// Hypothesis: yosys+ABC may find different local optima with explicit module
// boundaries, even when `flatten` is applied later.

module mag_compute (
    input  wire eh_a, el_a, ma,
    input  wire eh_b, el_b, mb,
    output wire [7:0] mag
);
    wire lb_a = eh_a | el_a;
    wire lb_b = eh_b | el_b;
    wire [1:0] Ma = {lb_a, ma};
    wire [1:0] Mb = {lb_b, mb};
    wire [3:0] P = Ma * Mb;
    wire [1:0] sa1 = {eh_a & el_a, eh_a & ~el_a};
    wire [1:0] sb1 = {eh_b & el_b, eh_b & ~el_b};
    wire [2:0] K = sa1 + sb1;
    assign mag = P << K;
endmodule


module fp4_mul (
    input  wire [3:0] a,
    input  wire [3:0] b,
    output wire [8:0] y
);
    wire [7:0] mag;
    mag_compute mc (
        .eh_a(a[2]), .el_a(a[1]), .ma(a[0]),
        .eh_b(b[2]), .el_b(b[1]), .mb(b[0]),
        .mag(mag)
    );
    wire sy = a[3] ^ b[3];
    wire [8:0] mag9 = {1'b0, mag};
    wire [8:0] xord = mag9 ^ {9{sy}};
    wire [8:0] outv = xord + {8'b0, sy};
    assign y = outv;
endmodule
