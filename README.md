# RFBC Backtest

Reproducible research and execution repository for frozen RFBC v1.0.

## Current validated state

The full independent 15-pair discovery study is complete using Dukascopy BID/ASK H1 data from 2013-01-01 through 2026-09-01, with H4/D1 bars built from that source and the frozen RFBC v1.0 rules applied unchanged.

Only two pairs passed the fixed promotion gate:

- USDJPY
- AUDJPY

All other tested pairs were rejected.

The fixed promotion gate was:

- full-sample expectancy >= +0.15R
- full-sample profit factor >= 1.30
- unseen-period expectancy > 0

No arbitrary maximum number of pairs was imposed.

## Frozen RFBC v1.0 rules

- D1 regime: EMA50 above/below EMA200 plus EMA50 slope over 5 completed D1 candles
- H4 trigger: strict 20-bar breakout using preceding completed H4 bars only
- Signal candle true range <= 2.0x ATR(14)
- Eligible UTC signal closes: Mon-Thu 08:00/12:00/16:00, Fri 08:00/12:00
- Entry: next H4 open; cancel if adverse displacement exceeds 0.20x signal ATR
- SL: 1.50x signal ATR
- TP: 2.50R
- Breakeven: only after a completed H4 close at or beyond +1.50R, then cost-adjusted BE
- Friday flat cutoff: 16:00 UTC
- No H1 confirmation
- No D1 trend-invalidation exit
- No unfrozen ATR-quantile filter
- No arbitrary time stop

Any strategic rule change creates a new strategy version and requires fresh validation.

## Independent survivor results

### USDJPY

- Full sample: 248 trades
- Expectancy: +0.1833R
- Profit factor: 1.403
- Max drawdown: 5.22%
- Total return at 0.5% nominal risk: +24.83%
- Unseen expectancy: +0.2021R
- Unseen profit factor: 1.468

### AUDJPY

- Full sample: 247 trades
- Expectancy: +0.1998R
- Profit factor: 1.426
- Max drawdown: 3.70%
- Total return at 0.5% nominal risk: +27.28%
- Unseen expectancy: +0.1824R
- Unseen profit factor: 1.409

## Two-pair portfolio evidence

- Return correlation: 0.0227
- Drawdown correlation: -0.0850
- Overlapping trade pairs: 89
- Portfolio Monte Carlo DD P50/P95: 3.76% / 6.43%
- Probability portfolio DD >10%: 0.22%

Both survivors contain JPY, so JPY concentration remains a live risk-control concern. It is not a reason to change the frozen strategy.

## Execution status

USDJPYc has undergone initial Exness Standard Cent execution-property validation and has a manual execution specification under `execution/`.

AUDJPYc must receive the same broker-specific validation before it is enabled for live/manual execution. Until that validation is complete, AUDJPY is research-qualified but not yet broker-qualified.

## Evidence

Primary outputs are under `results_external_discovery/`, including:

- `PAIR_DISCOVERY_SUMMARY.md`
- `pair_ranking.csv`
- `survivors.json`
- `portfolio_monte_carlo.json`
- per-pair trades, metrics, yearly results and Monte Carlo outputs

The completed discovery study was committed in `0b1d4df354de7b16d0071d3faf8e422c0c063bf7`.
