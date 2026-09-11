# Round 3C Validation Gate

**Status:** FROZEN BEFORE 2018--2020 RESULTS

## Scope

Round 3C is one validation run of the five Round 3B hypotheses on the fixed 15-pair universe (and the three fixed H5 peer groups), with signals from `2018-01-01T00:00:00Z` through `2020-12-31T23:45:00Z` only. A short December 2017 input warm-up is allowed solely to initialize indicators and prior-session state; it creates no signal, trade, metric, or selection input. The reader excludes `2021-01-01T00:00:00Z` and later before feature construction.

## Frozen execution controls

- Enter at the next valid M15 open after the completed event bar.
- Stop: 1.0 event-bar M15 ATR. Target: 1.0 event-bar M15 ATR. Max holding: 16 M15 bars.
- Resolve a same-bar stop/target conflict stop-first.
- Charge 0.10 R per single-pair round trip and 0.20 R per H5 two-leg round trip.
- One active position per pair/hypothesis; re-entry requires a fully false M15 bar before the same branch can fire again. H5 signals are discrete hourly observations, so each non-signal M15 interval re-arms its peer group.
- No entry from Friday 16:00 UTC; force-close at Friday 20:45 UTC; no weekend carry.
- Exclude missing-next-open, non-finite/non-positive ATR, zero-volume, and market-closed observations.

## Promotion gate

A hypothesis is `SURVIVED` only if **all** conditions below hold. Otherwise it is `REJECTED`; no parameter, filter, branch, instrument, or execution rule may be changed after seeing validation results.

| Test | Required result |
| --- | --- |
| Trade count | At least 120 completed trades |
| Expectancy | Strictly positive net R after frozen costs |
| Profit factor | Strictly greater than 1.00 |
| Year stability | Positive net expectancy in at least 2 of 3 years, and no single year may contribute more than 70% of total positive R |
| Breadth: H1--H4 | Positive net expectancy in at least 8 of 15 pairs |
| Breadth: H5 | Positive net expectancy in at least 2 of 3 fixed peer groups |
| Drawdown | Maximum closed-trade drawdown no greater than 20 R |
| Payoff sanity | Both wins and losses must exist; average win must be positive and average loss negative |

The gate is deliberately stricter than merely observing a favorable total. Round 3D eligibility is limited to `SURVIVED` hypotheses only. If none survive, Strategy 2 price-pattern discovery stops at Round 3C: no Round 4, holdout, or HistData work is authorized.
