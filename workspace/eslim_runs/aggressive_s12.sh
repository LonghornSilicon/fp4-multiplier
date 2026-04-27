#!/bin/bash
# Aggressive size-12 / size-14 eSLIM with --restarts on the most-promising
# starts from round 1's preliminary results. The canonical 65 and 70 are
# the obvious targets — we want to push internal below 58 with a much larger
# window than what's been tried before.
#
# Each run gets 2 hours per size. Larger windows mean fewer queries per run
# but each query has access to bigger neighborhoods.

set -u
ROOT=/home/shadeform/fp4-multiplier
WORK=$ROOT/workspace/eslim_runs
LEDGER=$WORK/sweep_ledger_aggressive.tsv
mkdir -p $WORK/outputs
source /home/shadeform/.venv-fp4/bin/activate

PROMISING_STARTS=(
    canonical_65.blif
    canonical_70.blif
    mut11_s99.blif    # smallest mut11 starting point: 76 gates
    mut26_s99.blif    # 76 gates
)

# Generate experiment grid for aggressive runs
cat > $WORK/grid_aggressive.txt <<EOF
EOF
for s in "${PROMISING_STARTS[@]}"; do
    name=${s%.blif}
    for size in 12 14; do
        for restarts in 0 5; do
            for seed in 1 7 42 7777; do
                echo "agg_${name}_z${size}_r${restarts}_se${seed}|$WORK/starts/${s}|${size}|${restarts}|none|${seed}|7200" >> $WORK/grid_aggressive.txt
            done
        done
    done
done
total=$(wc -l < $WORK/grid_aggressive.txt)
echo "Aggressive size-12/14 grid: $total experiments, 2hr budget each. Running 4 in parallel."

cat $WORK/grid_aggressive.txt | xargs -P 4 -I {} bash -c '
    spec="$1"
    run_id=$(echo "$spec" | cut -d"|" -f1)
    start=$(echo "$spec" | cut -d"|" -f2)
    size=$(echo "$spec" | cut -d"|" -f3)
    restarts=$(echo "$spec" | cut -d"|" -f4)
    limit=$(echo "$spec" | cut -d"|" -f5)
    seed=$(echo "$spec" | cut -d"|" -f6)
    budget=$(echo "$spec" | cut -d"|" -f7)
    if [ -z "$run_id" ]; then exit 0; fi
    python3 /home/shadeform/fp4-multiplier/workspace/eslim_runs/sweep_run.py \
        '"$LEDGER"' "$run_id" "$start" "$size" "$restarts" "$limit" "$seed" "$budget" \
        2>&1 | tail -20 > /home/shadeform/fp4-multiplier/workspace/eslim_runs/outputs/${run_id}.runlog || echo "FAIL: $run_id"
' _ {}

echo "Aggressive run complete. Best:"
sort -t$'\t' -k10n $LEDGER | head -10
