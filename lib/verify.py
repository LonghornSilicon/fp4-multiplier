"""Functional verification: simulate a BLIF netlist (the synthesis output) on
all 256 input pairs and compare to the reference truth table.

This is the FROZEN evaluation harness for the autoresearch loop. Do not modify
to make a candidate "pass" — fix the candidate.
"""
from __future__ import annotations
import re
from pathlib import Path

from fp4_spec import DEFAULT_FP4_VALUES, qi9_encode


def parse_blif(path: str | Path) -> dict:
    """Parse a tiny subset of BLIF (just enough for ABC's `write_blif`).

    Returns a dict:
      inputs: list of input net names (in order)
      outputs: list of output net names (in order)
      gates: list of (out_net, gate_type, [in_nets]) tuples
    Gate types we recognize: AND2, OR2, XOR2, NOT1.
    Constant nets ($false, $true) are recognized; constant inputs to gates are
    represented by literal "0" or "1" in the wire list.
    """
    txt = Path(path).read_text()
    inputs: list[str] = []
    outputs: list[str] = []
    gates: list[tuple] = []
    constant: dict[str, int] = {}

    lines = [ln.strip() for ln in txt.splitlines()]
    i = 0
    while i < len(lines):
        ln = lines[i]
        if not ln or ln.startswith("#"):
            i += 1
            continue
        if ln.startswith(".inputs"):
            buf = ln[len(".inputs"):].strip()
            while buf.endswith("\\"):
                buf = buf[:-1].rstrip() + " " + lines[i + 1].strip()
                i += 1
            inputs = buf.split()
        elif ln.startswith(".outputs"):
            buf = ln[len(".outputs"):].strip()
            while buf.endswith("\\"):
                buf = buf[:-1].rstrip() + " " + lines[i + 1].strip()
                i += 1
            outputs = buf.split()
        elif ln.startswith(".gate") or ln.startswith(".subckt"):
            # Format: .gate <type> A=net B=net Y=net
            # (yosys writes `.subckt`, ABC writes `.gate`; same syntax.)
            tokens = ln.split()
            gtype = tokens[1]
            pin = {}
            for tok in tokens[2:]:
                k, v = tok.split("=")
                pin[k] = v
            if gtype == "NOT1":
                gates.append((pin["Y"], "NOT", [pin["A"]]))
            elif gtype == "AND2":
                gates.append((pin["Y"], "AND", [pin["A"], pin["B"]]))
            elif gtype == "OR2":
                gates.append((pin["Y"], "OR", [pin["A"], pin["B"]]))
            elif gtype == "XOR2":
                gates.append((pin["Y"], "XOR", [pin["A"], pin["B"]]))
            else:
                raise ValueError(f"Unknown gate type {gtype}")
        elif ln.startswith(".names"):
            # Constant or single-input identity. Format examples ABC emits:
            #   .names $false
            #   .names $true
            #   1
            tokens = ln.split()
            net = tokens[-1]
            # Inspect following lines until next '.' line for cubes
            cubes = []
            j = i + 1
            while j < len(lines) and not lines[j].startswith("."):
                if lines[j] and not lines[j].startswith("#"):
                    cubes.append(lines[j])
                j += 1
            if not cubes:
                constant[net] = 0  # .names with no cubes -> always 0
            elif cubes == ["1"]:
                constant[net] = 1
            else:
                # Could be a single-input pass-through; not expected from ABC
                # in our flow, but handle defensively.
                if len(tokens) == 3 and cubes == ["1 1"]:
                    gates.append((net, "BUF", [tokens[1]]))
                elif len(tokens) == 3 and cubes == ["0 1"]:
                    gates.append((net, "NOT", [tokens[1]]))
                else:
                    raise ValueError(f"Unsupported .names cubes: {tokens} {cubes}")
            i = j - 1
        elif ln.startswith(".end") or ln.startswith(".model"):
            pass
        i += 1

    return {
        "inputs": inputs,
        "outputs": outputs,
        "gates": gates,
        "constant": constant,
    }


def evaluate(parsed: dict, input_assign: dict[str, int],
             targets: list[str] | None = None) -> dict[str, int]:
    """Evaluate the netlist for one input assignment.

    Evaluates eagerly: each round, evaluate every gate whose inputs are all
    available. Stop when all `targets` are known, OR when no more progress
    can be made. Yosys-emitted BLIF often contains dead BUF chains for
    auto-generated wires that are never connected to outputs; we tolerate
    those by stopping early once we have the targets.
    """
    vals: dict[str, int] = dict(input_assign)
    for net, lit in parsed["constant"].items():
        vals[net] = lit
    vals.setdefault("$false", 0)
    vals.setdefault("$true", 1)

    pending = list(parsed["gates"])
    targets_set = set(targets) if targets is not None else None

    while pending:
        progressed = False
        new_pending = []
        for g in pending:
            net, gtype, ins = g
            if any(x not in vals and x not in ("0", "1") for x in ins):
                new_pending.append(g)
                continue
            ivals = [int(x) if x in ("0", "1") else vals[x] for x in ins]
            if gtype == "NOT":
                v = 1 - ivals[0]
            elif gtype == "AND":
                v = ivals[0] & ivals[1]
            elif gtype == "OR":
                v = ivals[0] | ivals[1]
            elif gtype == "XOR":
                v = ivals[0] ^ ivals[1]
            elif gtype == "BUF":
                v = ivals[0]
            else:
                raise ValueError(f"Unknown gate {gtype}")
            vals[net] = v
            progressed = True
        pending = new_pending
        # Early exit: if we have all targets, we don't care about dead logic.
        if targets_set is not None and targets_set.issubset(vals.keys()):
            return vals
        if not progressed:
            # No progress and targets still missing -> genuine failure.
            if targets_set is not None and targets_set.issubset(vals.keys()):
                return vals
            missing = (targets_set - set(vals.keys())) if targets_set else None
            raise RuntimeError(
                f"Evaluation stuck; pending={len(pending)} target_missing={missing}")
    return vals


def _name_to_index(names: list[str], abkind: str) -> list[int]:
    """Given the .inputs or .outputs list, return a list `idx` such that
    `idx[bit_position]` is the position in `names` of that bit. Handles two
    naming conventions:
       (1) ABC PLA-style: `a3 a2 a1 a0 b3 b2 b1 b0`, `y8 y7 ... y0`
       (2) yosys Verilog-style: `a[0] a[1] a[2] a[3] b[0] b[1] b[2] b[3]`,
           `y[0] ... y[8]`
    Returns a list of length 8 (inputs) or 9 (outputs). For inputs, ordering
    is (a3,a2,a1,a0,b3,b2,b1,b0). For outputs, ordering is (y8 … y0).
    """
    if abkind == "in":
        wanted = ["a3", "a2", "a1", "a0", "b3", "b2", "b1", "b0"]
    else:
        wanted = [f"y{k}" for k in range(8, -1, -1)]
    out = []
    for w in wanted:
        # Try exact match first.
        if w in names:
            out.append(names.index(w))
            continue
        # Bracket form: a[N] / y[N].
        var, idx = w[0], w[1:]
        bracketed = f"{var}[{idx}]"
        if bracketed in names:
            out.append(names.index(bracketed))
            continue
        raise KeyError(f"Cannot locate {w} (or {bracketed}) in {names}")
    return out


def verify_blif(blif_path: str | Path,
                values: list[float] = DEFAULT_FP4_VALUES) -> tuple[bool, list[tuple]]:
    """Return (ok, mismatches). `values` is the encoding used to generate the
    truth-table reference, so we can re-derive the expected output.
    """
    parsed = parse_blif(blif_path)
    inputs = parsed["inputs"]
    outputs = parsed["outputs"]
    in_idx = _name_to_index(inputs, "in")
    out_idx = _name_to_index(outputs, "out")

    target_outputs = [outputs[i] for i in out_idx]
    mismatches = []
    for a in range(16):
        for b in range(16):
            assign = {}
            bits = f"{a:04b}{b:04b}"  # a[3], a[2], a[1], a[0], b[3], …
            for k, bit in enumerate(bits):
                assign[inputs[in_idx[k]]] = int(bit)
            try:
                v = evaluate(parsed, assign, targets=target_outputs)
            except RuntimeError as e:
                mismatches.append(("eval-failed", a, b, str(e)))
                continue
            got = 0
            for k in range(9):
                # out_idx[0] is the position in `outputs` of y8; etc.
                bit_pos = 8 - k
                name = outputs[out_idx[k]]
                if name in v:
                    got |= (v[name] & 1) << bit_pos
            expected = qi9_encode(4.0 * values[a] * values[b])
            if got != expected:
                mismatches.append((a, b, got, expected))
    return len(mismatches) == 0, mismatches


if __name__ == "__main__":
    import sys
    if len(sys.argv) != 2:
        print(f"usage: {sys.argv[0]} <netlist.blif>")
        sys.exit(1)
    ok, mism = verify_blif(sys.argv[1])
    if ok:
        print("OK — netlist matches reference for all 256 input pairs.")
    else:
        print(f"FAIL — {len(mism)} mismatches; first few:")
        for m in mism[:5]:
            print("  ", m)
        sys.exit(2)
