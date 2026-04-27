#!/bin/bash
# Clean sweep launcher with setsid + nohup so subprocess doesn't get killed
# when the parent terminates.
#
# Usage: bash run_sweep_clean.sh [parallelism] [grid_file] [ledger_path]
set -u
ROOT=/home/shadeform/fp4-multiplier
WORK=$ROOT/workspace/eslim_runs
JOBS=${1:-18}
GRID=${2:-$WORK/grid_round1.txt}
LEDGER=${3:-$WORK/sweep_ledger.tsv}
TODO=$WORK/todo_$(basename $GRID .txt).txt

# Build done set from ledger
done_ids=$WORK/.done_$(basename $GRID .txt).txt
tail -n +2 $LEDGER 2>/dev/null | awk -F'\t' '$15=="ok" {print $2}' > $done_ids
sort -u $done_ids -o $done_ids

# Filter grid
> $TODO
while IFS= read -r line; do
    rid=$(echo "$line" | cut -d'|' -f1)
    if ! grep -qx "$rid" $done_ids; then
        echo "$line" >> $TODO
    fi
done < $GRID

remaining=$(wc -l < $TODO)
echo "Total grid: $(wc -l < $GRID), already-done: $(wc -l < $done_ids), todo: $remaining"
echo "Running $JOBS in parallel."

# Use setsid + nohup. The bash script invocation is wrapped in setsid so it
# escapes the controlling terminal entirely.
LAUNCH_SCRIPT=$WORK/.launch_$$.sh
cat > $LAUNCH_SCRIPT <<EOF
#!/bin/bash
cat $TODO | xargs -P $JOBS -I {} bash -c '
    spec="\$1"
    rid=\$(echo "\$spec" | cut -d"|" -f1)
    start=\$(echo "\$spec" | cut -d"|" -f2)
    sz=\$(echo "\$spec" | cut -d"|" -f3)
    rs=\$(echo "\$spec" | cut -d"|" -f4)
    li=\$(echo "\$spec" | cut -d"|" -f5)
    sd=\$(echo "\$spec" | cut -d"|" -f6)
    bg=\$(echo "\$spec" | cut -d"|" -f7)
    if [ -z "\$rid" ]; then exit 0; fi
    /home/shadeform/.venv-fp4/bin/python3 $WORK/sweep_run.py $LEDGER "\$rid" "\$start" "\$sz" "\$rs" "\$li" "\$sd" "\$bg" 2>&1 | tail -20 > $WORK/outputs/\${rid}.runlog || echo "FAIL: \$rid"
' _ {}
echo "SWEEP COMPLETE"
EOF
chmod +x $LAUNCH_SCRIPT
setsid nohup bash $LAUNCH_SCRIPT > $WORK/sweep_$(basename $GRID .txt).log 2>&1 < /dev/null &
PID=$!
echo "Launched setsid PID=$PID, log at $WORK/sweep_$(basename $GRID .txt).log"
disown $PID 2>/dev/null || true
sleep 5
echo "Running reduce.py: $(pgrep -fc 'reduce.py')"
