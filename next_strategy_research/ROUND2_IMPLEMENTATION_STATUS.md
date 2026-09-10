# Strategy 2 — Round 2 implementation status

**Date:** 10 September 2026  
**Branch:** `strategy2-round2-wip`  
**Status:** FIDELITY-CORRECTED; FRESH INTERNAL SCREEN REQUIRED

## Completed

- Frozen deterministic implementation contract fidelity-corrected against the
  pre-data rules; see `ROUND2_FIDELITY_AUDIT.md`.
- S2R2-01 through S2R2-12 are implemented; S2R2-07/08/09 are no longer placeholders.
- Holdout guard remains hard-coded at `< 2021-01-01` in the reader.
- BID/ASK execution, 0.10-pip slippage, 1.25 ATR stop, 1.50R target, 24-M15 maximum hold, Friday 16:00 UTC close and stop-first ambiguity are preserved.
- Cross-pair USD/JPY basket state and correlation-dislocation state are built only from synchronized completed H1 bars with a one-hour availability lag.
- Grouped chronology hardening prevents the final M15 state from one UTC day/week from bleeding into the first row of the next day/week.
- Synthetic invariant suite added at `next_strategy_research/test_round2_engine.py`.

## Required before any heavy screen

Run from the repository root:

```bash
cd next_strategy_research
python test_round2_engine.py
```

Expected success line:

```text
PASS: 19 deterministic Round 2 tests
```

Do **not** start the full 15-pair Round 2 screen unless this passes. The earlier
screen is retained only as diagnostic runtime evidence and cannot be used for
promotion; it predates the fidelity corrections. GitHub Actions was attempted
but the repository workflow failed before any runner steps were allocated, so
it was removed rather than leaving a misleading red CI signal.

## After the fast test passes

Run the full internal screen only against the already-built Dukascopy M15/H1/D1 BID/ASK dataset. The runner itself excludes all rows from 2021 onward. Produce `results_next_strategy/round2/trades.csv`, `screen.csv`, checkpoint CSVs and `gate.json`. No holdout or HistData external validation is permitted until a hypothesis passes the frozen preliminary gate.
