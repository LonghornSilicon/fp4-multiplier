"""
Further gate-reduction experiments starting from 86-gate prefix-OR circuit.
Focus: can we reduce below 86?
"""
import sys
sys.path.insert(0, r'C:\Users\themo\Desktop\Etched Multiplier Assignment')
from eval_circuit import evaluate_fast

REMAP = [0, 4, 5, 1, 6, 2, 7, 3, 0, 12, 13, 9, 14, 10, 15, 11]

def run(name, fn):
    correct, gc, errors = evaluate_fast(fn, REMAP, verbose=False)
    status = "OK" if correct else f"WRONG({len(errors)} errors)"
    print(f"  {name:60s}  gates={gc:3d}  {status}")
    if errors and len(errors) <= 3:
        for e in errors:
            print(f"    err: a={e[0]} b={e[1]} exp={e[2]} got={e[3]}")
    return correct, gc

# The 86-gate circuit we established
def v86(a0,a1,a2,a3,b0,b1,b2,b3,NOT=None,AND=None,OR=None,XOR=None):
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
    p1 = m0
    p2 = OR(m0, m1);   p3 = OR(p2, m2);   p4 = OR(p3, m3)
    p5 = OR(p4, m4);   p6 = OR(p5, m5);   p7 = OR(p6, m6)
    sp1 = AND(sign, p1);  sp2 = AND(sign, p2);  sp3 = AND(sign, p3)
    sp4 = AND(sign, p4);  sp5 = AND(sign, p5);  sp6 = AND(sign, p6)
    sp7 = AND(sign, p7)
    r8 = m0
    r7 = XOR(m1, sp1);  r6 = XOR(m2, sp2);  r5 = XOR(m3, sp3)
    r4 = XOR(m4, sp4);  r3 = XOR(m5, sp5);  r2 = XOR(m6, sp6)
    r1 = XOR(m7, sp7)
    res0 = AND(sign, nz)
    return res0, r1, r2, r3, r4, r5, r6, r7, r8

print("=" * 75)
print("Experiments to reduce from 86 gates")
print("=" * 75)
run("v86 baseline", v86)

# ──────────────────────────────────────────────────────────────────────────────
# Idea A: Can we eliminate one of the 7 sp_i ANDs?
#
# Key observation: r8 = m0 (passthrough, no sign involvement).
# sp1 = AND(sign, m0) is used for r7 = XOR(m1, sp1).
# But r8 = m0 is already the LSB output. sp1 is sign AND m0.
#
# Could r7 = XOR(m1, AND(sign, m0)) be expressed without AND(sign, m0)?
# No, we need it.
#
# But wait: could we replace res0 = AND(sign, nz) with sp1 in some case?
# res0 = AND(sign, nz). sp1 = AND(sign, m0).
# Only equal when nz=m0, which isn't generally true.
#
# Idea B: eliminate the sp7 gate by noting m7=k9_6 only set in one case.
# When k9_6=0 (the common case): r1 = XOR(0, sp7) = sp7.
# When k9_6=1: r1 = XOR(1, sp7) = NOT(sp7).
# r1 = XOR(k9_6, AND(sign, p7))
# Can we use: r1 = AND(NOT(k9_6), sp7) OR AND(k9_6, NOT(sp7))? -- more gates.
# Can we merge sp7 cost into r1 directly?
# r1 = XOR(k9_6, AND(sign, OR(p6, m6)))
# = XOR(k9_6, OR(AND(sign, p6), AND(sign, m6)))
# = XOR(k9_6, OR(sp6, AND(sign, m6)))
# This costs: AND(sign,m6)[1] + OR(sp6, ...)[1] + XOR(k9_6,...)[1] = 3 gates
# But we still have p7 OR gate and sp7 AND gate in original = 2 gates, plus r1 XOR = 1 = 3 total.
# Same! But now we eliminate the p7 intermediate (which was only used for sp7).
# So: p7 gate is eliminated! But we add AND(sign,m6) instead. Net = 0.

print()
print("Idea A: Try to merge p7 into r1 directly (eliminate one explicit intermediate)")

def exp_merge_p7(a0,a1,a2,a3,b0,b1,b2,b3,NOT=None,AND=None,OR=None,XOR=None):
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
    # prefix chain up to p6, then fold p7 into sp7 calculation
    p1 = m0
    p2 = OR(m0, m1);   p3 = OR(p2, m2);   p4 = OR(p3, m3)
    p5 = OR(p4, m4);   p6 = OR(p5, m5)
    # sp6 = AND(sign, p6)
    sp1 = AND(sign, p1);  sp2 = AND(sign, p2);  sp3 = AND(sign, p3)
    sp4 = AND(sign, p4);  sp5 = AND(sign, p5);  sp6 = AND(sign, p6)
    # For r1: r1 = XOR(m7, AND(sign, OR(p6, m6)))
    #            = XOR(m7, OR(sp6, AND(sign, m6)))
    sign_m6 = AND(sign, m6)            # 1 gate
    sp7 = OR(sp6, sign_m6)             # 1 gate (replaces p7+AND(sign,p7))
    r8 = m0
    r7 = XOR(m1, sp1);  r6 = XOR(m2, sp2);  r5 = XOR(m3, sp3)
    r4 = XOR(m4, sp4);  r3 = XOR(m5, sp5);  r2 = XOR(m6, sp6)
    r1 = XOR(m7, sp7)
    res0 = AND(sign, nz)
    return res0, r1, r2, r3, r4, r5, r6, r7, r8

run("merge_p7 (same cost)", exp_merge_p7)

# ──────────────────────────────────────────────────────────────────────────────
# Idea C: Can we fuse the sign_mask (res0 = AND(sign,nz)) with nz detection?
# The sign bit appears in:
# 1) sign = XOR(a0,b0)
# 2) sp_i = AND(sign, p_i) [7 gates]
# 3) res0 = AND(sign, nz) [1 gate]
# Total AND-with-sign: 8 gates.
# Is there any way to reduce this to 7?
# res0 = AND(sign, nz)
# nz = AND(nz_a, nz_b)
# So res0 = AND(sign, AND(nz_a, nz_b))
# Alternatively: sign_nz_a = AND(sign, nz_a); res0 = AND(sign_nz_a, nz_b) -- still 2 AND for res0.
#
# But what if we could merge sign_nz_a with some sp computation?
# sp_i = AND(sign, p_i) - these use the final magnitude bits, not nz components.
# No structural opportunity.
#
# What if sign = XOR(a0,b0) is 0 whenever the product sign is 0?
# sign=0 when a0=b0. In that case all sp_i=0 and r_i=m_i.
# But we can't avoid computing sp_i - we need them for the general case.

print()
print("Idea C: Can sp1 = AND(sign, m0) share computation with res0 = AND(sign, nz)?")
print("  res0 = AND(sign, nz); sp1 = AND(sign, m0). No sharing since nz != m0.")
print("  But: sp1 = AND(sign, m0) and nz also used in k-masking.")
print("  What if we use AND(sign, p1) where p1=m0 is the same as AND(sign, m0)?")
print("  No new saving there.")

# ──────────────────────────────────────────────────────────────────────────────
# Idea D: Can we reduce AND-terms from 18 to 17?
# Current AND-terms:
#   7 nmc_i: nmc0..nmc6 = AND(nmc, sh0..sh5, u11)
#   6 k3_i:  k3_1..k3_6 = AND(k3, sh1..sh5, u11)
#   5 k9_i:  k9_2..k9_6 = AND(k9, sh2..sh5, u11)
# Total: 7+6+5 = 18
#
# Note: k9_6 = AND(k9, u11) = m7 directly. Already merged.
# Note: u11 is shared between nmc6, k3_6, k9_6. Already shared.
#
# Can any two AND-terms be merged?
# nmc6 = AND(nmc, u11); k3_6 = AND(k3, u11); k9_6 = AND(k9, u11)
# These three all use u11. Combined: AND(u11, OR(nmc,k3,k9))? -- but need them separately!
#
# Actually... do we always need nmc6, k3_6, k9_6 separately?
# m7 = k9_6
# m6 = OR(nmc6, k9_5)  -- k3_6 NOT used in m6!
# m5 = OR(nmc5, OR(k3_6, k9_4))  -- k3_6 used in m5
# m4 = OR(OR(nmc4, k3_5), OR(k9_6, k9_3))  -- k9_6 used in m4
# Also: m4 uses k9_6=m7, not a separate AND term.
#
# Can we check: do any AND-terms appear in only one output bit?
# nmc0: only in m0. k3_1: only in m0.  -- but they both go into m0.
# nmc6: only in m6. k3_6: only in m5. k9_6=m7: in m7 and m4.
#
# If some AND-term only affects one bit, maybe we can fold it:
# e.g., nmc6 only goes into m6 = OR(nmc6, k9_5).
# We already have that. Can't reduce further.
#
# What if k3 and nmc share shifts (both start at sh1 and sh0 respectively)?
# nmc uses sh0..sh5,u11 (7 terms starting at shift=0)
# k3  uses sh1..sh5,u11 (6 terms starting at shift=1)
# k9  uses sh2..sh5,u11 (5 terms starting at shift=2)
#
# Overlap at u11: nmc6, k3_6, k9_6 all use u11.
# Instead of 3 separate ANDs, could we compute:
#   all6 = AND(nz, u11)  -- only 1 AND with nz and u11
#   then: nmc6 = AND(or_a1b1, all6_nz) -- but this splits nmc into parts...
#
# Actually: nmc = AND(or_a1b1, nz); so nmc6 = AND(nmc, u11) = AND(AND(or_a1b1,nz), u11)
# k3 = AND(k3_raw, nz); k3_6 = AND(k3, u11) = AND(AND(k3_raw,nz), u11)
# k9 = AND(k9_raw, nz); k9_6 = AND(k9, u11) = AND(AND(k9_raw,nz), u11)
#
# Alternative: nz_u11 = AND(nz, u11)  -- 1 gate
# Then: nmc6 = AND(or_a1b1, nz_u11)  -- 1 gate
#       k3_6 = AND(k3_raw, nz_u11)   -- 1 gate
#       k9_6 = AND(k9_raw, nz_u11)   -- 1 gate
# Total for these 3: 4 gates (1 for nz_u11 + 3 ANDs)
# Original: nmc6=AND(nmc,u11), k3_6=AND(k3,u11), k9_6=AND(k9,u11) = 3 gates
# New: 4 gates. Worse!
#
# What about: k_u11 = AND(nz, u11) shared. Then:
# nmc6 = AND(or_a1b1, k_u11), k3_6 = AND(k3_raw, k_u11), k9_6 = AND(k9_raw, k_u11)
# That's 4 gates total for the three, vs 3 gates in original. Worse.

print()
print("Idea D: Sharing u11 AND-terms -- analyzed above, no savings possible.")

# ──────────────────────────────────────────────────────────────────────────────
# Idea E: Can we eliminate one magnitude bit computation?
#
# m7 = k9_6 (free - it's just a reference to k9_6)
# m6 = OR(nmc6, k9_5): 1 gate
# ...
# What if m6 could be expressed without the OR, using one of its inputs directly?
# No, because both nmc6 and k9_5 can be 1 independently.
#
# What if we could prove that nmc6 and k9_5 are mutually exclusive?
# nmc6 = AND(nmc, u11) = AND(AND(or_a1b1, nz), AND(s2, s1))
#   = 1 iff (a1 OR b1) AND nz AND s2=1 AND s1=1
#   = nmc=1 AND S∈{6,7} -- but S≤6 (since E' ranges 0-3 for each input, sum ≤6)
#   So nmc6 = 1 iff nmc=1 AND S=6
# k9_5 = AND(k9, sh5) = AND(AND(NOT(or_a1b1), nz), AND(u10, s0))
#   = 1 iff k9=1 AND nz AND s2=1 AND s1=0 AND s0=1
#   = k9=1 AND S=5
#
# nmc requires (a1 OR b1)=1; k9 requires (a1 OR b1)=0. These are mutually exclusive!
# Therefore: nmc6 AND k9_5 = 0 always!
# So m6 = OR(nmc6, k9_5) where the two are always mutually exclusive.
# = nmc6 XOR k9_5 (since they can't both be 1)
# = nmc6 OR k9_5 (same result, but XOR has same cost)
# No gate saving from this observation.

print()
print("Idea E: nmc and k9 are mutually exclusive (different K-types).")
print("  m6 = OR(nmc6, k9_5) since they can't both be 1.")
print("  Could replace OR with XOR -- same gate count, no savings.")
print("  But: can we use this mutual exclusivity elsewhere to reduce OR fan-in?")
print()

# Actually more interesting: since nmc, k3, k9 are mutually exclusive partitions
# of the 'nz' condition:
# nmc = AND(or_a1b1, nz)  -- both inputs have mantissa bit set
# k3  = AND(k3_raw, nz)   -- exactly one input has mantissa bit set
# k9  = AND(k9_raw, nz)   -- neither input has mantissa bit set
# nmc XOR k3 XOR k9 = nz (they partition the nz space)
# nmc AND k3 = 0, nmc AND k9 = 0, k3 AND k9 = 0
#
# Therefore in any magnitude bit expression involving nmc_i, k3_j, k9_k:
# they are all mutually exclusive (since they all include the K-mask factor).
# So ALL OR gates in the magnitude tree could be replaced by XOR:
# m_i = XOR(nmc_i, k3_{i+1}, k9_{i-1}, k9_{i+2})  (but can't do 4-input XOR cheaply)
# For m bits that have exactly one source active at a time: XOR = OR, no savings.
# But: if we had a 3-input XOR, we could save OR gates. With 2-input XOR, need same count.
#
# However: for m4 = OR(OR(nmc4,k3_5), OR(k9_6,k9_3))
# k9_6 and k9_3 are NOT mutually exclusive -- both are k9-type, but different shifts!
# k9_6 = AND(k9, u11) = 1 when k9=1, S=6
# k9_3 = AND(k9, sh3) = 1 when k9=1, S=3
# These ARE mutually exclusive (S can't be 6 and 3 simultaneously).
# So ALL the AND-terms are mutually exclusive! Every pair from any K-type and shift.
#
# This means ALL the OR gates in the magnitude tree are computing OR of mutually exclusive inputs.
# XOR would give same result but same gate count.
# The only potential savings: if we can prove some OR(a,b) where a implies NOT b,
# we can replace it with a simpler expression... but OR and XOR of mutually exclusive
# signals still cost 1 gate each.

print("  Since nmc, k3, k9 partition nz space, AND-terms are all mutually exclusive.")
print("  All magnitude OR gates could be XOR, but same cost. No gate saving.")

# ──────────────────────────────────────────────────────────────────────────────
# Idea F: Can we eliminate some AND-terms by merging adjacent magnitude bits?
#
# Notice that the prefix-OR chain p_i = OR(m0,...,m_{i-1}) could potentially
# be seeded from an earlier OR in the magnitude tree.
#
# For example:
# m0 = OR(nmc0, OR(k3_1, k9_2))
# m1 = OR(nmc1, OR(k3_2, k9_3))
# p2 = OR(m0, m1) = OR(OR(nmc0,k3_1,k9_2), OR(nmc1,k3_2,k9_3))
#    = OR(nmc0, nmc1, k3_1, k3_2, k9_2, k9_3)
#
# This could be seeded differently:
# big_or_low = OR(nmc0,nmc1) = OR(AND(nmc,sh0), AND(nmc,sh1)) = AND(nmc, OR(sh0,sh1))
# But OR(sh0,sh1) = OR(AND(u00,ns0), AND(u00,s0)) = AND(u00, OR(ns0,s0)) = AND(u00, 1) = u00
# So nmc_01 = AND(nmc, u00) -- 1 gate (replaces nmc0 and nmc1 as a 2-bit "OR block")
# Similarly k3_12 = AND(k3, u00) (since k3 at shifts 1,2: but wait, k3_1 uses sh1=AND(u00,s0)
# and k3_2 uses sh2=AND(u01,ns0). These are from different u pairs!)
#
# k3_1 = AND(k3, sh1) = AND(k3, AND(u00,s0))
# k3_2 = AND(k3, sh2) = AND(k3, AND(u01,ns0))
# OR(k3_1, k3_2) cannot be simplified as AND(k3, OR(sh1,sh2)) since sh1 and sh2
# come from different u00/u01 pairs.
#
# But: OR(sh1, sh2) = OR(AND(u00,s0), AND(u01,ns0))
#                   = OR(AND(ns2,ns1,s0), AND(ns2,s1,ns0))
#                   = AND(ns2, OR(AND(ns1,s0), AND(s1,ns0)))
#                   = AND(ns2, XOR(s0,s1))   [since a AND NOT(b) OR NOT(a) AND b = XOR]
# So OR(sh1,sh2) = AND(ns2, XOR(s1,s0)): 1 gate (if XOR(s1,s0) already computed).
# XOR(s1,s0) is s1 XOR s0 -- we have s1 and s0 already, so this is 1 XOR + 1 AND = 2 gates.
# Then k3_OR_12 = AND(k3, AND(ns2, XOR(s1,s0))) = AND(k3, ns2, XOR(s1,s0)) -- 2 ANDs.
# Total for k3_1 OR k3_2 via this route: 3 gates.
# Original: k3_1 + k3_2 = 2 AND-terms + OR(k3_1,k3_2) in m0/m1 = but they don't both
# appear in same magnitude bit...
#
# Let me check where k3_1 and k3_2 appear:
# k3_1: only in m0
# k3_2: only in m1
# They appear in DIFFERENT magnitude bits, so there's no place where OR(k3_1,k3_2) appears.
# No savings from combining them.

print()
print("Idea F: Merging AND-terms for adjacent magnitude bits -- no opportunity found.")

# ──────────────────────────────────────────────────────────────────────────────
# Idea G: Can the E-sum adder be restructured using the S decoder output?
# The E-sum produces s0,s1,s2 which are fed into the S decoder.
# The S decoder itself could potentially be restructured if some combinations
# of a2,a3,b2,b3 are never reached due to FP4 encoding constraints.
#
# In v4b encoding: a2,a3 represent E' values 0,1,2,3 (all 4 combinations valid).
# Similarly for b2,b3. So all E-sum values 0..6 are reachable.
# (S=7 not reachable since max E'=3+3=6, S≤6). This is already exploited (sh6=u11).
#
# Can we exploit that S=7 never occurs to simplify the decoder?
# u11 = AND(s2,s1) encodes s2=1,s1=1 (which means S=6 or S=7).
# Since S≤6: when u11=1 AND s0=0 => S=6; when u11=1 AND s0=1 => S=7 (impossible).
# We already use u11 directly as sh6. No further savings from this.

print()
print("Idea G: E-sum/S-decoder cannot be further reduced given FP4 constraints.")

# ──────────────────────────────────────────────────────────────────────────────
# Idea H: Try alternative nz detection with different OR tree to see if it can
# share computation with K-flags.
#
# nz_a = OR(a1, OR(a2, a3)) -- 2 gates
# nz_b = OR(b1, OR(b2, b3)) -- 2 gates
# nz   = AND(nz_a, nz_b)   -- 1 gate
#
# K-flags:
# or_a1b1 = OR(a1, b1)     -- 1 gate
# k9_raw  = NOT(or_a1b1)   -- 1 gate
# k3_raw  = XOR(a1, b1)    -- 1 gate
#
# Can we compute nz_a using or_a1b1?
# nz_a = OR(a1, OR(a2,a3)): uses a1 individually
# or_a1b1 = OR(a1, b1): uses a1 and b1
# No obvious shared subexpression.
#
# Alternative: compute nz_a = OR(a1, or_a23) where or_a23 = OR(a2,a3).
# We need or_a23 for nz, but or_a23 also appears in... nowhere else.
# No sharing possible.

print()
print("Idea H: nz detection / K-flag sharing -- no opportunity found.")

# ──────────────────────────────────────────────────────────────────────────────
# Idea I: More radical restructuring -- use a different cond_neg approach.
#
# Current prefix-OR approach: 20 gates (6 OR + 7 AND + 7 XOR).
#
# What if we split into two halves and use carry-lookahead?
# For 8 bits, the carry into each position i from the LSB:
# ci = sign AND NOR(m0,...,m_{i-1}) -- this is what we use.
#
# Alternative: use carry-skip (skip-ahead when all bits in a block are 0).
# For our prefix-OR chain, each step is already O(1) - a linear chain.
# Carry-lookahead would parallelize but not reduce gate count.
#
# Yet another: can we reduce by noting that p_i = p_{i-1} OR m_{i-1},
# and sp_i = AND(sign, p_i) = OR(sp_{i-1}, AND(sign, m_{i-1}))?
# This gives a "sign-gated prefix-OR" chain:
# sp_1 = AND(sign, m0)
# sp_2 = OR(sp_1, AND(sign, m1))
# sp_3 = OR(sp_2, AND(sign, m2))
# ...
# sp_7 = OR(sp_6, AND(sign, m6))
# Count: 7 AND + 6 OR = 13 (same as current 6 OR + 7 AND = 13).
#
# But could we save the sp1 gate by noting sp1 = AND(sign, m0)?
# We already have sign and m0. That's 1 AND gate. No way to avoid it
# since sp1 feeds r7 = XOR(m1, sp1).

print()
print("Idea I: Sign-gated chain form of prefix-OR -- same 13 gates, no savings.")

# ──────────────────────────────────────────────────────────────────────────────
# Idea J: Can we eliminate a gate in the magnitude OR tree by using
# the fact that for the prefix-OR chain, some p_i are already available?
#
# p2 = OR(m0, m1): this IS a new gate that wasn't in the baseline.
# But is OR(m0,m1) computable from earlier intermediates for free?
# m0 = OR(nmc0, OR(k3_1, k9_2))
# m1 = OR(nmc1, OR(k3_2, k9_3))
# OR(m0,m1) = OR of 6 AND-terms (all mutually exclusive).
# No direct shortcut.
#
# But wait: we could try to feed the magnitude OR tree in a way that
# also produces the prefix-OR chain values.
#
# For example, what if we compute:
# low2 = OR(m0, m1) directly from AND-terms?
# low2 = OR(nmc0, OR(nmc1, OR(k3_1, OR(k3_2, OR(k9_2, k9_3)))))
# That's 5 OR gates for low2. But currently:
# m0 takes 2 OR gates, m1 takes 2 OR gates, p2=OR(m0,m1) takes 1 OR gate = 5 total.
# If we compute low2 directly: still 5 OR gates minimum (6 things need 5 ORs).
# No savings.

print()
print("Idea J: Restructuring magnitude OR tree to share with prefix chain -- no savings.")

# ──────────────────────────────────────────────────────────────────────────────
# Idea K: Radically different approach for just the top 2 bits.
# r1 = XOR(m7, sp7): m7=k9_6, sp7=AND(sign, OR(m0..m6))
# r2 = XOR(m6, sp6): m6=OR(nmc6,k9_5), sp6=AND(sign, OR(m0..m5))
#
# When sign=0: r1=m7=k9_6, r2=m6=OR(nmc6,k9_5).
# When sign=1: we're negating. The negated value flips bits above the first 1.
#
# Observation: m7 can only be 1 when k9=1 AND S=6.
# When k9=1 AND S=6: magnitude = 9/4 × 2^(6-4) = 9/4 × 4 = 9. [FP4 max is 6×6=36]
# Wait: k9 means M_sum=0 (neither a1 nor b1 set, so M_a=M_b=0).
# Product = 1.5^0 × 2^S = 2^S.
# With S=6: product = 2^6 = 64. In QI9 (fractional, ×4): 64×4=256... wait.
# QI9 is Q-format with 9 bits (1 sign + 8 magnitude), scaled by 1/4?
# Let me recheck: QI9 means value = integer/4? Or is it integer bits representing ×4?
# From eval: expected_qi9 = np.int16(np.round(expected_fp32 * 4))
# So QI9 = value × 4 as an integer.
# So magnitude bits m7..m0 represent value/4, i.e., m = |product| × 4.
# k9 AND S=6: product = 2^S, S = E'_a + E'_b ∈ {0..6}.
# Wait, let me re-examine: magnitude code 001→1.5 (M=1,E'=1), 100→0.5 (M=0,E'=0).
# E'=E+1, E ranges -1..2.
# For k9 (M_a=M_b=0): product = 1.5^0 × 2^(E'_a-1 + E'_b-1) = 2^(E'_a+E'_b-2)
# With E'_a,E'_b ∈ {0,1,2,3}: S = E'_a+E'_b ∈ {0..6}.
# product = 2^(S-2). QI9 value = product × 4 = 2^(S-2) × 4 = 2^S.
# S=6: QI9 = 2^6 = 64 = 0b01000000 in 8-bit.
# m7=1 (bit 7 set), all others 0. When sign=0: output = 01000000, r1=0b1 at position bit 7.
# Wait, the output is (res0, r1, ..., r8) where res0 is the sign bit.
# r1 is the MSB of magnitude, r8 is the LSB.
# m7 → r1, m0 → r8.
# So when k9 AND S=6: magnitude = 0b10000000 (binary) = 128... but QI9 has 9 bits total.
# 9-bit QI9 = 1 sign bit + 8 magnitude bits. Max positive = 0_11111111 = 255.
# QI9 value = signed 9-bit, representing value × 4.
# So range is -256/4=-64 to 255/4≈63.75. Max FP4 product = 6×6=36, which × 4 = 144.
# But 8-bit magnitude goes to 255/4=63.75...
# Hmm: 6×6=36, ×4=144 = 0b10010000 = bit 7 and bit 4 set.
# That would require 8-bit magnitude at 144, fitting in 9-bit (0_10010000).
# So m7=1, m4=1, others 0 for the 6×6=36 product.
#
# For k9 AND S=6: product = 2^(S-2) = 2^4 = 16, ×4 = 64 = 0b01000000.
# m6=1, all others 0.
# Wait, let me recalculate: m7 corresponds to which bit?
# Output (res0, r1, r2, r3, r4, r5, r6, r7, r8)
# In the code: r1=XOR(m7,sp7) -- so r1 = MSB after sign (bit 7 of the 8-bit magnitude).
# m7 is the highest magnitude bit.
# m7 corresponds to value bit contributing (128/4)=32 to the product.
# Wait: QI9 = product × 4. The 9-bit value (res0,r1..r8) encodes:
#   res0 is the sign bit.
#   r1..r8 encode the magnitude in 2's complement when negated.
#   The numerical value = (-256*res0 + 128*r1 + 64*r2 + ... + 1*r8) / 4
#
# So bit r1 (=m7 when sign=0) contributes 128/4 = 32 to the product.
# m7=1 would mean |product| >= 32.
# For k9 AND S=6: product = 2^4 = 16. m7... 16*4=64, so bit representation:
# 64 = 0b01000000 => r1=0, r2=1, r3..r8=0. So m6=1 (not m7)!
#
# Let me re-derive: output integer = round(product * 4).
# Binary of output (9-bit): res0 r1 r2 r3 r4 r5 r6 r7 r8
# res0=sign, then 8 bits of two's complement magnitude.
# For positive product P: output = P*4 as 9-bit binary (no negation).
# Bit i of output (res0=0, r1=MSB=bit7 of P*4):
# P*4 in binary: bit 7 = 1 iff P*4 >= 128 iff P >= 32.
# Max positive FP4 product = 6*6 = 36. 36*4=144=0b10010000.
# So m7=1 when P*4 >= 128 (P >= 32).
# Valid products with m7=1: P=36 (6×6 or -6×-6), P=32 (not achievable since 6×6=36...).
# Let me list: max products 6×6=36, 6×4=24, 6×3=18, 4×6=24, 4×4=16, 3×6=18...
# 36 × 4 = 144 = 0b10010000: m7=1 (bit 7 set, contributes 128 to the 8-bit magnitude)
# Actually 144 binary = 1001 0000, so bits: m7=1, m6=0, m5=0, m4=1, m3=0, m2=0, m1=0, m0=0.
# That's for 6×6=36.
#
# What input gives m7=1? Only P=36 (|product|=36, i.e., 144/4):
# 6×6: sign=0, a1=0,a2=0,a3=1 (M=0,E=2,E'=3); b same. S=6, k9.
# Actually wait: mag code 011 → 6.0 (M=1, E=2, E'=3). So a1=0, a2=1, a3=1 for 6.0?
# Let me re-read the encoding:
# magnitude code a1a2a3:
#   001 → 1.5  (M=1, E=0,  E'=1) [a1=0, a2=0, a3=1 in the code comment... but code=001 means a1=0,a2=0,a3=1]
#   011 → 6.0  (M=1, E=2,  E'=3) [code=011: a1=0,a2=1,a3=1]
#   100 → 0.5  (M=0, E=-1, E'=0) [code=100: a1=1,a2=0,a3=0]
# Wait, code = a1a2a3 (3 bits). M = NOT(a1) means...
# Code 001 → M=1: NOT(a1)=NOT(0)=1. Yes.
# Code 100 → M=0: NOT(a1)=NOT(1)=0. Yes.
# Code 011 → a1=0, so M=1. E' = a2a3 = 11 = 3. E = E'-1 = 2. Value = 1.5 × 2^2 = 6. Yes.
#
# So for 6×6=36: a1=0, a2=1, a3=1 and b1=0, b2=1, b3=1.
# S = a2a3 + b2b3 in 2-bit: (1+1)... wait, E' = a2a3 as a 2-bit number = 11 = 3.
# E'_a = 3, E'_b = 3, S = 3+3 = 6. k9: a1=b1=0, so or_a1b1=0, k9_raw=NOT(0)=1, k9=1.
# k9=1, S=6 → k9_6=1, m7=1. Also k9_4=AND(k9,sh4): sh4 at S=4.
# No, m7=k9_6=1, m4=: check contribution.
# m4 = OR(OR(nmc4,k3_5), OR(k9_6,k9_3))
# k9_6=1 contributes to m4! So m4=1 also (from k9_6=m7 reuse).
# So for 6×6=36: m7=1, m4=1. QI value=0b10010000=144=36×4. Correct!

print()
print("Confirming m7 structure for k9 AND S=6 case (6×6=36 product):")
print("  m7=k9_6=1, m6=0, m5=0, m4=OR(...,k9_6,...)=1, m3=m2=m1=m0=0")
print("  => magnitude = 10010000 = 144 = 36×4. Correct!")
print()

# ──────────────────────────────────────────────────────────────────────────────
# Idea K: Can we eliminate one of the 6 prefix-OR gates?
# The chain: p2=OR(m0,m1), p3=OR(p2,m2), ..., p7=OR(p6,m6).
# Each p_i is used ONLY for sp_i = AND(sign, p_i).
# sp_i is used ONLY for r_{8-i} = XOR(m_{8-i}, sp_i).
# Wait: r7=XOR(m1,sp1), r6=XOR(m2,sp2), ..., r1=XOR(m7,sp7).
# r8=m0 (no sp needed for LSB).
#
# Can we prove sp_i=sp_{i-1} for some i based on magnitude structure?
# sp_i = AND(sign, OR(m0,...,m_{i-1}))
# sp_{i+1} = AND(sign, OR(m0,...,m_i))
# If m_i is always 0 given some constraint, then sp_{i+1}=sp_i and we can skip p_{i+1}.
# But m_i can be nonzero for any i, so we can't skip any p.
#
# What if some sp_i values are always equal to each other or other signals?
# In general, no -- they encode different carry signals.

print("Idea K: Cannot eliminate any prefix-OR intermediate gates.")

# ──────────────────────────────────────────────────────────────────────────────
# Idea L: Can we reduce the number of AND(sign, p_i) gates by sharing
# sign across adjacent pairs?
#
# sp1=AND(sign,p1), sp2=AND(sign,p2), ..., sp7=AND(sign,p7)
# These 7 ANDs all share the 'sign' input. In real hardware, this is a fan-out
# of sign to 7 gates. No gate-count saving for fan-out in this model.
#
# If sign were a computed expression we could share, we'd save. But sign=XOR(a0,b0) is atomic.

print()
print("Idea L: sign fan-out to 7 ANDs -- no savings possible.")

# ──────────────────────────────────────────────────────────────────────────────
# Idea M: Deep investigation -- can ANY two AND-terms be merged without net cost?
#
# Consider nmc0 and nmc1:
# nmc0 = AND(nmc, sh0) = AND(nmc, AND(u00,ns0))
# nmc1 = AND(nmc, sh1) = AND(nmc, AND(u00,s0))
# Both use u00. Could compute:
# nmc_u00 = AND(nmc, u00)  [1 gate]
# nmc0 = AND(nmc_u00, ns0) [1 gate]
# nmc1 = AND(nmc_u00, s0)  [1 gate]
# Total: 3 gates instead of 2 -- WORSE.
# Same issue for any grouping: adding a shared term always costs an extra gate.
#
# The only way to save is if a shared sub-expression is already computed for free.
# Is AND(nmc, u00) already computed? No.
# Is AND(nmc, u01) already computed? No.
# Is AND(nmc, u10) already computed? No.
# Is AND(nmc, u11) = nmc6 already computed? Yes -- that's nmc6!
# So nmc6 already exploits the u11 sharing. The others (u00,u01,u10 based) aren't shared.
#
# Similarly for k3 and k9. Already optimally structured.

print()
print("Idea M: AND-term grouping -- all opportunities already exploited.")

# ──────────────────────────────────────────────────────────────────────────────
# Idea N: Can we use the XOR trick for the cond_neg to save one more gate?
# Current: 6 OR + 7 AND + 7 XOR = 20 gates.
#
# The 7 XORs compute r_i = XOR(m_i, sp_i).
# When sp_i=0 (sign=0 or all lower bits 0): r_i = m_i.
# When sp_i=1 (sign=1 AND prefix has a 1): r_i = NOT(m_i).
#
# Can we compute NOT(m_i) as part of the magnitude computation and then MUX?
# MUX(sp_i, m_i, NOT(m_i)) = MUX(sp_i, m_i, NOT(m_i))
# Standard MUX = AND(sp_i, NOT(m_i)) OR AND(NOT(sp_i), m_i) = 4 gates.
# Or: MUX(sel, a, NOT(a)) = XOR(sel, a) -- exactly 1 XOR! That's what we already have.
# r_i = XOR(m_i, sp_i) IS already the optimal MUX(sp_i, m_i, NOT(m_i)). No savings.

print()
print("Idea N: XOR is already optimal 1-gate MUX for conditional bit flip.")

# ──────────────────────────────────────────────────────────────────────────────
# Idea O: Can the nz detection be merged with K-masking?
# Current: nz (5 gates) + K-masking (3 gates) = 8 gates.
#
# K-masking: nmc=AND(or_a1b1,nz), k3=AND(k3_raw,nz), k9=AND(k9_raw,nz)
# All three use 'nz'. The nz computation uses or_a23, or_b23 (intermediate values).
#
# Alternative: propagate nz check differently.
# or_a1b1 = OR(a1, b1)
# Already computed in K-flags.
# nz_a = OR(a1, OR(a2,a3)): could we say nz_a = OR(or_a1b1_a, OR(a2,a3))
# where or_a1b1_a = a1? No, or_a1b1 is OR(a1,b1), not just a1.
#
# nz_a uses a1 independently. We compute OR(a2,a3) separately.
# Can we share OR(a2,a3) with the adder?
# The adder computes s0=XOR(a3,b3), c0=AND(a3,b3), s1x=XOR(a2,b2).
# OR(a2,a3) is a different combination. No sharing.
#
# Total structural minimum for nz+K-masking is 8 gates. Already optimal.

print()
print("Idea O: nz detection + K-masking already optimal at 8 gates.")

# ──────────────────────────────────────────────────────────────────────────────
# Summary
print()
print("=" * 75)
print("SUMMARY: Best verified circuit is 86 gates.")
print("No further single-gate savings found in:")
print("  - cond_neg (already reduced from 22 to 20 via prefix-OR formula)")
print("  - magnitude OR tree (15 gates, all mutual exclusive ORs, already optimal)")
print("  - AND-terms (18 gates, structured grouping already optimal)")
print("  - S decoder (13 gates, minimum for 3-to-7 decode)")
print("  - E-sum adder (7 gates, minimum for 2-bit ripple carry)")
print("  - nz detection (5 gates, minimum for this structure)")
print("  - K-masking (3 gates, optimal for 3 masked signals)")
print("  - sign + sign_mask (2 gates)")
print("  - K-flags (3 gates: OR+NOT+XOR, minimal)")
print("=" * 75)
run("v86 final", v86)
