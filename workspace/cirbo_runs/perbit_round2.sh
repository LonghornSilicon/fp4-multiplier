#!/bin/bash
# Round 2 per-bit: longer budgets + try lingeling and glucose42 in addition
# to cadical195. Each Y[k] gets 3 different solvers running in parallel.
# Whichever decides first (SAT or UNSAT) wins.

set -u
WORK=/home/shadeform/fp4-multiplier/workspace/cirbo_runs
PY=/home/shadeform/.venv-fp4/bin/python3
G=7
BUDGET=14400  # 4 hours per attempt
mkdir -p $WORK/perbit_r2

# For each Y[k] (k=1..7), launch one job per solver
SOLVERS=(cadical195 lingeling glucose42)
for k in 1 2 3 4 5 6 7; do
    for s in "${SOLVERS[@]}"; do
        out=$WORK/perbit_r2/Y${k}_${s}.log
        nohup $PY $WORK/cirbo_perbit.py $k $G $BUDGET $s "0,1,2,3,6,7,4,5" \
            $WORK/perbit_r2/ledger.tsv > $out 2>&1 &
    done
done
sleep 3
echo "Launched: $(ps -ef | grep cirbo_perbit | grep -v grep | wc -l) workers"
free -g | head -2
