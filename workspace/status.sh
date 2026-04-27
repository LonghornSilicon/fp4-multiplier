#!/bin/bash
# Comprehensive campaign status reporter.
# Run: bash workspace/status.sh
set -u
WORK=/home/shadeform/fp4-multiplier/workspace
LEDGER=$WORK/eslim_runs/sweep_ledger.tsv

echo "=== FP4 Multiplier Campaign Status (2026-04-27) ==="
echo "Time: $(date)"
echo
echo "=== System ==="
free -g | head -2
uptime
echo
echo "=== Active campaign processes ==="
echo "  reduce.py (eSLIM workers):    $(pgrep -fc reduce.py)"
echo "  cirbo_perbit (per-bit):       $(pgrep -fc cirbo_perbit)"
echo "  cirbo_neg_block:              $(pgrep -fc cirbo_neg_block)"
echo "  perbit_single_g (perbit r2):  $(pgrep -fc perbit_single_g)"
echo "  total python procs:           $(pgrep -fc python3)"
echo
echo "=== eSLIM sweep ==="
echo "  Total ledger entries:    $(($(wc -l < $LEDGER 2>/dev/null) - 1))"
echo "  OK results:              $(tail -n +2 $LEDGER 2>/dev/null | awk -F'\t' '$15=="ok"' | wc -l)"
echo "  Best contest cells:      $(tail -n +2 $LEDGER 2>/dev/null | awk -F'\t' '$15=="ok" && $10!="" {print $10}' | sort -n | head -1)"
echo
echo "  Top 5 by contest:"
tail -n +2 $LEDGER 2>/dev/null | awk -F'\t' '$15=="ok" && $10!=""' | sort -t$'\t' -k10n | head -5 | awk -F'\t' '{printf "    %-50s contest=%s NOTs=%s internal=%s\n", $2, $10, $14, $9}'
echo
echo "=== Cirbo per-bit lower bounds ==="
echo "  Y[0]=4 (proven prior session)"
for k in 1 2 3 4 5 6 7; do
    last=$(tail -1 $WORK/cirbo_runs/perbit_Y${k}.log 2>/dev/null)
    last_r2=$(tail -3 $WORK/cirbo_runs/perbit_r2_Y${k}.log 2>/dev/null | grep -E "(SAT|UNSAT|TIMEOUT)" | tail -1)
    if [ -n "$last_r2" ]; then echo "  Y[$k]: ${last_r2}"; else echo "  Y[$k]: ${last}"; fi
done
last8=$(tail -1 $WORK/cirbo_runs/perbit_Y8.log 2>/dev/null)
echo "  Y[8]: $last8"
echo
echo "=== Cirbo conditional-negate sub-block ==="
tail -10 $WORK/cirbo_runs/neg_block.log 2>/dev/null | tail -6
echo
echo "=== Auto-launcher ==="
if pgrep -f auto_round2 > /dev/null; then
    echo "  ARMED: auto_round2_launcher waiting for round 1 completion"
else
    echo "  inactive (probably already fired)"
fi
echo
echo "=== Latest ledger entries ==="
tail -5 $LEDGER 2>/dev/null | awk -F'\t' '{printf "  %-50s int=%s contest=%s NOTs=%s status=%s\n", $2, $9, $10, $14, $15}'
