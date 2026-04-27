#!/bin/bash
# Watch for round 1 completion (no active reduce.py + ledger >= 100).
# Once round 1 is done (or close to it), launch round 2 phase A.
set -u

WORK=/home/shadeform/fp4-multiplier/workspace/eslim_runs
LEDGER=$WORK/sweep_ledger.tsv
PHASE_A_GRID=$WORK/grid_round2_phaseA.txt

while true; do
    cur=$(wc -l < $LEDGER 2>/dev/null || echo 0)
    active=$(pgrep -fc "reduce.py")
    # Round 1 + variants_mini = ~155 entries
    if [ "$active" -le 2 ] && [ "$cur" -ge 100 ]; then
        echo "Round 1 (and variants_mini) effectively done: $cur entries, $active active reduce.py"
        echo "Launching round 2 phase A..."
        break
    fi
    sleep 90
done

# Launch round 2 phase A
bash $WORK/run_sweep_clean.sh 18 $PHASE_A_GRID $LEDGER
echo "Round 2 phase A launched."
