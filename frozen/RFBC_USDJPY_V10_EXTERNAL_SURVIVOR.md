# RFBC USDJPY v1.0 — External Survivor Freeze

Status: **FROZEN FOR BROKER-SPECIFIC VALIDATION**

This file freezes Candidate A exactly as externally replicated on independent Dukascopy H1 BID/ASK data through 2026-09-01. Any rule change creates a new strategy version and requires full revalidation.

## Instrument
- USDJPY only
- Broker symbol mapping may use suffixes such as `USDJPYc`; symbol suffixes do not change strategy logic.

## Frozen rules
- D1 trend regime: EMA50 above EMA200 for longs, below EMA200 for shorts.
- EMA50 slope confirmation over 5 completed D1 candles in the trade direction.
- Use completed D1 candles only.
- H4 ATR(14).
- H4 breakout lookback: 20 completed H4 bars.
- Long signal: H4 close strictly above prior 20-H4 high.
- Short signal: H4 close strictly below prior 20-H4 low.
- Signal candle true range must be <= 2.0 × ATR(14).
- Eligible UTC H4 closes: Mon-Thu 08:00, 12:00, 16:00; Fri 08:00, 12:00.
- Entry: next H4 open.
- No-chase: cancel if adverse next-H4 displacement from signal close exceeds 0.20 × signal ATR.
- Initial SL: 1.50 × signal ATR.
- TP: 2.50R.
- Breakeven: only after a completed H4 close reaches or exceeds +1.50R; then move to cost-adjusted breakeven.
- Friday cutoff: flat at 16:00 UTC.
- No H1 confirmation.
- No D1 trend-invalidation exit.
- No extra volatility quantile filter.
- No arbitrary time stop.

## External replication evidence
Independent Dukascopy BID/ASK replication, 2013-01-01 through 2026-09-01:
- Trades: 248
- Expectancy: +0.1833R
- Profit factor: 1.403
- Max DD at 0.5% risk: 5.22%
- Total return at 0.5% risk: +24.83%
- Unseen 2022-03-04 onward: 100 trades, +0.2021R expectancy, PF 1.468, max DD 5.22%
- 5,000-run weekly block bootstrap: DD P50 5.93%, DD P95 10.76%, probability DD >10% 7.54%

## Promotion state
Not live-ready yet. Remaining gate: broker-specific Exness `USDJPYc` validation, costs, swap, session behavior, lot sizing, and forward monitoring.
