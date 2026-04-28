"""
Run the current best multiplier and log results.
Usage: python autoresearch/run.py [--approach "description"]
"""
import sys
import os
import json
import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from eval_circuit import evaluate_fast

LOG_FILE = os.path.join(os.path.dirname(__file__), "log.jsonl")
MULTIPLIER_FILE = os.path.join(os.path.dirname(__file__), "multiplier.py")


def run_multiplier(module_path=None, approach="unknown", notes=""):
    if module_path is None:
        module_path = MULTIPLIER_FILE

    import importlib.util
    spec = importlib.util.spec_from_file_location("multiplier_mod", module_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    fn = mod.write_your_multiplier_here
    remap = getattr(mod, 'INPUT_REMAP', None)

    correct, gate_count, errors = evaluate_fast(fn, remap, verbose=False)

    result = {
        "timestamp": datetime.datetime.now().isoformat(),
        "approach": approach,
        "correct": correct,
        "gate_count": gate_count if correct else None,
        "num_errors": len(errors),
        "notes": notes,
        "file": os.path.basename(module_path),
    }

    status = "CORRECT" if correct else f"WRONG ({len(errors)} errors)"
    print(f"[{approach}] {status} | {gate_count} gates")

    # Append to log
    with open(LOG_FILE, 'a') as f:
        f.write(json.dumps(result) + '\n')

    return result


def read_log():
    if not os.path.exists(LOG_FILE):
        return []
    results = []
    with open(LOG_FILE) as f:
        for line in f:
            line = line.strip()
            if line:
                results.append(json.loads(line))
    return results


def best_so_far():
    results = [r for r in read_log() if r.get('correct') and r.get('gate_count') is not None]
    if not results:
        return None
    return min(results, key=lambda r: r['gate_count'])


if __name__ == "__main__":
    approach = sys.argv[1] if len(sys.argv) > 1 else "baseline"
    module = sys.argv[2] if len(sys.argv) > 2 else None

    result = run_multiplier(module, approach=approach)

    best = best_so_far()
    if best and result['correct']:
        if result['gate_count'] <= best['gate_count']:
            print(f"NEW BEST: {result['gate_count']} gates (was {best['gate_count']})")
        else:
            print(f"Current best: {best['gate_count']} gates ({best['approach']})")

    print("\nAll results so far:")
    for r in sorted(read_log(), key=lambda x: x.get('gate_count') or 9999):
        gc = r.get('gate_count', 'N/A')
        print(f"  {gc:4} gates | {r['approach']:30s} | {'OK' if r['correct'] else 'WRONG'}")
