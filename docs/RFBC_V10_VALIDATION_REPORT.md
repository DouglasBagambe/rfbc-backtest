# RFBC v1.0 Validation Report

> **Status:** FINAL RESEARCH VALIDATION RECORD  
> **Validated pair set:** **USDJPY + AUDJPY**  
> **Data:** independent Dukascopy BID/ASK, 2013-01-01 through 2026-09-01  
> **Prepared:** 9 September 2026

---

## Executive conclusion

RFBC v1.0 was tested across a predeclared 15-pair liquid-FX universe using the frozen strategy definition and independent Dukascopy BID/ASK history. Exactly **two pairs survived** the unchanged promotion gate: **USDJPY and AUDJPY**.

> **VALIDATION DECISION:** Promote USDJPY and AUDJPY to the RFBC v1.0 research-qualified set. Reject the remaining 13 pairs. Do not retune RFBC v1.0 to force additional survivors.

---

## Frozen promotion gate

A pair survived only if all of the following were true:

| Gate | Threshold |
|---|---:|
| Full-sample expectancy | >= +0.15R |
| Full-sample profit factor | >= 1.30 |
| Unseen-period expectancy | > 0 |

The gate was not changed after results were observed.

---

## Frozen strategy definition

| Component | Rule |
|---|---|
| D1 trend | EMA50 vs EMA200 + EMA50 slope over 5 completed D1 candles |
| H4 trigger | Strict 20-bar breakout against preceding completed H4 bars |
| Signal filter | Signal TR <= 2.0 x ATR(14) |
| Eligible signal closes | Mon-Thu 08:00/12:00/16:00 UTC; Fri 08:00/12:00 UTC |
| Entry | Next H4 open; cancel if adverse displacement > 0.20 x signal ATR |
| Initial stop | 1.50 x signal ATR |
| Target | 2.50R |
| Breakeven | Completed H4 close >= +1.50R, then cost-adjusted BE |
| Friday | Flat at 16:00 UTC |

No H1 confirmation, discretionary trend-invalidating exit, arbitrary time stop, ATR-quantile filter or pair-specific retuning was added.

---

## Data and execution methodology

- Independent Dukascopy BID/ASK history from 2013-01-01 through 2026-09-01.
- Signals constructed from BID bars.
- Long entries use ASK; short entries use BID.
- Long stop/target execution is evaluated against BID; short stop/target execution against ASK.
- H4 and D1 structures were built from independent source data using UTC boundaries.
- Incomplete terminal buckets were excluded.
- Friday-flat and completed-H4 breakeven behavior were preserved exactly.
- Weekly-block Monte Carlo used 5,000 paths.
- Nominal return/DD metrics were evaluated at 0.5% risk for research comparability.

Chronology:

| Period | Dates |
|---|---|
| Overlap/reference | 2013-01-01 to 2022-03-03 |
| Unseen | 2022-03-04 to 2026-09-01 |
| Full independent | 2013-01-01 to 2026-09-01 |

---

## Survivor results

| Pair | Trades | Win rate | Expectancy | PF | Max DD | Total return | CAGR | Unseen trades | Unseen expectancy | Unseen PF |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| **USDJPY** | 248 | 43.95% | +0.1833R | 1.403 | 5.22% | +24.83% | 1.76% | 100 | +0.2021R | 1.468 |
| **AUDJPY** | 247 | 42.91% | +0.1998R | 1.426 | 3.70% | +27.28% | 1.93% | 107 | +0.1824R | 1.409 |

### Monte Carlo - survivors

| Pair | Final P05 | Final P50 | Final P95 | DD P50 | DD P95 | P(DD >10%) |
|---|---:|---:|---:|---:|---:|---:|
| USDJPY | 1.040 | 1.245 | 1.484 | 5.93% | 10.76% | 7.54% |
| AUDJPY | 1.076 | 1.268 | 1.509 | 5.32% | 9.43% | 3.54% |

---

## Rejected-pair summary

| Pair | Trades | Expectancy | PF | Unseen expectancy | Decision |
|---|---:|---:|---:|---:|---|
| GBPJPY | 269 | +0.1160R | 1.244 | -0.0248R | REJECTED |
| GBPUSD | 234 | +0.1042R | 1.197 | +0.1930R | REJECTED |
| CHFJPY | 285 | +0.0903R | 1.190 | +0.0630R | REJECTED |
| CADJPY | 239 | +0.0900R | 1.175 | +0.0311R | REJECTED |
| EURAUD | 226 | +0.0817R | 1.163 | +0.0646R | REJECTED |
| EURJPY | 265 | +0.0802R | 1.167 | +0.0535R | REJECTED |
| USDCHF | 208 | +0.0406R | 1.079 | +0.1079R | REJECTED |
| GBPAUD | 232 | +0.0067R | 1.013 | +0.0273R | REJECTED |
| USDCAD | 217 | -0.0454R | 0.918 | +0.0309R | REJECTED |
| AUDUSD | 230 | -0.0626R | 0.889 | -0.0849R | REJECTED |
| EURUSD | 241 | -0.0788R | 0.861 | +0.2988R | REJECTED |
| NZDUSD | 219 | -0.0873R | 0.840 | -0.1140R | REJECTED |
| EURGBP | 220 | -0.1776R | 0.708 | -0.3064R | REJECTED |

A pair can show positive unseen performance and still be rejected because the frozen full-sample gate must also pass. No exception was made after seeing favorable subperiods.

---

## Two-pair portfolio evidence

| Metric | Result |
|---|---:|
| Return correlation | 0.0227 |
| Drawdown correlation | -0.0850 |
| Overlapping trade pairs | 89 |
| Equal-risk historical portfolio max DD | 3.28% |
| Portfolio Monte Carlo final P05 | 1.110 |
| Portfolio Monte Carlo final P50 | 1.263 |
| Portfolio Monte Carlo final P95 | 1.450 |
| Portfolio Monte Carlo DD P50 | 3.76% |
| Portfolio Monte Carlo DD P95 | 6.43% |
| P(portfolio DD >10%) | 0.22% |

> **CONCENTRATION RISK:** both survivors contain JPY. Low historical return/drawdown correlation does not eliminate common JPY-event exposure. This is handled through live aggregate-risk controls rather than by changing the frozen strategy.

---

## Data-quality findings

The source data were not silently cosmetically repaired.

- EURUSD contained one crossed opening quote at **2016-06-08 14:00 UTC**.
- CADJPY contained two crossed opening quotes.
- Source anomalies were preserved and documented rather than altered to improve results.
- The consolidated research output reports one ambiguous H1 stop-first event for EURUSD; survivor pairs report zero such events.
- No survivor trade was left unclosed at the end of the dataset.

These findings do not change the survivor decision because the frozen gate and execution conventions were applied consistently.

---

## Interpretation

RFBC v1.0 is a **positive-expectancy, lower-frequency breakout strategy**, not a high-win-rate system. The survivor win rates are about 43-44%, but average winning trades are materially larger than average losing trades, producing positive expectancy and profit factors above the promotion gate.

The validation supports a narrow conclusion only:

> RFBC v1.0 demonstrated sufficient independent historical robustness on USDJPY and AUDJPY to justify controlled broker qualification and small forward testing.

It does **not** prove future profitability, guarantee a particular monthly return, or justify increasing risk to accelerate account growth.

---

## Final research status

- **USDJPY:** SURVIVED / RESEARCH-QUALIFIED
- **AUDJPY:** SURVIVED / RESEARCH-QUALIFIED
- **All other tested pairs:** REJECTED for RFBC v1.0
- **RFBC v1.0 strategy logic:** FROZEN

Primary evidence is under `results_external_discovery/`, including `PAIR_DISCOVERY_SUMMARY.md`, `pair_ranking.csv`, per-pair trades/yearly metrics/Monte Carlo, `survivors.json`, and `portfolio_monte_carlo.json`.

Operational qualification is maintained separately in `docs/RFBC_V10_LIVE_OPERATIONS_MANUAL.md` and `execution/RFBC_V10_OPERATIONAL_STATUS.md`.