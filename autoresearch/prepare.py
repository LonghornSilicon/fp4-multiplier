"""
One-time preparation: build truth tables, find best remappings, dump to JSON.
Run once before starting the autoresearch loop.

Outputs:
  data/truth_table_default.json   - full 256-entry truth table (default encoding)
  data/best_remappings.json       - top 100 remappings by heuristic score
  data/magnitude_products.json    - all 64 (mag_a, mag_b) -> product entries
"""

import sys
import os
import json
import itertools

# Add parent dir to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fp4_core import (
    FP4_VALUES, MAGNITUDES, build_truth_table, tt_to_bit_functions,
    score_tt, search_all_remappings
)

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
os.makedirs(DATA_DIR, exist_ok=True)


def dump_truth_table(perm, filename):
    tt = build_truth_table(perm)
    # Convert keys to strings for JSON
    serializable = {f"{a},{b}": bits for (a, b), bits in tt.items()}
    with open(filename, 'w') as f:
        json.dump(serializable, f)
    print(f"Wrote {filename}")


def dump_magnitude_products(filename):
    """All |4 * mag_a * mag_b| for 8x8 magnitude pairs."""
    products = {}
    for i, ma in enumerate(MAGNITUDES):
        for j, mb in enumerate(MAGNITUDES):
            val = round(ma * mb * 4)
            products[f"{i},{j}"] = {
                "mag_a": ma, "mag_b": mb,
                "product_x4": val,
                "bits_8": [(val >> (7 - k)) & 1 for k in range(8)]
            }
    with open(filename, 'w') as f:
        json.dump(products, f, indent=2)
    print(f"Wrote {filename}")


def find_best_remappings(n=100):
    print("Searching all 8! = 40320 remappings (heuristic score)...")
    results = search_all_remappings(verbose=True)
    top = [{"score": s, "perm": list(p)} for s, p in results[:n]]
    filename = os.path.join(DATA_DIR, "best_remappings.json")
    with open(filename, 'w') as f:
        json.dump(top, f, indent=2)
    print(f"Wrote {filename}")
    print(f"Best heuristic score: {results[0][0]}, perm: {list(results[0][1])}")
    return results


def print_product_structure():
    """Print the K-type structure of all products."""
    print("\n=== Product structure (4 * mag_a * mag_b = K * 2^k) ===")
    for ma in MAGNITUDES:
        for mb in MAGNITUDES:
            v = round(ma * mb * 4)
            if v == 0:
                continue
            # Find K and k
            k = 0
            while v % 2 == 0:
                v //= 2
                k += 1
            K = v
            print(f"  {ma} × {mb} = {round(ma*mb*4)} = {K} × 2^{k}  (K∈{{1,3,9}})")


if __name__ == "__main__":
    print("=== FP4 Multiplier - Data Preparation ===\n")

    # Dump default truth table
    dump_truth_table(tuple(range(8)),
                     os.path.join(DATA_DIR, "truth_table_default.json"))

    # Dump magnitude products
    dump_magnitude_products(os.path.join(DATA_DIR, "magnitude_products.json"))

    # Print product structure
    print_product_structure()

    # Find best remappings
    results = find_best_remappings(n=100)

    # Also dump truth table for best remapping
    best_perm = results[0][1]
    dump_truth_table(best_perm,
                     os.path.join(DATA_DIR, "truth_table_best_remap.json"))
    with open(os.path.join(DATA_DIR, "best_perm.json"), 'w') as f:
        json.dump({"perm": list(best_perm), "score": results[0][0]}, f)

    print("\nPreparation complete.")
