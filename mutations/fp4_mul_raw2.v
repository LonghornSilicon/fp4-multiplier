// Raw-bit FP4 multiplier v2 — aggressive simplifications under σ=(0,1,2,3,6,7,4,5).
//
// Under that remap, the structural multiplier's intermediates collapse to
// raw bits with no decoder XOR:
//   sa1[1] = eh_a & el_a       = (a[2]) & (a[1]^a[2])  =  a[2] & ~a[1]
//   sa1[0] = eh_a & ~el_a      = (a[2]) & ~(a[1]^a[2]) =  a[1] & a[2]
//   lb_a   = eh_a | el_a       = a[2] | (a[1]^a[2])    =  a[1] | a[2]
// Note sa1[1] + sa1[0] = a[2] (mutex on a[1]); lb_a OR-includes both.
// We never compute el explicitly — kill the XOR in the decode entirely.

module fp4_mul (
    input  wire [3:0] a,
    input  wire [3:0] b,
    output wire [8:0] y
);
    wire sa = a[3], sb = b[3];
    wire ma = a[0], mb = b[0];

    // Logical "leading bit" via raw OR — saves the XOR and a gate.
    wire lb_a = a[1] | a[2];
    wire lb_b = b[1] | b[2];

    // 2x2 mantissa product (M_a, M_b ∈ {0,1,2,3} via {lb, m})
    wire pp_aml = lb_a & mb;
    wire pp_alb = ma & lb_b;
    wire pp_lll = lb_a & lb_b;
    wire P0 = ma & mb;
    wire P1 = pp_aml ^ pp_alb;
    wire c1 = pp_aml & pp_alb;
    wire P2 = pp_lll ^ c1;
    wire P3 = pp_lll & c1;
    wire [3:0] P = {P3, P2, P1, P0};

    // K computation via raw bits: sa1[1]=a[2]&~a[1], sa1[0]=a[1]&a[2]
    wire na1 = ~a[1];
    wire nb1 = ~b[1];
    wire sa1_hi = a[2] & na1;
    wire sa1_lo = a[1] & a[2];
    wire sb1_hi = b[2] & nb1;
    wire sb1_lo = b[1] & b[2];
    wire [1:0] sa1 = {sa1_hi, sa1_lo};
    wire [1:0] sb1 = {sb1_hi, sb1_lo};
    wire [2:0] K = sa1 + sb1;

    wire [7:0] mag = P << K;

    // Sign + 2's-comp negate (same as before).
    wire sy = sa ^ sb;
    wire [8:0] mag9 = {1'b0, mag};
    wire [8:0] xord = mag9 ^ {9{sy}};
    wire [8:0] outv = xord + {8'b0, sy};
    assign y = outv;
endmodule
