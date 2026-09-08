# RFBC Backtest

Reproducible Phase 2 validation harness for the RFBC forex strategy.

## Scope
- Pairs: EURUSD, GBPUSD, USDJPY, AUDUSD
- Core stack: D1 regime, H4 setup, H1 confirmation
- Lower-timeframe validation variants: M30 and M15
- Baseline: 20-H4 breakout, ATR(14) stop at 1.5×ATR, 2.5R target
- Conservative same-bar handling: if stop and target are both touched in one H4 candle, stop is assumed first
- Costs: pair-specific spread assumptions + 0.2 pip slippage per side approximation

The lower-timeframe variants are tested separately and do not alter baseline RFBC results.

## Important limitation
The first pass is price-only. Historical high-impact news-event filtering and broker-specific tick/spread reconstruction are separate validation passes before any live PASS decision.
