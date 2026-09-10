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
4. Currency maps: fixed USD and JPY basket median/breadth, strongest/weakest members and residual direction. Synchronization is strict inner join, with no fill. At each synchronized H1 timestamp, cross-sectional dispersion is the population standard deviation of oriented member returns. Its current value is ranked only against preceding 252 synchronized observations: low `<=20th`, normal `>20th and <80th`, high `>=80th`. These exact regimes condition strongest/weakest behavior, strongest-minus-weakest spread change, residual behavior and basket persistence; raw level, percentile and regime counts are retained.
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
- Dispersion has no additional buckets or post-output threshold changes.
- No forward labels, future session extrema, future pivots, or global sample statistics in event definitions.
- The tool is resumable by output file only after a complete run; partial outputs are not conclusions.
- Each pair and the cross-sectional block publish an atomic CSV plus a checksummed completion manifest. A restart skips only valid manifests; corrupted or partial files are rebuilt. Final CSVs are withheld until every expected unit is valid, then exact statistics are streamed one group at a time rather than retaining all event rows in RAM.

## Discovery nomination criteria — frozen before output

An observed effect may be nominated for a separate Round 3B hypothesis only when all applicable conditions hold: aggregate N >=300; same-sign effect in at least 4 of the 5 development years; same sign in at least 8 of 15 pairs for universe-wide effects; fixed-peer/cross-sectional effects in at least 2 of 3 peer groups; absolute mean >=0.05 ATR at a useful horizon; absolute t-statistic >=2.0; and a coherent neighboring-horizon profile rather than one isolated spike. These are discovery criteria, not a trading promotion gate. Any Round 3B rule must still pass untouched 2018–2020 validation under the existing frozen trading gate.

## Multiple-testing control — frozen before output

Every predeclared event, including null and adverse results, is reported. Definitions, buckets, horizons and sequence completion window are fixed before the first output; no event is added after results are viewed. Multiple horizons remain one mechanism, and Round 3B may select at most 5–8 distinct mechanisms.
