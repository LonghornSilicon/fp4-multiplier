#!/bin/bash
# Generate diverse starting netlists in parallel using GNU xargs -P.
ROOT=/home/shadeform/fp4-multiplier
WORK=$ROOT/workspace/eslim_runs
mkdir -p $WORK/starts

# Build a job list: (mutation, seed, output_path)
jobs=""
for s in 1 2 3 5 7 11 13 17 23 31 42 99 101 211 313 555; do
    jobs="$jobs mut11:${s}:$WORK/starts/mut11_s${s}.blif"
done
for mut in mut2 mut26 mut27 raw; do
    if [ "$mut" = "raw" ]; then mutfile="fp4_mul_raw"; else mutfile="fp4_mul_${mut}"; fi
    for s in 1 7 42 99; do
        jobs="$jobs ${mutfile#fp4_mul_}:${s}:$WORK/starts/${mut}_s${s}.blif"
    done
done

echo "Total jobs: $(echo $jobs | wc -w)"

# Run all in parallel via xargs (using up to 24 cores to leave headroom)
echo $jobs | tr ' ' '\n' | xargs -P 24 -I {} bash -c '
    spec="{}"
    mut=$(echo "$spec" | cut -d: -f1)
    seed=$(echo "$spec" | cut -d: -f2)
    out=$(echo "$spec" | cut -d: -f3)
    if [ -z "$out" ]; then exit 0; fi
    timeout 90 /home/shadeform/fp4-multiplier/workspace/eslim_runs/synth_one.sh "fp4_mul_${mut}" "$seed" "$out" 2>/dev/null || echo "fail: $spec"
'

# Also include the existing canonicals as starting points
cp $ROOT/src/fp4_mul.blif $WORK/starts/canonical_65.blif
cp $ROOT/experiments_external/eslim/fp4_mul_70gate.blif $WORK/starts/canonical_70.blif
cp $ROOT/experiments_external/abc-deepsyn-74gate/fp4_mul.blif $WORK/starts/canonical_74.blif

echo
echo "All starts done:"
ls -la $WORK/starts/
