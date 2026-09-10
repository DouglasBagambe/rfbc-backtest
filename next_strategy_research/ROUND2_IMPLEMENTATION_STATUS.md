# Strategy 2 — Round 2 implementation status

**Date:** 10 September 2026  
**Branch:** `strategy2-round2-wip`  
**Status:** REJECTED; implementation retained as archived evidence

## Completed

- Frozen deterministic implementation contract fidelity-corrected against the
  pre-data rules; see `ROUND2_FIDELITY_AUDIT.md`.
- S2R2-01 through S2R2-12 are implemented; S2R2-07/08/09 are no longer placeholders.
- Holdout guard remains hard-coded at `< 2021-01-01` in the reader.
- BID/ASK execution, 0.10-pip slippage, 1.25 ATR stop, 1.50R target, 24-M15 maximum hold, Friday 16:00 UTC close and stop-first ambiguity are preserved.
- Cross-pair USD/JPY basket state and correlation-dislocation state are built only from synchronized completed H1 bars with a one-hour availability lag.
- Grouped chronology hardening prevents the final M15 state from one UTC day/week from bleeding into the first row of the next day/week.
- Synthetic invariant suite added at `next_strategy_research/test_round2_engine.py`.

## Archived verification command

Run from the repository root:

```bash
cd next_strategy_research
python test_round2_engine.py
```

Expected success line:

```text
PASS: 19 deterministic Round 2 tests
```

Round 2 is closed. Do **not** rerun, retune, or promote it. The existing screen
output is preserved as rejected evidence in `results_next_strategy/round2/`;
the retained implementation and tests exist for reproducibility only.

## Historical screen outputs

The archived screen used the already-built Dukascopy M15/H1/D1 BID/ASK dataset
and excludes all rows from 2021 onward. It produced `trades.csv`, `screen.csv`,
checkpoint CSVs and `gate.json`. No holdout or HistData external validation was
performed.
