"""Generate the round-2 experiment grid:
  - 12 variant BLIFs + canonical_65 + canonical_70 = 14 starts (all "best basin" candidates)
  - sizes {6, 8, 10, 12, 14}
  - restarts {0, 5}
  - limit-inputs {none, 4}
  - seeds {1, 42, 7777, 42424242}

Outputs to grid_round2.txt one spec per line.
"""
from pathlib import Path

WORK = Path("/home/shadeform/fp4-multiplier/workspace/eslim_runs")

starts = [
    "canonical_65.blif",
    "canonical_65_pushed.blif",
    "canonical_70.blif",
    "fp4_mul_v1_pushA_not_77.blif",
    "fp4_mul_v2_assocA_w_26.blif",
    "fp4_mul_v2_assocA_w_75.blif",
    "fp4_mul_v2_assocB_w_72.blif",
    "canonical_70_v1_pushA_not_46.blif",
    "canonical_70_v1_pushB_not_46.blif",
    "canonical_70_v1_pushB_not_73.blif",
    "canonical_70_v2_assocA_w_16.blif",
    "canonical_70_v2_assocB_w_10.blif",
    "canonical_70_v2_assocB_w_34.blif",
    "canonical_70_v2_assocB_y[3].blif",
]

# Phase A: comprehensive baseline on all variants (size 8/10 only)
phase_a = []
for s in starts:
    name = s.replace(".blif", "").replace("[", "").replace("]", "")
    for size in (8, 10):
        for seed in (1, 42, 7777):
            phase_a.append(f"r2A_{name}_z{size}_se{seed}|{WORK}/starts/{s}|{size}|0|none|{seed}|1500")

# Phase B: extreme params on canonical_65 only (the only path to 65 so far)
phase_b = []
canonical = f"{WORK}/starts/canonical_65.blif"
for size in (12, 14):
    for restarts in (0, 5):
        for seed in (1, 42, 7777, 42424242):
            phase_b.append(f"r2B_canonical_65_z{size}_r{restarts}_se{seed}|{canonical}|{size}|{restarts}|none|{seed}|3600")

# Phase C: extreme params on canonical_70 (best non-65 starting point)
phase_c = []
canonical70 = f"{WORK}/starts/canonical_70.blif"
for size in (12, 14):
    for restarts in (0, 5):
        for seed in (1, 42, 7777, 42424242):
            phase_c.append(f"r2C_canonical_70_z{size}_r{restarts}_se{seed}|{canonical70}|{size}|{restarts}|none|{seed}|3600")

all_specs = phase_a + phase_b + phase_c
print(f"Phase A (variants baseline): {len(phase_a)} experiments")
print(f"Phase B (canonical_65 extreme): {len(phase_b)} experiments")
print(f"Phase C (canonical_70 extreme): {len(phase_c)} experiments")
print(f"Total: {len(all_specs)} experiments")

with open(WORK / "grid_round2.txt", "w") as f:
    for s in all_specs:
        f.write(s + "\n")
print(f"Wrote {WORK}/grid_round2.txt")
