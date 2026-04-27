#!/bin/bash
# Round 2 launcher: focus on the most-promising starts from round 1 with
# expanded parameter grid (sizes 6-12, restarts, limit-inputs, more seeds).
#
# Picks "promising" as: starts whose round-1 best (low contest_cells)
# was either <= 70 or had <= 8 NOTs.

set -u
ROOT=/home/shadeform/fp4-multiplier
WORK=$ROOT/workspace/eslim_runs
LEDGER_R1=$WORK/sweep_ledger.tsv
LEDGER=$WORK/sweep_ledger_r2.tsv
GRID=$WORK/grid_round2.txt
OUT_ROOT=$WORK/outputs

mkdir -p $OUT_ROOT
source /home/shadeform/.venv-fp4/bin/activate

# Identify "promising" starts: any start whose round-1 best contest <= 70
# OR best NOT count <= 7.
echo "Scanning round-1 ledger for promising starts..."
PROMISING=$(tail -n +2 $LEDGER_R1 | awk -F'\t' '
    {
      # Group by start, track min contest and min not1
      if ($10 != "" && $10 != "contest") {
        c = $10 + 0
        n = $14 + 0
        if (!(start[$3])) start[$3] = c
        else if (c < start[$3]) start[$3] = c
        if (!(notmin[$3])) notmin[$3] = n
        else if (n < notmin[$3]) notmin[$3] = n
      }
    }
    END {
      for (s in start) {
        if (start[s] <= 70 || notmin[s] <= 7) {
          print s
        }
      }
    }' | sort -u)
echo "Promising starts:"
echo "$PROMISING"
echo "---"

# Generate experiment grid
true > $GRID
for s in $PROMISING; do
    for size in 6 8 10 12; do
        for restarts in 0 3; do
            for limit in none 4 5; do
                for seed in 1 42 7777 13371337; do
                    name="r2_${s%.blif}_z${size}_r${restarts}_l${limit}_se${seed}"
                    echo "${name}|$WORK/starts/${s}|${size}|${restarts}|${limit}|${seed}|2400" >> $GRID
                done
            done
        done
    done
done

total=$(wc -l < $GRID)
echo "Round 2: $total experiments queued."

# Cap at total $1 if specified
LIMIT="${1:-$total}"
head -$LIMIT $GRID > $GRID.head
mv $GRID.head $GRID
total=$(wc -l < $GRID)
echo "After cap to $LIMIT: $total experiments. Running 16 in parallel."

cat $GRID | xargs -P 16 -I {} bash -c '
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
        2>&1 | tail -20 > /home/shadeform/fp4-multiplier/workspace/eslim_runs/outputs/${run_id}.runlog || echo "JOB FAILED: $run_id"
' _ {}

echo
echo "=== Round 2 best results ==="
sort -t$'\t' -k10n $LEDGER | head -10
