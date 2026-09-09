# RFBC v1.0 Validated Pair Set

Status: frozen research result.

## Validated pairs

The full predefined 15-pair discovery universe was tested with the exact frozen RFBC v1.0 rules and independent Dukascopy BID/ASK data from 2013-01-01 through 2026-09-01.

The only pairs that passed the unchanged promotion gate were:

1. USDJPY
2. AUDJPY

No arbitrary cap was applied. Every pair that passed would have been retained for portfolio review.

## Promotion gate

A pair had to satisfy all of the following:

- full-independent expectancy >= +0.15R
- full-independent profit factor >= 1.30
- unseen-period expectancy > 0

The gate was not changed after results were observed.

## Survivor metrics

### USDJPY

- full trades: 248
- full expectancy: +0.1833R
- full profit factor: 1.403
- full max drawdown: 5.22%
- total return at 0.5% nominal risk: +24.83%
- unseen expectancy: +0.2021R
- unseen profit factor: 1.468

### AUDJPY

- full trades: 247
- full expectancy: +0.1998R
- full profit factor: 1.426
- full max drawdown: 3.70%
- total return at 0.5% nominal risk: +27.28%
- unseen expectancy: +0.1824R
- unseen profit factor: 1.409

## Portfolio evidence

For the equal-risk USDJPY + AUDJPY survivor portfolio:

- return correlation: 0.0227
- drawdown correlation: -0.0850
- overlapping trade pairs: 89
- portfolio Monte Carlo DD P50: 3.76%
- portfolio Monte Carlo DD P95: 6.43%
- probability portfolio DD >10%: 0.22%

Both pairs contain JPY. This creates currency concentration risk and must be controlled at the execution/portfolio layer. It does not invalidate either independently qualified strategy-pair combination and must not be addressed by silently changing RFBC rules.

## Rejected universe

The other 13 tested pairs were rejected under the same fixed criteria. They are not approved for RFBC v1.0 live execution.

## Freeze policy

RFBC v1.0 means the existing frozen rules exactly. No parameter tuning, pair-specific filters, extra confirmations, alternative exits, session changes or discretionary overrides may be added under the v1.0 label.

Any strategic rule change creates a new RFBC version and requires a new independent validation cycle.

## Evidence source

The full discovery outputs are under `results_external_discovery/`. The study completion commit is `0b1d4df354de7b16d0071d3faf8e422c0c063bf7`.
