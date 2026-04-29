#!/bin/bash
# Watches /tmp/sat_k62.log; if K=62 returns SAT (a 62-gate witness exists),
# automatically launches a K=61 SAT follow-up to push deeper. If K=62 returns
# UNSAT or the wrapper exits non-zero, exits silently — UNSAT at K=62 implies
# UNSAT at K<62 trivially.
#
# Run with: nohup bash analysis/sat_k61_autolaunch.sh >/dev/null 2>&1 &

set -u
LOG=/tmp/sat_k62.log
K61_LOG=/tmp/sat_k61.log
TRIGGER=/tmp/k61_autolaunch.log
REPO=/home/ubuntu/fp4-multiplier-minimization

echo "$(date -u +%FT%TZ) k61 auto-launcher started, watching $LOG (PID=$$)" \
  > "$TRIGGER"

while true; do
  if [ ! -f "$LOG" ]; then sleep 60; continue; fi

  # Only fire after the K=62 wrapper has actually exited (its memory has been
  # released); otherwise launching K=61 in parallel would OOM-kill K=62.
  if ! grep -q "^EXIT=" "$LOG"; then
    sleep 60; continue
  fi

  if grep -q "Result: SAT" "$LOG"; then
    echo "$(date -u +%FT%TZ) K=62 returned SAT — launching K=61 follow-up" \
      >> "$TRIGGER"
    cd "$REPO" || { echo "$(date -u +%FT%TZ) cd failed" >> "$TRIGGER"; exit 1; }
    nohup bash -c \
      "timeout 86400 python3 -u analysis/sat_exact.py --K 61 --time-budget 86400 > $K61_LOG 2>&1; echo \"EXIT=\$?\" >> $K61_LOG" \
      >/dev/null 2>&1 &
    echo "$(date -u +%FT%TZ) K=61 launched, child PID=$!" >> "$TRIGGER"
  else
    echo "$(date -u +%FT%TZ) K=62 finished without SAT — no follow-up needed" \
      >> "$TRIGGER"
  fi
  exit 0
done
