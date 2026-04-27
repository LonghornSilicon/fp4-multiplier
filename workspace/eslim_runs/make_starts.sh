#!/bin/bash
# Generate diverse starting netlists by varying ABC's &deepsyn seed.
# Output: starts/start_{name}.blif

set -e
export PATH=/home/shadeform/oss-cad-suite/bin:$PATH
ROOT=/home/shadeform/fp4-multiplier
WORK=$ROOT/workspace/eslim_runs
mkdir -p $WORK/starts

# We'll synthesize from mut11.v (the canonical Verilog). For each ABC seed
# we'll run a full deepsyn pipeline and capture the BLIF.
synth_seed() {
    local seed="$1"
    local out="$WORK/starts/seed${seed}.blif"
    local tmpdir=$(mktemp -d)
    cp $ROOT/mutations/fp4_mul_mut11.v $tmpdir/fp4_mul.v
    cp $ROOT/lib/contest.lib $tmpdir/
    cat > $tmpdir/synth.ys <<EOF
read_verilog $tmpdir/fp4_mul.v
hierarchy -top fp4_mul
proc; opt; flatten; opt -full; techmap; opt
abc -liberty $tmpdir/contest.lib -script "+strash; ifraig; scorr; dc2; strash; balance; rewrite; refactor; balance; rewrite; rewrite -z; balance; refactor -z; rewrite -z; balance; &get -n; &deepsyn -T 10 -I 8 -S $seed; &put; logic; mfs2; strash; dch -f; map -a -B 0"
write_blif $out
stat -liberty $tmpdir/contest.lib
EOF
    yosys $tmpdir/synth.ys 2>&1 | grep -E "Chip area" | head -1
    rm -rf $tmpdir
}

# Generate 10 different seeds (ABC's &deepsyn is non-deterministic w.r.t. seed)
for s in 1 2 3 5 7 11 13 17 23 31 42 99; do
    echo "Seed $s:"
    synth_seed "$s"
done

# Also synthesize from each top mutation we have
for mut in mut11 mut2 mut26 mut27; do
    for s in 1 7 42; do
        local_out=$WORK/starts/${mut}_s${s}.blif
        tmpdir=$(mktemp -d)
        cp $ROOT/mutations/fp4_mul_${mut}.v $tmpdir/fp4_mul.v
        cp $ROOT/lib/contest.lib $tmpdir/
        cat > $tmpdir/synth.ys <<EOF
read_verilog $tmpdir/fp4_mul.v
hierarchy -top fp4_mul
proc; opt; flatten; opt -full; techmap; opt
abc -liberty $tmpdir/contest.lib -script "+strash; ifraig; scorr; dc2; strash; balance; rewrite; refactor; balance; rewrite; rewrite -z; balance; refactor -z; rewrite -z; balance; &get -n; &deepsyn -T 10 -I 8 -S $s; &put; logic; mfs2; strash; dch -f; map -a -B 0"
write_blif $local_out
stat -liberty $tmpdir/contest.lib
EOF
        yosys $tmpdir/synth.ys 2>&1 | grep -E "Chip area" | head -1 || echo "fail"
        rm -rf $tmpdir
    done
done

# Also include the existing canonicals as starting points
cp $ROOT/src/fp4_mul.blif $WORK/starts/canonical_65.blif
cp $ROOT/experiments_external/eslim/fp4_mul_70gate.blif $WORK/starts/canonical_70.blif
cp $ROOT/experiments_external/abc-deepsyn-74gate/fp4_mul.blif $WORK/starts/canonical_74.blif

echo "All starts:"
ls -la $WORK/starts/
