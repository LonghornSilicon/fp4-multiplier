#!/bin/bash
# Master eSLIM sweep — run many (start, size, seed, restarts) combos in parallel.
# Karpathy-autoresearch style: TSV ledger, single scalar metric (gate count),
# frozen verifier, every experiment logged.

set -u
ROOT=/home/shadeform/fp4-multiplier
WORK=$ROOT/workspace/eslim_runs
LEDGER=$WORK/sweep_ledger.tsv
LOG_ROOT=$WORK/outputs

mkdir -p $LOG_ROOT
source /home/shadeform/.venv-fp4/bin/activate

# Build the experiment grid as lines of: run_id|start_blif|size|restarts|limit_inputs|seed|budget_s
gen_grid() {
    local round="$1"
    if [ "$round" = "round1" ]; then
        # Round 1: every start at size 8 and size 10 with default seed.
        # Goal: reach internal floor on each starting topology to find low-NOT solutions.
        local budget=900
        for f in $WORK/starts/*.blif; do
            name=$(basename "$f" .blif)
            for size in 8 10; do
                for seed in 1 42; do
                    echo "${round}_${name}_s${size}_seed${seed}|$f|${size}|0|none|${seed}|${budget}"
                done
            done
        done
    elif [ "$round" = "round2_focus" ]; then
        # Round 2: focus on best-of-round1 starts with longer budgets, restarts, limit-inputs
        # User must pass list of starts via env var FOCUS_STARTS (space-separated)
        local budget=2400
        for f in ${FOCUS_STARTS}; do
            name=$(basename "$f" .blif)
            for size in 6 8 10; do
                for restarts in 0 3; do
                    for limit in 4 5 none; do
                        echo "${round}_${name}_s${size}_r${restarts}_l${limit}|$f|${size}|${restarts}|${limit}|7777|${budget}"
                    done
                done
            done
        done
    fi
}

ROUND="${1:-round1}"
JOBS_PARALLEL="${2:-22}"

gen_grid "$ROUND" > $WORK/grid_${ROUND}.txt
total=$(wc -l < $WORK/grid_${ROUND}.txt)
echo "Round $ROUND: $total experiments queued, running $JOBS_PARALLEL in parallel."
echo "Ledger: $LEDGER"
echo "---"

# Use parallel via xargs -P
cat $WORK/grid_${ROUND}.txt | xargs -P $JOBS_PARALLEL -I {} bash -c '
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
    echo "DONE: $run_id" >&2
' _ {}

echo "---"
echo "Round $ROUND complete. Best results:"
sort -t$'\t' -k10n $LEDGER | head -10
