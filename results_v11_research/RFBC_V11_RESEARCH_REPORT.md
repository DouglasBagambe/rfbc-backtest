# RFBC v1.1 Exploratory Research Report

## Scope and safeguards

This is exploratory analysis of 2013 through March 2022 price-only data. Frozen RFBC v1.0 code and `results/` were not changed. No live trading, broker, or MT5 connection was used.

## v1.0 control

- Trades: 464
- Expectancy: -0.0459R
- Profit factor: 0.917
- Maximum drawdown at 0.5% risk: 22.66%

## Phase A: corrected bootstrap

The corrected prop bootstrap assigns every sampled week/day a synthetic sequential simulation identity. Duplicate sampled historical weeks therefore cannot reuse an original calendar-date daily balance. Monte Carlo uses only sequential R outcomes in sampled weekly blocks; it does not carry real dates across paths.

## Phase B: strongest descriptive findings

- USDJPY: 151 trades, expectancy 0.1689R, PF 1.360
- GBPUSD: 139 trades, expectancy -0.0605R, PF 0.895
- EURUSD: 174 trades, expectancy -0.2207R, PF 0.642

Chronological v1.0 control expectancy: development 0.0959R (173 trades), validation -0.1029R (158 trades), holdout -0.1626R (133 trades).
Corrected 5,000-path prop bootstrap daily-breach probabilities are 0.25%: 0.00%, 0.50%: 0.00%, 1.00%: 0.00%; zero is expected because the H4 dataset has at most one exit per original day and synthetic days reset correctly.

Feature tables are saved as CSVs; they are descriptive, not selection proof.

## Phase C: USDJPY parameter stability

- Positive/PF>=1.0 USDJPY sensitivity cells: 52 of 52.
- Inspect `usdjpy_sensitivity.csv` for every tested cell; no Cartesian mega-search was run.

## Phase D-F: candidate decision

No signal-time filter passed the predeclared development threshold (>=0.15R, PF>=1.30) while also staying positive in validation and holdout. The three parameter variants below are therefore stress tests, not promoted candidates:
- **v11_usdjpy_control** (USDJPY only; frozen v1.0 parameters (control subset)) — 151 trades, 1.50/month, expectancy 0.1689R, PF 1.360, DD 5.26%, CAGR 1.51%, total return 13.23%; development/validation/holdout expectancy = 0.4166/-0.0977/0.0796R; corrected 0.5% MC final P05/P50/P95 = $99,016/$113,161/$128,938, DD P50/P95 = 4.99%/9.39%, 5% internal halt = 49.80%.
- **v11_usdjpy_l25_rr3** (USDJPY only; 25-H4 breakout, 1.50 ATR stop, 3.00R target) — 136 trades, 1.35/month, expectancy 0.2127R, PF 1.464, DD 5.69%, CAGR 1.72%, total return 15.17%; development/validation/holdout expectancy = 0.5386/-0.0686/0.0736R; corrected 0.5% MC final P05/P50/P95 = $101,112/$115,008/$131,897, DD P50/P95 = 4.58%/8.36%, 5% internal halt = 39.84%.
- **v11_usdjpy_l25_wide** (USDJPY only; 25-H4 breakout, 1.75 ATR stop, 2.50R target) — 135 trades, 1.34/month, expectancy 0.1614R, PF 1.373, DD 4.47%, CAGR 1.29%, total return 11.22%; development/validation/holdout expectancy = 0.4047/-0.0714/0.0737R; corrected 0.5% MC final P05/P50/P95 = $98,860/$111,103/$125,156, DD P50/P95 = 4.41%/8.26%, 5% internal halt = 37.18%.
Recommendation: **REJECT** a v1.1 candidate on this dataset. CONTINUE RESEARCH only after independent data validation, not further optimization of this sample.

## Mandatory next validation

Re-run frozen v1.0 and any candidate unchanged on independent Dukascopy/HistData data with a validated timestamp/session convention, historical bid/ask costs, news handling, and broker-specific prop rules. Do not declare a tradable edge from this dataset.
