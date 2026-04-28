"""Per-cone re-synthesis with side inputs.

Idea: Take the canonical 64-gate netlist. For each output Y[k], identify
the gates that are PRIVATE to Y[k] (drive only Y[k], no other output).
Treat all SHARED gates as primary inputs and try to re-synthesize Y[k]
using Cirbo with the smallest number of new gates.

If Cirbo finds a smaller per-cone re-synthesis than the current private
count, we save gates by replacing.

This is fundamentally different from eSLIM's local-window rewriting:
eSLIM operates on small connected sub-circuits (max 12 gates). Per-cone
re-synth operates on the *full per-output cone* with all shared signals
as free inputs — captures non-local rewrites eSLIM cannot.

Usage: cirbo_cone_resynth.py <netlist.blif> <output_idx> [G_max] [time_budget]
"""
import sys, time
from collections import defaultdict
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO / "lib"))
from cirbo.core.truth_table import TruthTableModel
from cirbo.synthesis.circuit_search import CircuitFinderSat, Operation
from verify import parse_blif

OUR_BASIS = [Operation.and_, Operation.or_, Operation.xor_, Operation.lnot_]


def evaluate_gate(kind, ivals):
    if kind == 'NOT': return 1 - ivals[0]
    if kind == 'AND': return ivals[0] & ivals[1]
    if kind == 'OR':  return ivals[0] | ivals[1]
    if kind == 'XOR': return ivals[0] ^ ivals[1]
    if kind == 'BUF': return ivals[0]
    raise ValueError(kind)


def evaluate_netlist_at(parsed, input_assign, target_nets):
    """Evaluate the netlist for one input assignment, returning values
    for the named target nets."""
    vals = dict(input_assign)
    for net, lit in parsed["constant"].items():
        vals[net] = lit
    vals.setdefault("$false", 0)
    vals.setdefault("$true", 1)
    pending = list(parsed["gates"])
    while pending:
        progress = False
        new_pending = []
        for g in pending:
            net, kind, ins = g
            if any(x not in vals and x not in ("0", "1") for x in ins):
                new_pending.append(g)
                continue
            ivals = [int(x) if x in ("0", "1") else vals[x] for x in ins]
            vals[net] = evaluate_gate(kind, ivals)
            progress = True
        pending = new_pending
        if not progress:
            break
    return {n: vals.get(n) for n in target_nets if n in vals}


def cone(parsed, target):
    """Set of gate names that drive `target`."""
    fanin = {g[0]: g[2] for g in parsed["gates"]}
    visited = set()
    stack = [target]
    while stack:
        n = stack.pop()
        if n in visited or n not in fanin:
            continue
        visited.add(n)
        for s in fanin[n]:
            stack.append(s)
    # Filter to actual gate outputs (not PIs, not constants)
    gate_set = set(fanin.keys())
    return visited & gate_set


def main():
    blif = sys.argv[1]
    out_idx = int(sys.argv[2])
    G_max = int(sys.argv[3]) if len(sys.argv) > 3 else 30
    time_limit = int(sys.argv[4]) if len(sys.argv) > 4 else 600

    parsed = parse_blif(blif)
    inputs = parsed["inputs"]
    outputs = parsed["outputs"]
    gates = parsed["gates"]

    # Identify cones for each output
    output_cones = {op: cone(parsed, op) for op in outputs}
    target_op = f"y[{out_idx}]"
    if target_op not in output_cones:
        # Try alternative naming
        target_op = [o for o in outputs if f"y[{out_idx}]" in o or o == f"y{out_idx}"][0]
    print(f"Target: {target_op}", flush=True)

    # Private = gates only in this cone, not in any other cone
    target_cone = output_cones[target_op]
    other_cones = set()
    for op, c in output_cones.items():
        if op != target_op:
            other_cones |= c
    private = target_cone - other_cones
    shared = target_cone & other_cones
    print(f"Cone size: {len(target_cone)}, private: {len(private)}, shared: {len(shared)}",
          flush=True)
    print(f"Private gates: {sorted(private)}", flush=True)

    # The "side inputs" = PIs + ALL shared signals
    # We'll synthesize Y[k] using these as inputs.
    # First: build truth table for these side inputs over all 256 PI assignments.
    # The Cirbo input set = inputs (8 PIs) + shared signals (subset of internal nets)
    # whose values depend on PIs.

    # Collect all "free input" nets: PIs + shared gate outputs
    # Convert to a list, deterministic order
    pi_names = list(inputs)
    shared_names = sorted(shared)
    free_inputs = pi_names + shared_names
    n_free = len(free_inputs)
    print(f"# free inputs: {n_free} ({len(pi_names)} PIs + {len(shared_names)} shared signals)",
          flush=True)

    # We need: for each value of the 8 PIs (256 cases), compute Y[target_op]
    # AND the value of each shared signal at that PI assignment.
    # Then Cirbo synthesizes a function from `free_inputs` -> Y[target_op]
    # treating each free input as an independent variable.
    #
    # IMPORTANT: this gives a CONSERVATIVE lower bound. The true min uses
    # the joint constraint that shared signals are FUNCTIONS of PIs.
    # Cirbo treats each as independent (over 2^n_free cases), some of which
    # are unreachable. So Cirbo's minimum is an UPPER bound on what we
    # could achieve if we modeled the constraint, but a valid candidate
    # for the actual netlist replacement.
    #
    # We use Cirbo's "don't care" mechanism by setting unreachable rows
    # to don't-cares (False, but allowing both 0/1).

    # For now, treat the free inputs as independent and use only the
    # 256 reachable rows. This means we only need the truth table over
    # 256 minterms (PI assignments), but the resulting function has
    # n_free input dimensions.

    # Strategy: enumerate 2^n_free input rows and mark only those
    # that match a reachable PI assignment.

    # That's 2^n_free which could be huge. So we use a different trick:
    # we directly synthesize over the (PI, shared) joint truth table by
    # treating shared signals as auxiliary inputs that match their actual
    # values for reachable PI assignments.

    # The simplest correct framing: Cirbo solves a function problem with
    # a CompleteTruthTableModel of dimension 256 (PI assignments). The
    # value of Y[target_op] at row i is known. The "free inputs" we hand
    # Cirbo are the (PIs, shared signal values) at each row. Cirbo finds
    # a circuit using this n_free-dimensional input.

    # But Cirbo's TruthTableModel takes a 2^n table. We'd need n_free
    # dimensions which is 2^n_free rows. Too large.

    # Alternative approach: PartiallySpecifiedFunction (don't cares for
    # unreachable rows).

    # For this MVP: just synthesize Y[target_op] using only PIs (8 inputs)
    # as a sanity check. We've already done this — it gives the per-bit
    # minimum. To use side inputs, we need a more elaborate setup.

    print(f"\n[Sanity] synthesizing Y[{out_idx}] from 8 PIs only (per-bit min):",
          flush=True)

    # Build per-bit truth table by simulating netlist
    truth_bits = []
    for pi_assign_idx in range(256):
        # Assignment: bit i corresponds to PI i (in inputs list order)
        assign = {}
        for i, pname in enumerate(pi_names):
            assign[pname] = (pi_assign_idx >> i) & 1
        result = evaluate_netlist_at(parsed, assign, [target_op])
        truth_bits.append(bool(result.get(target_op, 0)))

    table = [truth_bits]
    model = TruthTableModel(table)

    last_unsat = None
    for G in range(1, G_max + 1):
        finder = CircuitFinderSat(boolean_function_model=model,
                                  number_of_gates=G, basis=OUR_BASIS)
        t0 = time.time()
        try:
            circuit = finder.find_circuit(time_limit=time_limit)
            wall = time.time() - t0
            print(f"  G={G}: SAT  ({wall:.1f}s)  -> Y[{out_idx}] per-bit min = {G}",
                  flush=True)
            return
        except Exception as e:
            wall = time.time() - t0
            ename = type(e).__name__
            if "NoSolution" in ename:
                last_unsat = G
                print(f"  G={G}: UNSAT ({wall:.1f}s)", flush=True)
            elif "TimeOut" in ename or "Timeout" in ename:
                print(f"  G={G}: TIMEOUT ({wall:.1f}s)  -> >= {(last_unsat or 0) + 1}",
                      flush=True)
                return
            else:
                print(f"  G={G}: ERROR {ename}: {e}", flush=True)
                return


if __name__ == "__main__":
    main()
