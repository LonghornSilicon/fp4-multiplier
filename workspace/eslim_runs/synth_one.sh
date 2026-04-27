#!/bin/bash
# Synthesize one (mutation, seed) -> BLIF. Used in parallel.
# Args: <mutation_basename_no_ext> <seed> <output_path>
set -e
mut="$1"
seed="$2"
out="$3"
ROOT=/home/shadeform/fp4-multiplier
export PATH=/home/shadeform/oss-cad-suite/bin:$PATH

tmpdir=$(mktemp -d -p /tmp synth.XXXXXX)
trap "rm -rf $tmpdir" EXIT

if [ ! -f "$ROOT/mutations/${mut}.v" ]; then
    echo "MISSING: $mut" >&2; exit 1
fi
cp "$ROOT/mutations/${mut}.v" "$tmpdir/fp4_mul.v"
cp "$ROOT/lib/contest.lib" "$tmpdir/"
cat > "$tmpdir/synth.ys" <<EOF
read_verilog $tmpdir/fp4_mul.v
hierarchy -top fp4_mul
proc; opt; flatten; opt -full; techmap; opt
abc -liberty $tmpdir/contest.lib -script "+strash; ifraig; scorr; dc2; strash; balance; rewrite; refactor; balance; rewrite; rewrite -z; balance; refactor -z; rewrite -z; balance; &get -n; &deepsyn -T 10 -I 8 -S $seed; &put; logic; mfs2; strash; dch -f; map -a -B 0"
write_blif $out
stat -liberty $tmpdir/contest.lib
EOF
yosys "$tmpdir/synth.ys" >"$tmpdir/log" 2>&1
gates=$(grep "Chip area" "$tmpdir/log" | tail -1 | grep -oE "[0-9.]+" | head -1)
gates_int=${gates%.*}
echo "${mut}_s${seed} ${gates_int}"
