// Raw-bit FP4 multiplier (uses the σ=(0,1,2,3,6,7,4,5) remap implicitly).
//
// Under that remap:
//   sign = a[3]                            (unchanged)
//   eh   = a[2]                            (unchanged)
//   el   = a[1] XOR a[2]                   (XOR-decoded)
//   m    = a[0]                            (unchanged)
// Therefore:
//   lb = eh | el = a[2] | (a[1]^a[2]) = a[1] | a[2]   (no XOR needed!)
// The leading-bit collapses to a clean OR of raw input bits, saving a gate.
//
// More generally, expressing the multiplier directly in raw bits gives
// ABC a starting AIG that already has the remap savings absorbed.

module fp4_mul (
    input  wire [3:0] a,
    input  wire [3:0] b,
    output wire [8:0] y
);
    // Logical fields (under the σ remap), expressed in raw input bits where
    // possible. lb is the cleanest win: OR of two raw bits.
    wire sa = a[3], sb = b[3];
    wire eh_a = a[2], eh_b = b[2];
    wire ma = a[0], mb = b[0];
    wire lb_a = a[1] | a[2];          // = eh_a | el_a after remap
    wire lb_b = b[1] | b[2];
    // el is needed only for K computation:
    wire el_a = a[1] ^ a[2];
    wire el_b = b[1] ^ b[2];

    // 2x2 mantissa multiplier P = M_a * M_b ∈ {0,1,2,3,4,6,9}
    wire pp_aml = lb_a & mb;
    wire pp_alb = ma & lb_b;
    wire pp_lll = lb_a & lb_b;
    wire P0 = ma & mb;
    wire P1 = pp_aml ^ pp_alb;
    wire c1 = pp_aml & pp_alb;
    wire P2 = pp_lll ^ c1;
    wire P3 = pp_lll & c1;
    wire [3:0] P = {P3, P2, P1, P0};

    // K = sa1 + sb1, sa1 = (eh_a&el_a)·2 + (eh_a&~el_a)·1 = eh_a·(1+el_a)
    wire [1:0] sa1 = {eh_a & el_a, eh_a & ~el_a};
    wire [1:0] sb1 = {eh_b & el_b, eh_b & ~el_b};
    wire [2:0] K = sa1 + sb1;

    wire [7:0] mag = P << K;

    // Sign + 2's-comp negate.
    wire sy = sa ^ sb;
    wire [8:0] mag9 = {1'b0, mag};
    wire [8:0] xord = mag9 ^ {9{sy}};
    wire [8:0] outv = xord + {8'b0, sy};
    assign y = outv;
endmodule
