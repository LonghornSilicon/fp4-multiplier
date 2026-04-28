"""
Gate-reduction experiments for FP4×FP4→QI9 multiplier.
Baseline: 88 gates (v4b).
"""
import sys
sys.path.insert(0, r'C:\Users\themo\Desktop\Etched Multiplier Assignment')
from eval_circuit import evaluate_fast

REMAP = [0, 4, 5, 1, 6, 2, 7, 3, 0, 12, 13, 9, 14, 10, 15, 11]

def run(name, fn):
    correct, gc, errors = evaluate_fast(fn, REMAP, verbose=False)
    status = "OK" if correct else f"WRONG({len(errors)})"
    print(f"  {name:50s}  gates={gc:3d}  {status}")
    return correct, gc

print("=" * 70)
print("Baseline (v4b, 88 gates)")
print("=" * 70)

# ── BASELINE ──────────────────────────────────────────────────────────────────
def baseline(a0,a1,a2,a3,b0,b1,b2,b3,NOT=None,AND=None,OR=None,XOR=None):
    sign = XOR(a0, b0)
    or_a23 = OR(a2, a3);   nz_a = OR(a1, or_a23)
    or_b23 = OR(b2, b3);   nz_b = OR(b1, or_b23)
    nz = AND(nz_a, nz_b)
    s0  = XOR(a3, b3);  c0  = AND(a3, b3)
    s1x = XOR(a2, b2);  s1  = XOR(s1x, c0)
    s2  = OR(AND(a2, b2), AND(s1x, c0))
    or_a1b1 = OR(a1, b1)
    k9_raw  = NOT(or_a1b1)
    k3_raw  = XOR(a1, b1)
    nmc = AND(or_a1b1, nz)
    k3  = AND(k3_raw,  nz)
    k9  = AND(k9_raw,  nz)
    ns0 = NOT(s0);  ns1 = NOT(s1);  ns2 = NOT(s2)
    u00 = AND(ns2, ns1);  u01 = AND(ns2, s1)
    u10 = AND(s2, ns1);   u11 = AND(s2, s1)
    sh0 = AND(u00, ns0);  sh1 = AND(u00, s0)
    sh2 = AND(u01, ns0);  sh3 = AND(u01, s0)
    sh4 = AND(u10, ns0);  sh5 = AND(u10, s0)
    nmc0 = AND(nmc, sh0);  nmc1 = AND(nmc, sh1);  nmc2 = AND(nmc, sh2)
    nmc3 = AND(nmc, sh3);  nmc4 = AND(nmc, sh4);  nmc5 = AND(nmc, sh5)
    nmc6 = AND(nmc, u11)
    k3_1 = AND(k3, sh1);  k3_2 = AND(k3, sh2);  k3_3 = AND(k3, sh3)
    k3_4 = AND(k3, sh4);  k3_5 = AND(k3, sh5);  k3_6 = AND(k3, u11)
    k9_2 = AND(k9, sh2);  k9_3 = AND(k9, sh3);  k9_4 = AND(k9, sh4)
    k9_5 = AND(k9, sh5);  k9_6 = AND(k9, u11)
    m7 = k9_6
    m6 = OR(nmc6, k9_5)
    m5 = OR(nmc5, OR(k3_6, k9_4))
    m4 = OR(OR(nmc4, k3_5), OR(k9_6, k9_3))
    m3 = OR(OR(nmc3, k3_4), OR(k9_5, k9_2))
    m2 = OR(nmc2, OR(k3_3, k9_4))
    m1 = OR(nmc1, OR(k3_2, k9_3))
    m0 = OR(nmc0, OR(k3_1, k9_2))
    t0 = XOR(m0, sign);  r8 = m0;            c1 = AND(t0, sign)
    t1 = XOR(m1, sign);  r7 = XOR(t1, c1);  c2 = AND(t1, c1)
    t2 = XOR(m2, sign);  r6 = XOR(t2, c2);  c3 = AND(t2, c2)
    t3 = XOR(m3, sign);  r5 = XOR(t3, c3);  c4 = AND(t3, c3)
    t4 = XOR(m4, sign);  r4 = XOR(t4, c4);  c5 = AND(t4, c4)
    t5 = XOR(m5, sign);  r3 = XOR(t5, c5);  c6 = AND(t5, c5)
    t6 = XOR(m6, sign);  r2 = XOR(t6, c6);  c7 = AND(t6, c6)
    t7 = XOR(m7, sign);  r1 = XOR(t7, c7)
    res0 = AND(sign, nz)
    return res0, r1, r2, r3, r4, r5, r6, r7, r8

run("baseline", baseline)

# ─────────────────────────────────────────────────────────────────────────────
print()
print("=" * 70)
print("Experiment 1: m7=k9_6 is a single AND; t7=XOR(k9_6,sign)")
print("  r1=XOR(t7,c7). c7=AND(t6,c6). When m7=1 -> k9=1,S=6.")
print("  Try: skip t7 XOR, use c7 directly as the carry into r1.")
print("  Observation: r1 = XOR(XOR(k9_6,sign), AND(XOR(m6,sign), c6))")
print("  Can we use: r1 = XOR(k9_6, AND(m6_xor_sign, c6), sign)?  No savings directly.")
print("  But: when sign=0, r1=k9_6. When sign=1, r1=NOT(k9_6) XOR c7.")
print("  => r1 = XOR(k9_6, XOR(sign, c7))  which is same cost.")
print("=" * 70)

# Idea 1a: Try using XNOR-like identity for last stage
# r1 = XOR(m7, sign) XOR c7 = XOR(m7, XOR(sign, c7))
# No gate savings here - same 2 gates.

# Idea 1b: Note c7 = AND(t6, c6) = AND(XOR(m6,sign), c6)
# When sign=1: t6=NOT(m6), c7 = AND(NOT(m6), c6) = AND(NOR(m6), c6)
# When sign=0: c7=0, r1=m7
# Merged: r1 = XOR(m7, XOR(sign, AND(XOR(m6,sign), c6)))
# That's still XOR+AND+XOR+XOR = same count.

# Let's try: avoid one XOR by noting:
# t6 = XOR(m6, sign)
# c7 = AND(t6, c6)
# t7 = XOR(m7, sign)
# r1 = XOR(t7, c7)
#
# Alternative: r1 = XOR(m7, XOR(sign, c7)) — saves nothing
# Another: precompute sign_and_c6 = AND(sign, c6) when sign=1 gates

# Idea 1c: XOR(t7, c7) where t7=XOR(k9_6, sign)
# = XOR(XOR(k9_6, sign), c7)
# = XOR(k9_6, XOR(sign, c7))
# Not fewer gates.

# Let's try a different angle: eliminate t6 by merging with c7 computation.
# c7 = AND(XOR(m6,sign), c6)
# We could try: c7 = AND(m6, c6) XOR AND(sign, c6) — that's MORE gates.
# Or: c7 = AND(m6 XNOR sign, c6) -- not standard.

# What if we note m6 = OR(nmc6, k9_5)?
# t6 = XOR(OR(nmc6,k9_5), sign)
# Hmm. Let's try using a NOR for c7 differently.

# ─────────────────────────────────────────────────────────────────────────────
print()
print("Experiment 2: Try collapsing last 2 cond_neg stages")
print("  r1=XOR(t7,c7), r2=XOR(t6,c6) with c7=AND(t6,c6)")
print("  Both r1 and r2 depend on t6,c6. Can we merge?")
print("=" * 70)

# r2 = XOR(t6, c6)
# c7 = AND(t6, c6)
# r1 = XOR(t7, c7) = XOR(t7, AND(t6,c6))
# Note: r2 = XOR(t6,c6) and c7 = AND(t6,c6)
# These are the SUM and CARRY of a half-adder on t6,c6.
# Then r1 = XOR(t7, carry) = XOR(t7, AND(t6,c6))
#
# Key insight: m7=k9_6 is the ONLY thing in bit-7.
# t7 = XOR(k9_6, sign)
# r1 = XOR(t7, c7) = XOR(XOR(k9_6,sign), AND(t6,c6))
#
# Can we precompute "AND(t6,c6)" as c7 without computing t6 first for r2?
# No - t6 is needed for r2 anyway.

# ─────────────────────────────────────────────────────────────────────────────
print()
print("Experiment 3: NOR-based carry for sign=1 case")
print("  c_i = AND(t_{i-1}, c_{i-1})")
print("  When sign=1: t_i = NOT(m_i), so c_i = AND(NOT(m_{i-1}), c_{i-1})")
print("  c_i = 1 iff all m_j=0 for j<i AND sign=1")
print("  = AND(sign, NOR(m0,...,m_{i-1}))")
print("  = AND(sign, NOT(OR(m0,...,m_{i-1})))")
print("  This could allow shared prefix-OR computation.")
print("=" * 70)

# The idea: carry c_i = AND(sign, NOT(OR(m_{i-1},...,m_0)))
# Define prefix_or_i = OR(m_0, m_1, ..., m_{i-1})
# c_i = AND(sign, NOT(prefix_or_i))
#
# prefix_or_0 = 0  (empty)  -> c1 = AND(sign, 1) = sign... wait
# Actually c1 = AND(t0, sign) = AND(XOR(m0,sign), sign)
#   when sign=1: AND(NOT(m0), 1) = NOT(m0) -- but this is only the "sign=1" branch
#   when sign=0: c1=0
# So c1 = AND(sign, NOT(m0)) -- only valid if sign is a clean bit
#
# Let's derive c1 directly:
# c1 = AND(XOR(m0,sign), sign)
#    = AND(sign, XOR(m0,sign))
#    = AND(sign, OR(AND(sign,NOT(m0)), AND(NOT(sign),m0)))   -- expand XOR
# When sign=0: c1 = AND(0,...) = 0. OK.
# When sign=1: c1 = AND(1, NOT(m0)) = NOT(m0)... but NOT(m0) uses a NOT gate.
#
# Alternative formula: c1 = AND(sign, NOT(m0))? Let's verify:
# sign=0,m0=0: c1=AND(0,1)=0; formula gives 0. OK
# sign=0,m0=1: c1=AND(0,0)=0; formula gives 0. OK
# sign=1,m0=0: c1=AND(NOT(0),1)=AND(1,1)=1; formula AND(1,NOT(0))=AND(1,1)=1. OK
# sign=1,m0=1: c1=AND(NOT(1),1)=AND(0,1)=0; formula AND(1,NOT(1))=AND(1,0)=0. OK
# YES: c1 = AND(sign, NOT(m0))
#
# Similarly:
# c2 = AND(t1, c1) = AND(XOR(m1,sign), AND(sign, NOT(m0)))
# When sign=0: c2=0. When sign=1: c2=AND(NOT(m1), NOT(m0)) = AND(sign, NOR(m0,m1))
# So c2 = AND(sign, NOT(OR(m0,m1)))? Let's check:
# sign=1,m0=0,m1=0: c2=AND(NOT(m1),NOT(m0))=1; formula AND(1,NOT(OR(0,0)))=AND(1,1)=1. OK
# sign=1,m0=1,m1=0: c2=AND(NOT(0),AND(1,NOT(1)))=AND(1,0)=0; formula AND(1,NOT(OR(1,0)))=AND(1,0)=0. OK
# sign=1,m0=0,m1=1: c2=AND(NOT(1),AND(1,1))=AND(0,1)=0; formula AND(1,NOT(OR(0,1)))=0. OK
#
# General pattern: c_i = AND(sign, NOT(OR(m_0,...,m_{i-1})))
#
# Cost analysis:
# prefix_or_1 = m0  (free, already computed)
# prefix_or_2 = OR(m0,m1)      -- 1 gate
# prefix_or_3 = OR(prefix_or_2, m2) -- 1 gate
# ...
# prefix_or_7 = OR(prefix_or_6, m6) -- 1 gate
# That's 6 new OR gates.
# Then: NOT(prefix_or_i) = 7 NOT gates -> AND(sign,...) = 7 AND gates
# But we also still need the r_i = XOR(m_i, sign) XOR c_i computation
#
# Original cond_neg cost:
#   8 XOR for t_i, 7 XOR for r_i, 1 r8=m0 passthrough, 7 AND for c_i = 22 gates
#
# New approach cost:
#   NOT(m0) = 1 gate  (but we can use prefix OR differently)
#   Actually let's think again: we need NOT(prefix_or_i) for each carry.
#   But NOT(prefix_or_i) = NOT(OR(m0,...)) can we share?
#   No - each bit needs its own NOT.
#
# Alternative: use NOR gates or De Morgan:
#   NOT(OR(a,b)) = NOR(a,b) -- but NOR = NOT(OR) = 2 gates in AND/OR/NOT basis
#
# So the cost for all carries via the "prefix NOR" approach:
#   6 OR for prefix (prefix_or_2..7)
#   7 NOT for NOT(prefix_or_1..7)  [NOT(m0) for c1, NOT(prefix_or_2) for c2, etc.]
#   7 AND for AND(sign, ...) for c1..c7
#   = 20 gates for carries
#   + 8 XOR for t_i (still needed for r_i)  [since r_i = XOR(t_i, c_i) = XOR(XOR(m_i,sign),c_i)]
#   + 7 XOR for r_i = 15 XORs
#   + r8 = m0 passthrough
#
# Wait: we still need t_i = XOR(m_i, sign)?
# r_i = XOR(t_i, c_i) = XOR(XOR(m_i,sign), c_i)
# Alternatively: r_i = XOR(m_i, XOR(sign, c_i))
# XOR(sign, c_i) - we can compute sign XOR c_i more cheaply?
# When sign=0: c_i=0, so XOR(sign,c_i)=0, r_i=m_i
# When sign=1: c_i=NOT(prefix_or_i), so XOR(1, NOT(prefix_or_i)) = NOT(NOT(prefix_or_i)) = prefix_or_i
# So: r_i = MUX(sign, m_i, XOR(m_i, prefix_or_i))
#         = MUX(sign, m_i, m_i XOR prefix_or_i)
# But MUX is 4 gates (NOT+2AND+OR) or 3 gates... not cheaper.
#
# Actually: when sign=1, r_i = XOR(m_i, prefix_or_i) [i.e., sum bit of half-adder of increment]
# This makes intuitive sense: adding 1 to the magnitude, carry propagates until first 1-bit.
# r_i = m_i XOR prefix_or_i (when sign=1)
# r_i = m_i (when sign=0)
# So r_i = XOR(m_i, AND(sign, prefix_or_i))
#
# Using this:
#   Compute prefix_or_i for i=1..7: 6 OR gates
#   AND(sign, prefix_or_i) for i=1..7: 7 AND gates
#   XOR(m_i, ...) for i=1..7: 7 XOR gates
#   r8 = m0 passthrough
#
# Total: 6+7+7 = 20 gates for bits r1-r7, plus r8=m0
# Savings: 22-20 = 2 gates!
#
# Let's verify the formula r_i = XOR(m_i, AND(sign, prefix_or_i)):
# sign=0: r_i = XOR(m_i, AND(0,...)) = XOR(m_i, 0) = m_i. Correct (no negation).
# sign=1: r_i = XOR(m_i, prefix_or_i) where prefix_or_i = OR(m_0,..,m_{i-1})
#
# This is the "increment" formula: negating a number = flip all bits then add 1.
# When you add 1 to a binary number, bits flip from LSB until (and including) first 1-bit.
# So bit i of (magnitude+1) = m_i XOR (all bits below i were 0) = XOR(m_i, NOR(m_0..m_{i-1}))
# Wait, that gives the INCREMENTED value. But we want:
# neg(x) = ~x + 1
# bit i of neg(x) = (bit i of ~x) XOR (carry into position i)
# carry_i = 1 iff m_0=...=m_{i-1}=0
# So bit i of neg(x) = XOR(NOT(m_i), carry_i) = XOR(NOT(m_i), NOR(m_0..m_{i-1}))
#
# Hmm but above I said r_i = XOR(m_i, prefix_or_i).
# Let me re-derive:
# neg(x) bit_i = NOT(m_i) XOR carry_i, where carry_i = NOR(m_{i-1},...,m_0)
# But the FULL result is:
# when sign=1: result_i = NOT(m_i) XOR carry_i = XOR(NOT(m_i), NOR(m_{i-1}..m_0))
# = XOR(NOT(m_i), NOT(OR(m_0..m_{i-1})))
# Using XOR(NOT(a),NOT(b)) = XOR(a,b):
# = XOR(m_i, OR(m_0..m_{i-1})) = XOR(m_i, prefix_or_i)
# when sign=0: result_i = m_i
# Combined: result_i = XOR(m_i, AND(sign, prefix_or_i))
#
# This is CORRECT! Let's implement it.

def exp3_prefix_or_negation(a0,a1,a2,a3,b0,b1,b2,b3,NOT=None,AND=None,OR=None,XOR=None):
    sign = XOR(a0, b0)
    or_a23 = OR(a2, a3);   nz_a = OR(a1, or_a23)
    or_b23 = OR(b2, b3);   nz_b = OR(b1, or_b23)
    nz = AND(nz_a, nz_b)
    s0  = XOR(a3, b3);  c0  = AND(a3, b3)
    s1x = XOR(a2, b2);  s1  = XOR(s1x, c0)
    s2  = OR(AND(a2, b2), AND(s1x, c0))
    or_a1b1 = OR(a1, b1)
    k9_raw  = NOT(or_a1b1)
    k3_raw  = XOR(a1, b1)
    nmc = AND(or_a1b1, nz)
    k3  = AND(k3_raw,  nz)
    k9  = AND(k9_raw,  nz)
    ns0 = NOT(s0);  ns1 = NOT(s1);  ns2 = NOT(s2)
    u00 = AND(ns2, ns1);  u01 = AND(ns2, s1)
    u10 = AND(s2, ns1);   u11 = AND(s2, s1)
    sh0 = AND(u00, ns0);  sh1 = AND(u00, s0)
    sh2 = AND(u01, ns0);  sh3 = AND(u01, s0)
    sh4 = AND(u10, ns0);  sh5 = AND(u10, s0)
    nmc0 = AND(nmc, sh0);  nmc1 = AND(nmc, sh1);  nmc2 = AND(nmc, sh2)
    nmc3 = AND(nmc, sh3);  nmc4 = AND(nmc, sh4);  nmc5 = AND(nmc, sh5)
    nmc6 = AND(nmc, u11)
    k3_1 = AND(k3, sh1);  k3_2 = AND(k3, sh2);  k3_3 = AND(k3, sh3)
    k3_4 = AND(k3, sh4);  k3_5 = AND(k3, sh5);  k3_6 = AND(k3, u11)
    k9_2 = AND(k9, sh2);  k9_3 = AND(k9, sh3);  k9_4 = AND(k9, sh4)
    k9_5 = AND(k9, sh5);  k9_6 = AND(k9, u11)
    m7 = k9_6
    m6 = OR(nmc6, k9_5)
    m5 = OR(nmc5, OR(k3_6, k9_4))
    m4 = OR(OR(nmc4, k3_5), OR(k9_6, k9_3))
    m3 = OR(OR(nmc3, k3_4), OR(k9_5, k9_2))
    m2 = OR(nmc2, OR(k3_3, k9_4))
    m1 = OR(nmc1, OR(k3_2, k9_3))
    m0 = OR(nmc0, OR(k3_1, k9_2))

    # Prefix-OR based conditional negation
    # r_i = XOR(m_i, AND(sign, OR(m_0,...,m_{i-1})))
    # prefix_or_0 = 0 (empty), so r_0 term = XOR(m0, AND(sign,0)) = m0?
    # But r8 = m0 is the LSB passthrough (no negation of LSB)
    # Wait -- in 2's complement negation of an 8-bit number:
    # the LSB is always = m0 (the last zero before first 1 becomes 1, others become NOT)
    # Actually: neg(x) = NOT(x) + 1
    # bit 0 of neg(x) = m0 (unchanged) -- LSB is preserved (1->1 since -x LSB = x LSB for 2s comp)
    # Actually for 2's complement negation:
    # neg(x) = ~x + 1
    # bit 0 = NOT(m0) + 1... no, the full addition:
    # ~x = flip all bits
    # ~x + 1: bit 0 = NOT(m0) XOR 1 = m0 (yes, LSB preserved when adding 1)
    # Wait: NOT(m0) XOR 1:
    #   m0=0: NOT(0)=1, 1 XOR 1 = 0? That doesn't seem right.
    #   Actually: ~x + 1:
    #   bit 0 = NOT(m0) XOR 1 = XOR(NOT(m0), 1) = m0 (since XOR with 1 flips)
    #   carry_out_0 = AND(NOT(m0), 1) = NOT(m0)
    # So yes, bit 0 of neg(x) = m0 -- that's the passthrough!
    # And carry_1 = NOT(m0) = 1 iff m0=0
    # bit 1 of neg(x) = NOT(m1) XOR carry_1 = XOR(NOT(m1), NOT(m0))
    #                 = XOR(m0, m1) [since XOR(NOT(a),NOT(b))=XOR(a,b)]
    # Hmm no. Let me redo:
    # carry_i = 1 iff m_{i-1}=0 AND carry_{i-1}=1
    # carry_1 = NOT(m0) (since carry_0=1 always when we're adding 1)
    # bit_i = NOT(m_i) XOR carry_i
    # bit_0 = NOT(m_0) XOR 1 = m_0  [XOR with 1 inverts]
    # bit_1 = NOT(m_1) XOR NOT(m_0) = XOR(m_0, m_1)...
    # Actually NOT(m_1) XOR NOT(m_0) = m_1 XOR m_0 (XOR of two NOTs = XOR of originals)
    # carry_2 = AND(NOT(m_1), NOT(m_0))
    # bit_1 when m0=0,m1=0: NOT(0) XOR NOT(0) = 1 XOR 1 = 0...
    # but for number 00, neg(00)=00 (or 100 in 2-bit), so bit_1=0. OK.
    # bit_1 when m0=1,m1=0: NOT(0) XOR NOT(1) = 1 XOR 0 = 1...
    # Number=01 (=1), neg=11 (=-1 in 2s comp but we want magnitude), bit_1=1. OK.
    # bit_1 when m0=0,m1=1: NOT(1) XOR NOT(0) = 0 XOR 1 = 1. Number=10, neg=10, bit_1=1. OK.
    #
    # So bit_1 of neg(x) = XOR(m_0, m_1) -- that's what our formula gives: XOR(m1, prefix_or_1)
    # where prefix_or_1 = m0. Correct!
    #
    # For the cond_neg (negate only if sign=1):
    # result_i = MUX(sign, m_i, neg(x)_i)
    # r8 (bit 0) = m0 [same regardless of sign since neg LSB = original LSB]
    # result_i for i>=1: XOR(m_i, AND(sign, prefix_or_i)) where prefix_or_i = OR(m0..m_{i-1})

    # prefix_or_1 = m0 (no gate needed)
    prefix_or_2 = OR(m0, m1)          # 1 gate
    prefix_or_3 = OR(prefix_or_2, m2) # 1 gate
    prefix_or_4 = OR(prefix_or_3, m3) # 1 gate
    prefix_or_5 = OR(prefix_or_4, m4) # 1 gate
    prefix_or_6 = OR(prefix_or_5, m5) # 1 gate
    prefix_or_7 = OR(prefix_or_6, m6) # 1 gate
    # 6 OR gates for prefix

    s_and_p1 = AND(sign, m0)           # AND(sign, prefix_or_1) -- 1 gate
    s_and_p2 = AND(sign, prefix_or_2)  # 1 gate
    s_and_p3 = AND(sign, prefix_or_3)  # 1 gate
    s_and_p4 = AND(sign, prefix_or_4)  # 1 gate
    s_and_p5 = AND(sign, prefix_or_5)  # 1 gate
    s_and_p6 = AND(sign, prefix_or_6)  # 1 gate
    s_and_p7 = AND(sign, prefix_or_7)  # 1 gate
    # 7 AND gates

    r8 = m0
    r7 = XOR(m1, s_and_p1)  # 1 gate
    r6 = XOR(m2, s_and_p2)  # 1 gate
    r5 = XOR(m3, s_and_p3)  # 1 gate
    r4 = XOR(m4, s_and_p4)  # 1 gate
    r3 = XOR(m5, s_and_p5)  # 1 gate
    r2 = XOR(m6, s_and_p6)  # 1 gate
    r1 = XOR(m7, s_and_p7)  # 1 gate
    # 7 XOR gates
    # Total cond_neg: 6+7+7 = 20 gates (saves 2!)

    res0 = AND(sign, nz)
    return res0, r1, r2, r3, r4, r5, r6, r7, r8

run("exp3_prefix_or_negation (target: 86)", exp3_prefix_or_negation)

# ─────────────────────────────────────────────────────────────────────────────
print()
print("Experiment 4: Can we share sign ANDs with prefix OR?")
print("  s_and_p_i = AND(sign, prefix_or_i)")
print("  Instead: precompute sign_prefix chain:")
print("  sp1 = AND(sign, m0)")
print("  sp2 = AND(sign, OR(m0,m1)) vs OR(sp1, AND(sign,m1))")
print("  Using OR(sp1,AND(sign,m1)) saves nothing.")
print("  But: sp2 = OR(sp1, AND(sign,m1)) -- same gate count.")
print("  Alt: since sp1=AND(sign,m0), sp2=AND(sign,OR(m0,m1))")
print("  We could use sp2 = OR(sp1, AND(sign,m1)) to avoid explicit OR(m0,m1).")
print("  This replaces 1 OR+1 AND with 1 AND+1 OR -- same count, no savings.")
print("=" * 70)

# ─────────────────────────────────────────────────────────────────────────────
print()
print("Experiment 5: Further optimize prefix OR sharing with sign masking")
print("  Note: all sp_i = AND(sign, prefix_or_i)")
print("  Alternative: sp_i = OR(sp_{i-1}, AND(sign, m_{i-1}))")
print("  This way: sp1 = AND(sign, m0)  [1 AND]")
print("            sp2 = OR(sp1, AND(sign, m1))  [1 AND + 1 OR]")
print("            sp3 = OR(sp2, AND(sign, m2))  [1 AND + 1 OR]")
print("            ...")
print("  Total: 7 AND + 6 OR = 13 gates for sp1..sp7")
print("  vs current: 6 OR (prefix) + 7 AND = 13 gates")
print("  Same count! But different structure.")
print("=" * 70)

# ─────────────────────────────────────────────────────────────────────────────
print()
print("Experiment 6: Can we share 'sign AND nz' with prefix computation?")
print("  res0 = AND(sign, nz) is 1 gate.")
print("  The sp_i = AND(sign, prefix_or_i) -- these are 7 ANDs of sign with something.")
print("  If sign=0: all sp_i=0, and r_i=m_i (magnitude pass-through).")
print("  The AND(sign, nz) for res0 is separate.")
print("  No sharing opportunity obvious.")
print("=" * 70)

# ─────────────────────────────────────────────────────────────────────────────
print()
print("Experiment 7: Eliminate some AND(sign, prefix_or_i) by noting sparsity")
print("  When k9=1 (k9_raw AND nz), only certain bits set.")
print("  But we already handle K-masking with nz, so at evaluation time")
print("  m_i can be anything -- we need the full formula regardless.")
print("  No structural simplification possible here without case splitting.")
print("=" * 70)

# ─────────────────────────────────────────────────────────────────────────────
print()
print("Experiment 8: Try to merge nz detection into sign computation")
print("  res0 = AND(XOR(a0,b0), AND(OR(a1,OR(a2,a3)), OR(b1,OR(b2,b3))))")
print("  sign is used in cond_neg too. nz is used in K-masking too.")
print("  Can sign_nz = AND(sign, nz) be computed more cheaply?")
print("  Current: sign(1) + nz(5) + sign_mask(1) = 7 gates total for sign/nz/mask.")
print("  Can we compute nz differently to share with K-flags?")
print("  nz = AND(nz_a, nz_b) where nz_a=OR(a1,OR(a2,a3)), nz_b=OR(b1,OR(b2,b3))")
print("  K-flags: or_a1b1 = OR(a1,b1) -- different combination, no sharing.")
print("=" * 70)

# ─────────────────────────────────────────────────────────────────────────────
print()
print("Experiment 9: Can K-masking (3 gates) be reduced?")
print("  nmc = AND(or_a1b1, nz)")
print("  k3  = AND(k3_raw, nz)")
print("  k9  = AND(k9_raw, nz)")
print("  These 3 gates mask K-flags with nz.")
print("  Alternative: mask only at output bits level.")
print("  Each output bit has terms involving nmc/k3/k9.")
print("  Replacing: nmc_i = AND(AND(or_a1b1,nz), sh_i) = AND(or_a1b1, AND(nz, sh_i))")
print("  This would require AND(nz, sh_i) for each sh, then AND with K-flag.")
print("  7+6+5=18 AND-terms each needing nz-AND = 18 more gates. Much worse.")
print("  The current 3-gate masking is already optimal.")
print("=" * 70)

# ─────────────────────────────────────────────────────────────────────────────
print()
print("Experiment 10: Can S-decoder be reduced?")
print("  Current: 3 NOT + 4 u + 6 sh = 13 gates")
print("  s2,s1,s0 are the 3-bit shift value.")
print("  We need one-hot sh0..sh5 and u11 (=sh6).")
print("  Minimum for 3-to-7 one-hot decode: at least 7-1=6 AND gates + invert cost.")
print("  Can we reduce NOT gates?")
print("  ns0,ns1,ns2 = NOT(s0),NOT(s1),NOT(s2) -- 3 NOTs needed for the decode.")
print("  u00=AND(ns2,ns1), u01=AND(ns2,s1), u10=AND(s2,ns1), u11=AND(s2,s1): 4 ANDs")
print("  sh0=AND(u00,ns0), sh1=AND(u00,s0), sh2=AND(u01,ns0), sh3=AND(u01,s0),")
print("  sh4=AND(u10,ns0), sh5=AND(u10,s0): 6 ANDs")
print("  Total: 3+4+6=13. Hard to do better -- minimum decode cost.")
print("=" * 70)

# ─────────────────────────────────────────────────────────────────────────────
print()
print("Experiment 11: Can Magnitude-OR tree (15 gates) be reduced?")
print("  m7 = k9_6                           [0 OR]")
print("  m6 = OR(nmc6, k9_5)                 [1 OR]")
print("  m5 = OR(nmc5, OR(k3_6, k9_4))       [2 OR]")
print("  m4 = OR(OR(nmc4,k3_5), OR(k9_6,k9_3)) [3 OR]")
print("  m3 = OR(OR(nmc3,k3_4), OR(k9_5,k9_2)) [3 OR]")
print("  m2 = OR(nmc2, OR(k3_3, k9_4))       [2 OR -- but k9_4 also used in m5!]")
print("  m1 = OR(nmc1, OR(k3_2, k9_3))       [2 OR]")
print("  m0 = OR(nmc0, OR(k3_1, k9_2))       [2 OR]")
print("  Total: 0+1+2+3+3+2+2+2 = 15 OR gates")
print("  Note: k9_4 appears in m5 AND m2. Already shared!")
print("  Note: k9_5 appears in m6 AND m3. Already shared!")
print("  Note: k9_6=m7 appears in m4. Already shared (m7=k9_6)!")
print("  These are already accounted for in AND-terms (18 gates).")
print("  Can we find shared sub-expressions?")
print("  OR(k9_5, k9_2) in m3, OR(k9_5, k9_3) doesn't appear, etc.")
print("  Try: OR(nmc_i, k3_{i+1}) as shared sub-expression across adjacent bits?")
print("=" * 70)

# ─────────────────────────────────────────────────────────────────────────────
print()
print("Experiment 12: Try sharing OR(nmc_i, k3_{i+1}) sub-expressions")
print("  m5 = OR(nmc5, OR(k3_6, k9_4))")
print("  m4 = OR(OR(nmc4,k3_5), OR(k9_6, k9_3))")
print("  m3 = OR(OR(nmc3,k3_4), OR(k9_5, k9_2))")
print("  m2 = OR(nmc2, OR(k3_3, k9_4))")
print("  m1 = OR(nmc1, OR(k3_2, k9_3))")
print("  m0 = OR(nmc0, OR(k3_1, k9_2))")
print("  nk_i = OR(nmc_i, k3_{i+1}): used in m_i for i=0..5?")
print("  Actually: nmc and k3 have different shift indices:")
print("  m_i = nmc_i OR k3_{i+1} OR k9_{i-1} OR k9_{i+2}")
print("  nk_i = OR(nmc_i, k3_{i+1}): would give m5=OR(nk5, k9_4), saving?")
print("  But nk_5 = OR(nmc5, k3_6), nk_4 = OR(nmc4, k3_5), etc.")
print("  m5 = OR(nk5, k9_4)  -- if nk5 defined, 1 OR instead of 2 OR for these terms")
print("  m4 = OR(nk4, OR(k9_6, k9_3)) -- same")
print("  But we spend 1 AND defining nk_i... wait, it's an OR gate to define nk.")
print("  nk5 = OR(nmc5, k3_6): 1 gate to define")
print("  m5 = OR(nk5, k9_4): 1 gate instead of OR(nmc5, OR(k3_6, k9_4)) = 2 gates")
print("  Net savings: 0 (spend 1 to define nk5, save 1 in m5 computation).")
print("  No benefit from sharing this way.")
print("=" * 70)

# ─────────────────────────────────────────────────────────────────────────────
print()
print("Experiment 13: Look at shared k9_i usage across magnitude bits")
print("  k9_2 used in m3, m0")
print("  k9_3 used in m4, m1")
print("  k9_4 used in m5, m2")
print("  k9_5 used in m6, m3")
print("  k9_6 used in m7, m4")
print("  For m3: OR(OR(nmc3,k3_4), OR(k9_5,k9_2))")
print("  For m4: OR(OR(nmc4,k3_5), OR(k9_6,k9_3))")
print("  The pattern OR(k9_{i+2},k9_{i-1}) appears in m3,m4.")
print("  But these are different pairs each time, no sharing.")
print("=" * 70)

# ─────────────────────────────────────────────────────────────────────────────
print()
print("Experiment 14: Full experiment - verify prefix-OR cond_neg saves 2 gates")
print("  Baseline: 88 gates, prefix-OR formula: should be 86 gates")
print("=" * 70)

# Already ran exp3 above - let's also try a variant with different organization
def exp14_verify(a0,a1,a2,a3,b0,b1,b2,b3,NOT=None,AND=None,OR=None,XOR=None):
    """Same as exp3 but double-checking the formula explicitly."""
    sign = XOR(a0, b0)                                          # 1
    or_a23 = OR(a2, a3);   nz_a = OR(a1, or_a23)              # 2
    or_b23 = OR(b2, b3);   nz_b = OR(b1, or_b23)              # 2
    nz = AND(nz_a, nz_b)                                        # 1
    s0  = XOR(a3, b3);  c0  = AND(a3, b3)                     # 2
    s1x = XOR(a2, b2);  s1  = XOR(s1x, c0)                   # 2
    s2  = OR(AND(a2, b2), AND(s1x, c0))                        # 3
    or_a1b1 = OR(a1, b1)                                        # 1
    k9_raw  = NOT(or_a1b1)                                      # 1
    k3_raw  = XOR(a1, b1)                                       # 1
    nmc = AND(or_a1b1, nz)                                      # 1
    k3  = AND(k3_raw,  nz)                                      # 1
    k9  = AND(k9_raw,  nz)                                      # 1
    ns0 = NOT(s0);  ns1 = NOT(s1);  ns2 = NOT(s2)             # 3
    u00 = AND(ns2, ns1);  u01 = AND(ns2, s1)                  # 2
    u10 = AND(s2, ns1);   u11 = AND(s2, s1)                   # 2
    sh0 = AND(u00, ns0);  sh1 = AND(u00, s0)                  # 2
    sh2 = AND(u01, ns0);  sh3 = AND(u01, s0)                  # 2
    sh4 = AND(u10, ns0);  sh5 = AND(u10, s0)                  # 2
    nmc0 = AND(nmc, sh0);  nmc1 = AND(nmc, sh1);  nmc2 = AND(nmc, sh2)   # 3
    nmc3 = AND(nmc, sh3);  nmc4 = AND(nmc, sh4);  nmc5 = AND(nmc, sh5)   # 3
    nmc6 = AND(nmc, u11)                                        # 1
    k3_1 = AND(k3, sh1);  k3_2 = AND(k3, sh2);  k3_3 = AND(k3, sh3)     # 3
    k3_4 = AND(k3, sh4);  k3_5 = AND(k3, sh5);  k3_6 = AND(k3, u11)     # 3
    k9_2 = AND(k9, sh2);  k9_3 = AND(k9, sh3);  k9_4 = AND(k9, sh4)     # 3
    k9_5 = AND(k9, sh5);  k9_6 = AND(k9, u11)                # 2
    m7 = k9_6
    m6 = OR(nmc6, k9_5)                                        # 1
    m5 = OR(nmc5, OR(k3_6, k9_4))                             # 2
    m4 = OR(OR(nmc4, k3_5), OR(k9_6, k9_3))                  # 3
    m3 = OR(OR(nmc3, k3_4), OR(k9_5, k9_2))                  # 3
    m2 = OR(nmc2, OR(k3_3, k9_4))                             # 2
    m1 = OR(nmc1, OR(k3_2, k9_3))                             # 2
    m0 = OR(nmc0, OR(k3_1, k9_2))                             # 2

    # New cond_neg: 6 OR + 7 AND + 7 XOR = 20 gates (vs 22 in baseline)
    p1 = m0                         # prefix_or_1 = m0, free
    p2 = OR(m0, m1)                 # 1
    p3 = OR(p2, m2)                 # 1
    p4 = OR(p3, m3)                 # 1
    p5 = OR(p4, m4)                 # 1
    p6 = OR(p5, m5)                 # 1
    p7 = OR(p6, m6)                 # 1  [6 OR total]

    sp1 = AND(sign, p1)             # 1
    sp2 = AND(sign, p2)             # 1
    sp3 = AND(sign, p3)             # 1
    sp4 = AND(sign, p4)             # 1
    sp5 = AND(sign, p5)             # 1
    sp6 = AND(sign, p6)             # 1
    sp7 = AND(sign, p7)             # 1  [7 AND total]

    r8 = m0
    r7 = XOR(m1, sp1)              # 1
    r6 = XOR(m2, sp2)              # 1
    r5 = XOR(m3, sp3)              # 1
    r4 = XOR(m4, sp4)              # 1
    r3 = XOR(m5, sp5)              # 1
    r2 = XOR(m6, sp6)              # 1
    r1 = XOR(m7, sp7)              # 1  [7 XOR total]

    res0 = AND(sign, nz)           # 1
    return res0, r1, r2, r3, r4, r5, r6, r7, r8

run("exp14_verify_prefix_or (target: 86)", exp14_verify)

# ─────────────────────────────────────────────────────────────────────────────
print()
print("Experiment 15: Can we further reduce by sharing sign with prefix chain?")
print("  sp_i = AND(sign, p_i) where p_i = OR(p_{i-1}, m_{i-1})")
print("  Alternative: sp_i = OR(sp_{i-1}, AND(sign, m_{i-1}))")
print("  This uses: 7 AND(sign, m_i) + 6 OR = 13 vs current 6 OR + 7 AND = 13")
print("  Same count, but maybe sp1 = AND(sign, m0) could be shared with res0?")
print("  res0 = AND(sign, nz). sp1 = AND(sign, m0). Different second operand.")
print("  No obvious sharing.")
print("=" * 70)

# ─────────────────────────────────────────────────────────────────────────────
print()
print("Experiment 16: Can we use the 'carry chain' variant of prefix-OR negation?")
print("  sp_i = OR(sp_{i-1}, AND(sign, m_{i-1})) with sp_0=0")
print("  sp_1 = OR(0, AND(sign, m0)) = AND(sign, m0) [1 AND, save OR]")
print("  sp_2 = OR(sp_1, AND(sign, m1)) [1 OR + 1 AND]")
print("  ...")
print("  sp_7 = OR(sp_6, AND(sign, m6)) [1 OR + 1 AND]")
print("  Total: 7 AND + 6 OR = 13 gates (same)")
print("  But wait: with the chain form, sp_1 = AND(sign,m0) [1 AND, no OR]")
print("  sp_2 = OR(sp_1, AND(sign,m1)) [2 gates]")
print("  Total for sp1..sp7: 1 + 2*6 = 13? No: 7 ANDs + 6 ORs = 13. Same.")
print("=" * 70)

# ─────────────────────────────────────────────────────────────────────────────
print()
print("Experiment 17: Try to eliminate one prefix OR by noting k9_6=m7 is sparse")
print("  m7 = k9_6 (only set for k9=1, S=6)")
print("  p7 = OR(p6, m6): need prefix up to m6 for sp7 (used for r1=XOR(m7,sp7))")
print("  sp7 = AND(sign, p7)")
print("  r1 = XOR(k9_6, AND(sign, OR(p6, m6)))")
print("  Can we skip sp7 entirely? Only if r1 can be computed without it.")
print("  r1 = XOR(m7, sp7)")
print("     = XOR(k9_6, AND(sign, p7))")
print("  When k9_6=0: r1=AND(sign,p7) XOR 0 = AND(sign,p7)")
print("  When k9_6=1: r1=AND(sign,p7) XOR 1 = NOT(AND(sign,p7))")
print("  = XOR(AND(sign,p7), k9_6) -- same computation.")
print("  No savings here.")
print("=" * 70)

# ─────────────────────────────────────────────────────────────────────────────
print()
print("Experiment 18: Try sharing prefix OR with Magnitude-OR tree computation")
print("  The magnitude OR tree computes m0..m7 from AND-terms.")
print("  The prefix OR chain is: p2=OR(m0,m1), p3=OR(p2,m2), ...")
print("  Are any intermediate prefix ORs the same as intermediate mag-OR results?")
print("  mag: m0=OR(nmc0,OR(k3_1,k9_2)), m1=OR(nmc1,OR(k3_2,k9_3)), etc.")
print("  prefix: p2=OR(m0,m1)")
print("  = OR(OR(nmc0,OR(k3_1,k9_2)), OR(nmc1,OR(k3_2,k9_3)))")
print("  This is a fresh combination -- no sharing with any existing subexpression.")
print("=" * 70)

# ─────────────────────────────────────────────────────────────────────────────
print()
print("Experiment 19: Explore if E-sum can be simplified")
print("  s0  = XOR(a3, b3);  c0  = AND(a3, b3)")
print("  s1x = XOR(a2, b2);  s1  = XOR(s1x, c0)")
print("  s2  = OR(AND(a2, b2), AND(s1x, c0))")
print("  This is a 2-bit ripple-carry adder: 7 gates.")
print("  Minimum for 2-bit adder: 7 gates (3 XOR + 3 AND/OR + 1 more OR)")
print("  Already optimal.")
print("=" * 70)

# ─────────────────────────────────────────────────────────────────────────────
print()
print("Experiment 20: nz detection optimization")
print("  or_a23 = OR(a2, a3);   nz_a = OR(a1, or_a23)  [2 gates]")
print("  or_b23 = OR(b2, b3);   nz_b = OR(b1, or_b23)  [2 gates]")
print("  nz = AND(nz_a, nz_b)                            [1 gate]")
print("  Total: 5 gates")
print("  Minimum for NOR(a1,a2,a3) AND NOR(b1,b2,b3): need 2 3-input ORs = 2*2 + AND")
print("  5 gates is optimal for this structure.")
print("=" * 70)

# ─────────────────────────────────────────────────────────────────────────────
print()
print("Experiment 21: Can cond_neg be further reduced using k9_6 sparsity?")
print("  k9_6 is the only contributor to m7.")
print("  r1 = XOR(m7, sp7) = XOR(k9_6, AND(sign, p7))")
print("  p7 = OR(p6, m6). m6 = OR(nmc6, k9_5).")
print("  sp7 = AND(sign, OR(p6, OR(nmc6, k9_5)))")
print("  Can we merge sp7 into the existing OR tree for m6?")
print("  = AND(sign, OR(p6, m6)) where m6 = OR(nmc6, k9_5)")
print("  = OR(AND(sign, p6), AND(sign, m6)) -- distributing AND over OR")
print("  = OR(sp6, AND(sign, m6))")
print("  sp6 is already computed. AND(sign, m6) is a new gate.")
print("  sp7 = OR(sp6, AND(sign, m6)) -- 2 gates instead of OR(p6,m6) [1] + AND(sign,p7) [1] = 2")
print("  Same count. But we save the OR(p6,m6) = p7 gate by folding it.")
print("  Old: p7=OR(p6,m6) [1] + sp7=AND(sign,p7) [1] = 2 gates for sp7")
print("  New: AND(sign,m6) [1] + sp7=OR(sp6,AND(sign,m6)) [1] = 2 gates for sp7")
print("  Same! But now we don't need p7 as an intermediate.")
print("  However p7 was only used for sp7 anyway, so no savings.")
print("=" * 70)

# ─────────────────────────────────────────────────────────────────────────────
print()
print("Experiment 22: Try to save 1 AND by reusing sign in the OR prefix chain")
print("  Current (prefix form): ")
print("  p1=m0 (free), p2=OR(m0,m1) ... p7=OR(p6,m6): 6 ORs")
print("  sp1=AND(sign,p1)...sp7=AND(sign,p7): 7 ANDs")
print("  Total: 13 gates")
print()
print("  Observation: sp7 = AND(sign, p7)")
print("  When nz=0: all m_i=0, p_i=0, sp_i=0. r_i=XOR(m_i,0)=0. Correct.")
print("  When sign=0: sp_i=0, r_i=m_i. Correct.")
print("  When sign=1,nz=1: sp_i = p_i.")
print()
print("  Can we use 'nz' to short-circuit? sp_i=AND(sign,p_i) works because nz=1")
print("  guarantees correct non-zero magnitudes, and nz=0 guarantees m_i=0 hence p_i=0.")
print("  So: sp_i = AND(sign, p_i) already naturally handles nz=0 (p_i=0 trivially).")
print("  No further reduction possible from nz sharing.")
print("=" * 70)

# ─────────────────────────────────────────────────────────────────────────────
print()
print("Final count summary:")
print("=" * 70)
run("baseline (88 gates)", baseline)
run("prefix-OR cond_neg (target: 86 gates)", exp14_verify)
