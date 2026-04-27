#!/bin/bash
# Iterative eSLIM refeed: take eSLIM's internal output (.names form) and run
# eSLIM AGAIN on it. The previous session noted this saturates at internal=58
# but didn't try with size 12 or restarts.
#
# Args: <input_eslim_blif> <num_iters> <size> <restarts> <budget_per_iter>
set -u
in_blif="$1"
iters="${2:-5}"
size="${3:-10}"
restarts="${4:-3}"
budget="${5:-1500}"

ROOT=/home/shadeform/fp4-multiplier
WORK=$ROOT/workspace/eslim_runs
source /home/shadeform/.venv-fp4/bin/activate
export PYTHONPATH=/home/shadeform/eslim/src/bindings/build

cur="$in_blif"
out_dir="$WORK/outputs/refeed_$(basename ${in_blif%.blif})"
mkdir -p "$out_dir"

for i in $(seq 1 $iters); do
    out="$out_dir/iter${i}.blif"
    cmd="python3 /home/shadeform/eslim/src/reduce.py $cur $out $budget --syn-mode sat --size $size"
    [ "$restarts" != "0" ] && cmd="$cmd --restarts $restarts"
    [ -n "${seed:-}" ] && cmd="$cmd --seed $((i * 1000 + 7))"
    echo "Iteration $i: $cmd"
    $cmd 2>&1 | tail -5
    if [ ! -f "$out" ]; then
        echo "iter$i no output, stopping"
        break
    fi
    g=$(grep "Final #gates" $out_dir/iter${i}.log 2>/dev/null | grep -oE "[0-9]+" | tail -1)
    [ -z "$g" ] && g="?"
    echo "  -> internal=$g"
    cur="$out"
done

echo "Final iteration result: $cur"
# Translate final to contest cells via both translators, pick best
python3 $ROOT/experiments_external/eslim/scripts/eslim_to_gates.py "$cur" "$out_dir/final_legacy.blif" 2>&1 | tail -2
python3 $ROOT/lib/eslim_translator2.py "$cur" "$out_dir/final_v2.blif" 2>&1 | tail -2

# Verify each
for f in "$out_dir/final_legacy.blif" "$out_dir/final_v2.blif"; do
    if [ -f "$f" ]; then
        cnt=$(grep -cE '^\.gate (NOT1|AND2|OR2|XOR2)' "$f")
        ok=$(python3 -c "
import sys; sys.path.insert(0,'$ROOT/lib')
from verify import verify_blif
from remap import encoding_from_magnitude_perm
v=encoding_from_magnitude_perm((0,1,2,3,6,7,4,5))
ok,_ = verify_blif('$f', values=v)
print('OK' if ok else 'FAIL')
")
        echo "  $(basename $f): $cnt cells, verify=$ok"
    fi
done
