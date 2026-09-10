# Strategy 2 — Round 3A empirical edge-map specification

**Status:** FROZEN FOR EXPLORATORY DEVELOPMENT ONLY
**Date:** 10 September 2026
**Scope:** Descriptive event study, not a strategy test. RFBC, Round 2, and the preregistered Round 3 strategy register are unchanged.

> **BOUNDARY:** The reader admits only `2013-01-01 <= dt < 2018-01-01`. It must reject 2018–2020 validation and 2021+ holdout rows before any indicator or event construction. No P&L, stop, target, order, parameter sweep, or pair-specific selection is permitted.

## Fixed data and statistical conventions

| Item | Definition |
|---|---|
| Universe | The fixed 15-pair Strategy 2 universe. BID M15 constructs events and BID H1 provides completed context; ASK is not used because no execution is simulated. |
| ATR | Wilder ATR/RMA(14). M15 and H1 percentile/regime values use only trailing completed observations, with a 252-bar trailing percentile rank excluding the current bar. |
| H1 | Completed H1 fields become available at source timestamp +1 hour, via backward as-of merge only. |
| Forward labels | BID close-to-close return from event `T` to T+{1,2,4,8,16} M15 bars, normalized by event M15 ATR. Labels never enter event predicates. |
| Statistics | Count, mean/median, sample standard error, t-statistic, positive-direction probability, 25/50/75 percentiles; pair and 2013–2017 breadth report effect-sign stability. |
| Sessions | Asia 00:00–06:45; London open 07:00–08:45; London body 09:00–12:45; NY open 13:00–14:45; overlap 13:00–15:45 UTC. |

## Predeclared event groups

1. Session state: session high/low sweep-reclaims, opening-range close breaks, and 1.5 ATR extreme session moves.
2. Volatility: M15/H1 trailing-ATR percentile regimes: compression `<=20`, normal `20–80`, expansion `>=80`; and forward signed/absolute behavior.
3. Shocks: completed M15/H1 close changes in ATR units: 0.5–1.0, 1.0–1.5, 1.5–2.0, >2.0, separated by sign; forward continuation/reversion is descriptive only.
4. Currency maps: fixed USD and JPY basket median/breadth, strongest/weakest members and residual direction. Synchronization is strict inner join, with no fill.
5. Fixed-pair divergence: EURUSD/GBPUSD, AUDUSD/NZDUSD and EURJPY/GBPJPY normalized-return spread and later convergence/persistence.
6. ICT primitives independently: FVG formation, four-bar MSS, Asia and prior-D1 sweep/reclaim, order-block candidate, breaker invalidation, OTE-zone occurrence, and fixed-pair SMT divergence.
7. Limited interactions only: session×volatility, shock×available H1 trend, sweep×MSS, FVG×H1 trend, divergence×session.

## Outputs

- `results_next_strategy/round3a/edge_map.csv`: aggregate event/horizon statistics.
- `results_next_strategy/round3a/by_pair.csv`: event/horizon/pair statistics.
- `results_next_strategy/round3a/by_year.csv`: event/horizon/year statistics.
- `results_next_strategy/round3a/event_counts.csv`: raw event frequencies before forward-label availability.
- `ROUND3A_EDGE_MAP_REPORT.md`: method, coverage, strongest stable descriptive effects and explicit non-strategy disclaimer.

## Required safeguards

- UTC-aware timestamps, completed-only features, and strict source ordering.
- H1 availability delayed one full hour.
- Missing synchronized members invalidate cross-pair timestamp.
- No forward labels, future session extrema, future pivots, or global sample statistics in event definitions.
- The tool is resumable by output file only after a complete run; partial outputs are not conclusions.
