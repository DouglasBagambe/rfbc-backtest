# Strategy 2 — M15/H1 Screening Gate

**Status:** FROZEN FOR PRELIMINARY SCREENING  
**Scope:** Dukascopy BID/ASK M15 data; development 2013-01-01 to 2017-12-31, validation 2018-01-01 to 2020-12-31. The 2021+ period is not read by the screening runner.

## Common execution model

- Signals use completed M15 BID and completed H1 BID information only.
- Entry occurs at the next M15 open: ASK plus 0.10 pip slippage for a long; BID minus 0.10 pip for a short.
- Long exits use BID less 0.10 pip slippage; short exits use ASK plus 0.10 pip slippage.
- Same-candle SL/TP conflicts are recorded and resolved stop-first.
- One active trade per pair/hypothesis; Friday 16:00 UTC is a forced exit.

## Gate

Each hypothesis must achieve all of the following on the combined, predeclared universe before it can enter parameter-neighborhood work:

| Test | Threshold |
|---|---:|
| Development expectancy | >= +0.10R |
| Development PF | >= 1.15 |
| Validation expectancy | >= +0.05R |
| Validation PF | >= 1.10 |
| Development + validation trades | >= 120 |

> **IMPORTANT:** A result from EURUSD, GBPUSD and USDJPY alone is an acquisition-stage checkpoint only. It cannot promote a final Strategy 2 candidate or access holdout/external data until the predefined 15-pair universe is complete.
