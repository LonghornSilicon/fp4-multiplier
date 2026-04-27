# Campaign Workspace (gitignored artifacts)

Self-contained workspace for the 28-vCPU/56GB VPS campaign launched 2026-04-27.
Holds the toolchain glue, parallel sweep drivers, and per-experiment artifacts.

## Layout

```
workspace/
├── eslim_runs/               # eSLIM SAT-based local-improvement campaign
│   ├── starts/               # 35+ diverse starting BLIFs (mut11/2/26/27/30..34 across ABC seeds + canonicals)
│   ├── outputs/              # gitignored — per-experiment intermediate BLIFs and logs
│   ├── sweep_ledger.tsv      # frozen Karpathy-autoresearch experiment ledger (kept in git)
│   ├── sweep_run.py          # one-experiment runner (frozen verifier, dual translator)
│   ├── run_sweep_clean.sh    # parallel orchestrator with setsid (resilient to terminal exit)
│   ├── parallel_synth.sh     # parallel start-netlist generator
│   ├── make_starts.sh        # legacy sequential generator
│   ├── verify_starts.py      # sanity check: every start passes the frozen verifier
│   ├── grid_round1.txt       # 140 round-1 specs (35 starts × 2 sizes × 2 seeds)
│   ├── round2_launch.sh      # round-2 launcher (focuses on best round-1 starts)
│   ├── aggressive_s12.sh     # size-12/14 with --restarts on the most-promising starts
│   ├── iterative_refeed.sh   # multi-iteration eSLIM refeed (eSLIM internal -> eSLIM)
│   └── synth_one.sh          # single-mutation yosys+ABC synth
└── cirbo_runs/               # Cirbo SAT lower-bound campaign
    ├── cirbo_perbit.py       # per-output-bit walk-up search
    ├── cirbo_portfolio.py    # multi-solver portfolio for full-circuit (memory-heavy; not used)
    ├── cirbo_dimacs.py       # CNF dump for direct kissat (memory-heavy; not used)
    └── perbit_ledger.tsv     # per-bit search ledger (kept in git)
```

## Running

Round 1 of the eSLIM sweep (auto-resumes from the ledger):
```bash
bash workspace/eslim_runs/run_sweep_clean.sh 18 \
    workspace/eslim_runs/grid_round1.txt \
    workspace/eslim_runs/sweep_ledger.tsv
```

Cirbo per-output-bit campaign (one process per Y[k]):
```bash
cd workspace/cirbo_runs
for k in 1 2 3 4 5 6 7 8; do
    nohup python3 cirbo_perbit.py $k 25 1200 cadical195 > perbit_Y$k.log 2>&1 &
done
```

## Toolchain (must be installed on the box)

- yosys 0.51+ (OSS CAD Suite 2025-04-01) at `/home/shadeform/oss-cad-suite/bin/`
- python venv at `/home/shadeform/.venv-fp4/` with cirbo 1.0.0, pysat, sympy, bitarray, pybind11
- eSLIM at `/home/shadeform/eslim/` with bindings built (see top-level MEMORY.md for build steps)
- Optional: kissat 4.0.4 at `/home/shadeform/kissat/` for CNF-direct SAT solving

## Frozen evaluation harness

All experiments verify their candidate netlist against `lib/verify.py` under
`sigma=(0,1,2,3,6,7,4,5)+sign`. A FAIL is a hard halt for that experiment;
the result is logged with `status=eslim_no_output|verify_fail|...` and the
experiment is discarded. Per Karpathy autoresearch, the verifier and the
spec (`lib/fp4_spec.py`) are FROZEN and must never be modified to make a
candidate "pass".

## Karpathy autoresearch discipline

The single scalar metric is **contest gate count**. The TSV ledger records
every experiment with full parameters so the campaign is reproducible.
Each experiment is fixed-budget (900s default for round 1; up to 7200s
for aggressive size-14 runs). On breakthrough we promote the new canonical
to `src/fp4_mul.blif` and re-tag in MEMORY.md.
