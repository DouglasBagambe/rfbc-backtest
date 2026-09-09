# RFBC Backtest

Reproducible research, validation and execution repository for **frozen RFBC v1.0**.

> **Current status:** RFBC v1.0 is research-qualified, broker-qualified and authorized for **small manual forward trading** on `USDJPYc` and `AUDJPYc` only. Full automatic order placement is not enabled.

## Validated pair set

The independent 15-pair discovery study used Dukascopy BID/ASK data from 2013-01-01 through 2026-09-01, with H4/D1 bars built from that source and frozen RFBC v1.0 applied unchanged.

Only two pairs passed the fixed promotion gate:

- **USDJPY**
- **AUDJPY**

All other tested pairs were rejected. No arbitrary maximum number of pairs was imposed.

Promotion gate:

- full-sample expectancy >= +0.15R
- full-sample profit factor >= 1.30
- unseen-period expectancy > 0

## Frozen RFBC v1.0

- D1 regime: EMA50 vs EMA200 plus EMA50 slope over 5 completed D1 candles
- H4 trigger: strict 20-bar breakout using preceding completed H4 bars only
- Signal candle TR <= 2.0 x ATR(14)
- Eligible UTC closes: Mon-Thu 08:00/12:00/16:00; Fri 08:00/12:00
- Entry: next H4 open; cancel if adverse displacement > 0.20 x signal ATR
- SL: 1.50 x signal ATR
- TP: 2.50R
- Breakeven: only after a completed H4 close >= +1.50R
- Friday flat: 16:00 UTC
- No discretionary overrides or unfrozen filters

Any strategic rule change creates a new version and requires fresh validation.

## Survivor evidence

| Pair | Trades | Expectancy | PF | Max DD | Unseen expectancy | Unseen PF |
|---|---:|---:|---:|---:|---:|---:|
| USDJPY | 248 | +0.1833R | 1.403 | 5.22% | +0.2021R | 1.468 |
| AUDJPY | 247 | +0.1998R | 1.426 | 3.70% | +0.1824R | 1.409 |

Portfolio evidence:

- return correlation: 0.0227
- drawdown correlation: -0.0850
- overlapping trade pairs: 89
- portfolio MC DD P50/P95: 3.76% / 6.43%
- P(portfolio DD >10%): 0.22%

Both survivors contain JPY, so aggregate live risk control remains mandatory.

## Current execution status

Both Exness Standard Cent symbols are broker-qualified:

- `USDJPYc`
- `AUDJPYc`

Current account snapshot used for sizing: **1,001 USC = $10.01 equivalent**.

Tiny-account overlay:

- 0.01 maximum volume per RFBC position
- <=1.00% individual new-trade risk
- <=1.00% aggregate initial open risk
- -1.00% daily realized-loss stop
- -2.00% weekly realized-loss stop
- -3.00% closed-balance HWM warning
- -5.00% hard kill for new entries

Daily/weekly/high-water-mark account state remains operator-enforced during manual execution because the monitor has no broker-account API.

## Live monitoring

Production monitor supports both `USDJPYc` and `AUDJPYc` and sends actionable alerts directly to Telegram.

Direct Render -> Telegram delivery has been tested successfully. Production startup self-tests cover pair mapping, account-risk conversion, simultaneous-signal portfolio gating and all operator-facing alert formats.

Current action vocabulary:

`TRADE`, `SKIP_RISK`, `SKIP_CHASE`, `SKIP_PORTFOLIO_RISK`, `MOVE_BE`, `FRIDAY_CLOSE`, `STALE`, `ERROR`, `NONE`.

Detailed operating instructions: `docs/RFBC_V10_LIVE_OPERATIONS_MANUAL.md`.

## Forward phase

RFBC v1.0 is now in **small manual forward trading**. The first naturally occurring live ticket must be visually sanity-checked before submission.

Formal review is planned after approximately **30 forward/live trades or six months**, whichever provides the more meaningful evidence window.

Full automatic execution remains a later phase and should use an MT5 EA, VPS or dedicated scheduler rather than ChatGPT in the critical timing/execution path.

## Evidence and documentation

- `docs/RFBC_V10_MASTER_SYSTEM_MANUAL.md`
- `docs/RFBC_V10_LIVE_OPERATIONS_MANUAL.md`
- `docs/RFBC_V10_VALIDATION_REPORT.md`
- `execution/RFBC_V10_PORTFOLIO_RISK_OVERLAY.md`
- `execution/RFBC_V10_LIVE_JOURNAL_AND_REVIEW.md`
- `results_external_discovery/PAIR_DISCOVERY_SUMMARY.md`
- `results_external_discovery/pair_ranking.csv`
- `results_external_discovery/survivors.json`
- `results_external_discovery/portfolio_monte_carlo.json`

The completed 15-pair discovery study was committed in `0b1d4df354de7b16d0071d3faf8e422c0c063bf7`.

## Expansion

Do not retune RFBC v1.0 to force more pairs. Strategy 2 and any future system are separate evidence chains. There is no arbitrary five-pair cap: future components are added only when they independently validate and improve the portfolio.