# RFBC Full Pair Discovery — Codex Runbook

## Objective
Run a one-off, reproducible external validation of frozen RFBC v1.0 across the predefined FX universe using Dukascopy H1 BID/ASK data from 2013-01-01 through 2026-09-01.

## Non-negotiable rules
- Do not modify RFBC strategy logic.
- Do not tune parameters per pair.
- Preserve the frozen rule set exactly: D1 EMA50/EMA200 trend + 5-bar EMA50 slope, strict 20-H4 breakout, TR <= 2.0 ATR(14), eligible H4 close times, next-H4 entry, 0.20 ATR no-chase, 1.50 ATR SL, 2.50R TP, BE after completed H4 close reaches +1.50R, Friday flat 16:00 UTC.
- Keep execution BID/ASK aware exactly as in the existing external USDJPY validation.
- Treat USDJPY as control/reference; do not retune it.

## Universe
USDJPY, EURUSD, GBPUSD, AUDUSD, NZDUSD, USDCAD, USDCHF, EURJPY, GBPJPY, AUDJPY, CADJPY, CHFJPY, EURGBP, EURAUD, GBPAUD.

## Required workflow
1. Inspect the repository and verify the existing external-validation scripts before running anything.
2. Fix only infrastructure/data-pipeline issues that prevent the exact frozen test from running. Do not change strategy behavior.
3. Download Dukascopy H1 BID and ASK data for each pair from 2013-01-01 to 2026-09-01.
4. Build H4 and D1 bars with the same conventions already used for USDJPY.
5. Run each pair independently and checkpoint results immediately after each pair so a crash does not lose prior work.
6. Persist outputs under `results_external_discovery/<PAIR>/`.
7. For each pair report, at minimum:
   - full-period trades
   - full-period expectancy R
   - full-period profit factor
   - full-period max drawdown
   - unseen 2022-03-04 to 2026-09-01 trades
   - unseen expectancy R
   - unseen profit factor
   - unseen max drawdown
   - yearly metrics
   - Monte Carlo summary
8. Use the predeclared promotion gate already encoded in the repo where applicable: full expectancy >= +0.15R, full PF >= 1.30, unseen expectancy > 0. Do not weaken this gate after seeing results.
9. Create a consolidated table ranking all 15 pairs.
10. After individual testing only, evaluate diversification among survivors using trade/equity correlation and overlapping drawdowns. Do not simply pick the five highest returns.

## Robustness / integrity checks
- Verify no timestamp duplication.
- Verify BID/ASK H1 alignment.
- Preserve missing sessions rather than fabricating bars.
- Exclude incomplete terminal aggregation buckets.
- Record ambiguous same-H1 stop/target events if any.
- Confirm no data leakage from incomplete D1/H4 bars.
- Keep an audit trail of any infrastructure-only code changes.

## Final deliverables
Commit all code fixes and small text/CSV result files needed to reproduce conclusions. Avoid committing huge raw market datasets.

Create:
- `results_external_discovery/PAIR_DISCOVERY_SUMMARY.md`
- `results_external_discovery/pair_ranking.csv`
- `results_external_discovery/survivors.json`
- per-pair result folders

The summary must clearly state:
- which pairs SURVIVED
- which pairs were REJECTED
- the strongest diversified survivor subset
- whether RFBC has enough independent survivors to support a multi-pair portfolio
- any reasons the study is inconclusive

Do not declare a pair live-ready. This is strategy validation only; broker-specific symbol validation and execution constraints happen later.
