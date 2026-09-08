# RFBC Backtest

Reproducible Phase 2 falsification harness for frozen RFBC v1.0.

## Frozen baseline
- Pairs: EURUSD, GBPUSD, USDJPY
- D1 regime: EMA50 above/below EMA200 plus EMA50 slope over 5 completed D1 candles
- H4 trigger: strict 20-bar breakout using preceding completed H4 bars only
- Signal candle true range <= 2.0x ATR(14)
- Eligible UTC signal closes: Mon-Thu 08:00/12:00/16:00, Fri 08:00/12:00
- Entry: next H4 open; cancel if adverse displacement exceeds 0.20x signal ATR
- SL: 1.50x signal ATR
- TP: 2.50R
- Breakeven: only after a completed H4 close at or beyond +1.50R, then cost-adjusted BE
- Friday flat cutoff: 16:00 UTC
- No H1 confirmation in baseline
- No D1 trend-invalidation exit
- No unfrozen ATR-quantile volatility filter
- No arbitrary 30-day time stop

## Execution variants
M30 and M15 are tested separately as execution-resolution variants. They do not silently modify the frozen H4 RFBC baseline.

## Scope of this dataset
This is the first price-only empirical falsification pass, not final validation. Fixed spread/slippage approximations are used; historical news blocks/exits, historical bid/ask spreads, exact broker slippage, swap, missing-pair expansion, Dukascopy/HistData cross-validation and exact prop-firm adapters remain subsequent validation work if RFBC survives this pass.

AUDUSD may be downloaded for later exploratory coverage but is not part of frozen RFBC v1.0 baseline performance.
