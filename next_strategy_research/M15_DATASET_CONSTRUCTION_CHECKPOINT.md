# Strategy 2 — M15 Dataset Construction Checkpoint

**Date:** 10 September 2026  
**Status:** PENDING SCREENING  
**Scope:** Independent Dukascopy UTC BID/ASK M15 data; EURUSD, GBPUSD, USDJPY only

## Decision

> **DECISION:** EURUSD, GBPUSD and USDJPY have passed source-file validation and have locally derived M15, H1, H4 and D1 BID/ASK bars. This is an acquisition checkpoint only; it is not a Strategy 2 result or candidate promotion.

## Source audit

| Pair | BID/ASK rows aligned | Date range UTC | Crossed opening spreads | Exact boundary duplicates per side | Missing expected weekday M15 slots |
|---|---:|---|---:|---:|---:|
| EURUSD | 354,195 | 2013-01-01 00:00 to 2026-09-01 21:00 | 0 | 120 | 1,369 |
| GBPUSD | 354,151 | 2013-01-01 00:00 to 2026-09-01 21:00 | 0 | 119 | 1,383 |
| USDJPY | 354,186 | 2013-01-01 00:00 to 2026-09-01 21:00 | 0 | 120 | 1,373 |

## Handling rules applied

- All timestamps remain UTC; no timezone transformation was applied.
- Monthly fetch boundaries contain exact duplicate OHLCV records. They are counted in the manifest and collapsed only after verifying that no duplicate timestamp has conflicting prices.
- Missing weekday slots are retained as an anomaly count. They are not forward-filled or invented.
- H1/H4 bars require four/sixteen complete M15 source bars. D1 bars require 96 M15 rows Monday–Thursday and 84 on Friday, so incomplete daily buckets are excluded.

## Research status

The M15/H1 screen runner and its frozen preliminary gate are present in:

- [run_m15_screen.py](run_m15_screen.py)
- [M15_SCREEN_GATE.md](M15_SCREEN_GATE.md)

> **PENDING:** The local machine had only 506 MB `MemAvailable` while the screen started, below the established 1 GB no-swap safety floor. No hypothesis result was accepted or generated. Resume the screen only after sufficient RAM is available, then continue acquisition for the remaining predeclared 12 pairs before any candidate can access holdout or external data.
