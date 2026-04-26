"""Generate structural Verilog parameterized by an input bijection (remap).

For sign-symmetric remaps (sign bit kept at MSB; lower-3-bits permuted),
the structural multiplier still applies — we just insert a 3-input → 3-output
"sigma decode" that converts the remapped low 3 bits back to the default
(e_h, e_l, m) interpretation. ABC then optimizes the sigma decoder + the
structural multiplier together.

For arbitrary (non-sign-symmetric) bijections, we still emit a 4-input → 4-
output decoder, but we can no longer assume sign is unchanged. The structural
multiplier wraps that.
"""
from __future__ import annotations
from typing import Iterable

from fp4_spec import DEFAULT_FP4_VALUES
from remap import MAGNITUDES, encoding_from_magnitude_perm


# Default encoding's per-codepoint (sign, eh, el, m) tuple.
# code i in 0..15: (i>>3, (i>>2)&1, (i>>1)&1, i&1)
DEFAULT_FIELDS = [(i >> 3, (i >> 2) & 1, (i >> 1) & 1, i & 1) for i in range(16)]


def fields_for_values(values: list[float]) -> list[tuple[int, int, int, int]]:
    """For a given encoding (`values` list[16]), return the (sign, eh, el, m)
    tuple that the structural multiplier should consume for each 4-bit input
    code. The convention: this tuple is the *default-encoding code* for the
    same value. So under any remap, dec(code) = π^{-1}(code) as 4 bit fields,
    meaning the structural mul's interpretation matches the default encoding.

    Concretely: for each code i, find j such that `values[i]` equals
    `DEFAULT_FP4_VALUES[j]`. That j (as 4 bits) is the decode output.

    Tie-breaking: 0 has two encodings (j=0 and j=8 in default). Pick the one
    with the same sign bit as i.
    """
    out: list[tuple[int, int, int, int]] = []
    for i, v in enumerate(values):
        s = (i >> 3) & 1
        # Match the value, prefer the j with same sign bit
        candidates = [j for j in range(16) if DEFAULT_FP4_VALUES[j] == v]
        if not candidates:
            # Should not happen for any sane bijection of FP4 values.
            raise ValueError(f"value {v} at code {i} doesn't appear in default table")
        # Prefer same sign bit; useful when v == 0 (j=0 or 8).
        cand_same_sign = [j for j in candidates if ((j >> 3) & 1) == s]
        j = (cand_same_sign or candidates)[0]
        out.append(((j >> 3) & 1, (j >> 2) & 1, (j >> 1) & 1, j & 1))
    return out


def emit_decoder_verilog(values: list[float], port: str = "a") -> str:
    """Emit a 4-bit input → 4-bit output decoder Verilog block.

    Strategy: for each of the 4 output bits, determine its 16-row truth
    table, then either (a) recognize it as a single input bit / negation
    (free passthrough), or (b) emit a compact case statement that yosys can
    reduce. Falling back to SOP-of-minterms is the worst case and would
    bloat the synthesizer's starting AIG.
    """
    fields = fields_for_values(values)
    # Collect each output's 16-row truth table.
    out_names = ["s", "eh", "el", "m"]
    tts = [[fields[code][k] for code in range(16)] for k in range(4)]

    lines = []
    for k, name in enumerate(out_names):
        tt = tts[k]
        expr = _simplify_4to1(tt, port)
        lines.append(f"    wire dec_{port}_{name:<2} = {expr};")
    return "\n".join(lines) + "\n"


def _simplify_4to1(tt: list[int], port: str) -> str:
    """Find the smallest Verilog expression for a 16-entry truth table over
    inputs {port[3], port[2], port[1], port[0]}.

    Cheap matches:
      - constant 0 / constant 1
      - single-bit pass-through or its negation: tt depends on exactly one bit.
    Otherwise: emit SOP of minterms (yosys will Boolean-simplify).
    """
    # Constant?
    if all(v == 0 for v in tt):
        return "1'b0"
    if all(v == 1 for v in tt):
        return "1'b1"

    # Single-bit dependence: which bits does tt actually depend on?
    deps = []
    for bit_idx in range(4):
        # Does flipping `port[bit_idx]` ever change tt?
        flipped = False
        for code in range(16):
            other = code ^ (1 << bit_idx)
            if tt[code] != tt[other]:
                flipped = True
                break
        if flipped:
            deps.append(bit_idx)
    if len(deps) == 1:
        bit_idx = deps[0]
        # Is it tt(code) = port[bit_idx]?
        if tt[1 << bit_idx] == 1 and tt[0] == 0:
            return f"{port}[{bit_idx}]"
        else:
            return f"~{port}[{bit_idx}]"

    # 2-bit dependence: try XOR / XNOR / AND / OR / NAND / NOR patterns.
    if len(deps) == 2:
        b0, b1 = deps
        # Project tt to a 4-row table over (port[b1], port[b0])
        proj = []
        for v0 in range(2):
            for v1 in range(2):
                code = (v1 << b1) | (v0 << b0)
                proj.append(tt[code])
        # proj[0] = tt with both 0, proj[1] = port[b0]=1, proj[2] = port[b1]=1, proj[3] = both 1
        patterns = {
            (0, 0, 0, 1): f"({port}[{b0}] & {port}[{b1}])",
            (0, 1, 1, 1): f"({port}[{b0}] | {port}[{b1}])",
            (0, 1, 1, 0): f"({port}[{b0}] ^ {port}[{b1}])",
            (1, 0, 0, 1): f"~({port}[{b0}] ^ {port}[{b1}])",
            (1, 1, 1, 0): f"~({port}[{b0}] & {port}[{b1}])",
            (1, 0, 0, 0): f"~({port}[{b0}] | {port}[{b1}])",
            # proj index: 0=v0=0,v1=0 ; 1=v0=0,v1=1 ; 2=v0=1,v1=0 ; 3=v0=1,v1=1
            #   (where v_i is the value of port[b_i])
            (0, 0, 1, 0): f"({port}[{b0}] & ~{port}[{b1}])",  # only v0=1,v1=0
            (0, 1, 0, 0): f"(~{port}[{b0}] & {port}[{b1}])",  # only v0=0,v1=1
            (1, 1, 0, 1): f"({port}[{b0}] | ~{port}[{b1}])",  # NOT(only v0=1,v1=0)
            (1, 0, 1, 1): f"(~{port}[{b0}] | {port}[{b1}])",  # NOT(only v0=0,v1=1)
        }
        key = tuple(proj)
        if key in patterns:
            return patterns[key]

    # General case: emit SOP-of-minterms. yosys's `opt` should simplify.
    cubes = []
    for code in range(16):
        if tt[code] == 1:
            bits = f"{code:04b}"
            cube_terms = []
            for k, b in enumerate(bits):
                wire = f"{port}[{3-k}]"
                cube_terms.append(wire if b == "1" else f"~{wire}")
            cubes.append("(" + " & ".join(cube_terms) + ")")
    return " | ".join(cubes)


def emit_struct_verilog_with_remap(values: list[float]) -> str:
    """Emit a full FP4 multiplier Verilog whose input bits decode according
    to `values`, and whose multiplier core uses the standard structural decomp."""
    dec_a = emit_decoder_verilog(values, "a")
    dec_b = emit_decoder_verilog(values, "b")
    return f"""
module fp4_mul (
    input  wire [3:0] a,
    input  wire [3:0] b,
    output wire [8:0] y
);
    // Per-remap decode: extract (sign, eh, el, m) in default-encoding form.
{dec_a}{dec_b}
    wire sa  = dec_a_s;
    wire eh_a = dec_a_eh;
    wire el_a = dec_a_el;
    wire ma  = dec_a_m;
    wire sb  = dec_b_s;
    wire eh_b = dec_b_eh;
    wire el_b = dec_b_el;
    wire mb  = dec_b_m;

    // ---- Standard structural multiplier (lifted from fp4_mul_struct.v) ----
    wire lb_a = eh_a | el_a;
    wire lb_b = eh_b | el_b;
    wire [1:0] Ma = {{lb_a, ma}};
    wire [1:0] Mb = {{lb_b, mb}};
    wire [3:0] P = Ma * Mb;

    wire [1:0] sa1 = {{eh_a & el_a, eh_a & ~el_a}};
    wire [1:0] sb1 = {{eh_b & el_b, eh_b & ~el_b}};
    wire [2:0] K = sa1 + sb1;

    wire [7:0] mag = P << K;
    wire sy = sa ^ sb;
    wire [8:0] mag9 = {{1'b0, mag}};
    wire [8:0] xord = mag9 ^ {{9{{sy}}}};
    wire [8:0] outv = xord + {{8'b0, sy}};
    assign y = outv;
endmodule
"""


def _self_test():
    # Default encoding: decoder should be identity.
    v = DEFAULT_FP4_VALUES
    fields = fields_for_values(v)
    for i, t in enumerate(fields):
        expected = ((i>>3)&1, (i>>2)&1, (i>>1)&1, i&1)
        assert t == expected, f"default decoder wrong at i={i}: {t} != {expected}"
    print("OK identity decoder for default encoding")

    # Sign-symmetric remap test: σ = (0,1,2,4,3,5,6,7) swaps 1.5 and 2.
    perm = (0, 1, 2, 4, 3, 5, 6, 7)
    v2 = encoding_from_magnitude_perm(perm)
    # Under this remap, code 011 (orig 1.5) should now decode to "the default
    # code for the new magnitude at index 3", which is MAGNITUDES[perm[3]] = MAGNITUDES[4] = 2.
    # The default code for value 2 is code 0100 = (sign=0, eh=1, el=0, m=0).
    fields = fields_for_values(v2)
    assert fields[0b0011] == (0, 1, 0, 0), f"got {fields[0b0011]}"
    print(f"OK sign-symmetric decoder for perm {perm}")


if __name__ == "__main__":
    _self_test()
