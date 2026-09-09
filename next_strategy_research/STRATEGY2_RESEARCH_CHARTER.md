# Strategy 2 Research Charter

> **Status:** ACTIVE RESEARCH CHARTER  
> **Project:** Fx  
> **Relationship to RFBC:** fully separate research track; RFBC v1.0 must remain untouched  
> **Objective:** discover the strongest robust high-frequency FX strategy family we can prove exists, without forcing a predefined win rate, reward:risk ratio, pair count, or monthly return.

---

## 1. Core mandate

Be highly ambitious on edge discovery and highly conservative on validation.

The goal is to find a strategy that is materially faster and psychologically different from RFBC, ideally producing multiple portfolio opportunities per day across a broad liquid FX universe while retaining strong expectancy, realistic execution, and controlled drawdown.

The desired profile is aspirational, not a backtest target to overfit:

| Metric | Ambitious research target |
|---|---:|
| Portfolio frequency | 3-6 quality trades/day average |
| Initial universe | 10-20 liquid FX pairs |
| Win rate | 60%+ desirable; 65%+ excellent; 70%+ exceptional |
| Average winner | preferably >=0.8R; 1R+ ideal if robust |
| Expectancy | >=+0.20R/trade desirable; +0.30R exceptional |
| Profit factor | >=1.50 desirable; 1.70+ exceptional |
| Historical max DD | preferably <10% at 1% nominal risk |
| Unseen / external data | must remain clearly profitable |

Do **not** optimize specifically for $100 -> $170 in one month, 70% win rate, 1:1 RR, five trades/day, or any other user brainstormed number. Those are only mental reference points.

---

## 2. Hard prohibitions

The following are forbidden:

- martingale;
- grid recovery;
- averaging into losing positions;
- hidden asymmetric tail risk;
- widening stops after entry;
- pair-specific hand tuning after seeing holdout results;
- lookahead / future leakage;
- repeated holdout reuse until a candidate passes;
- changing validation gates after seeing outcomes;
- presenting in-sample profitability as validation;
- modifying RFBC v1.0.

A strategy that wins 90% of the time but occasionally loses catastrophic amounts is a rejection, not a success.

---

## 3. Strategy-family search space

Start broad and cheap, then go deep only on survivors. Research independent families rather than one giant indicator soup.

Priority families:

1. **Intraday trend pullback continuation**  
   Higher-timeframe direction + session liquidity + controlled pullback + continuation trigger.

2. **Session/opening-range expansion**  
   London/New York range formation and expansion with realistic spread/session controls.

3. **Short-horizon mean reversion**  
   Abnormal extension away from a rolling intraday mean followed by statistically defined reversion, with strict regime filters.

4. **Compression -> expansion**  
   Volatility contraction followed by directional expansion, structurally distinct from RFBC's slow H4 breakout.

5. **Sweep/reclaim / failed-break structure**  
   Liquidity sweep or failed breakout followed by reclaim and continuation/reversal confirmation.

6. **Momentum continuation**  
   Intraday impulse + shallow retracement + renewed momentum.

7. **Time-of-day statistical edges**  
   Only where a simple, causal market rationale and repeated cross-pair evidence exist.

Additional sensible families may be proposed, but each must have a clear causal hypothesis and a falsifiable definition.

---

## 4. Timeframes and execution

Prefer M15/H1 research for frequency. M5 may be explored only if data quality and transaction-cost realism are sufficient. Avoid tick-level complexity unless a survivor genuinely requires it.

Signals must be based only on completed information available at decision time.

Execution assumptions must include realistic BID/ASK behavior, spread, slippage sensitivity, session boundaries, Friday handling, and no impossible same-bar ordering assumptions.

---

## 5. Universe

Start with a predefined liquid universe before viewing strategy results. At minimum include:

EURUSD, GBPUSD, USDJPY, AUDUSD, NZDUSD, USDCAD, USDCHF, EURJPY, GBPJPY, AUDJPY, CADJPY, CHFJPY, EURGBP, EURAUD, GBPAUD.

Add other liquid crosses only by predeclared rationale, not because a backtest looked attractive after searching thousands of symbols.

Do not impose an arbitrary final pair cap. Keep every independently qualified pair only if portfolio analysis shows it adds useful edge/diversification without unacceptable concentration.

---

## 6. Research pipeline

### Stage A - broad prototype falsification

Implement 15-30 simple, causal hypotheses across multiple strategy families using a common backtest engine and common cost model.

Kill weak ideas quickly.

### Stage B - development / validation chronology

Use strict chronological splits. Development is allowed for bounded design work; validation is for selection; holdout remains untouched.

### Stage C - parameter robustness

For surviving families, test parameter neighborhoods. A candidate should survive reasonable nearby values rather than depend on one exact setting.

### Stage D - pair breadth

Require evidence across multiple instruments or a clear pair-specific market rationale. Reject strategies that depend on one accidental symbol unless independently extraordinary and externally validated.

### Stage E - untouched holdout

Run once after design is frozen. Do not recycle the holdout as a development set.

### Stage F - independent external data

Use an independently sourced BID/ASK dataset for final validation. Rebuild bars ourselves where practical and document data anomalies rather than silently repairing them.

### Stage G - Monte Carlo / stress

Run block-bootstrap Monte Carlo, loss-streak analysis, parameter perturbation, spread/slippage stress, delayed-entry sensitivity, and regime/year breakdowns.

### Stage H - portfolio construction

Analyze survivors jointly:

- return correlation;
- drawdown correlation;
- trade overlap;
- currency concentration;
- simultaneous losses;
- combined equity curve;
- portfolio Monte Carlo DD;
- marginal contribution of each pair/strategy.

### Stage I - broker qualification

Only after strategy validation: map survivors to Exness symbols and validate broker contract size, minimum lot, step, spread, swaps, stops level, sessions and practical risk sizing.

---

## 7. Promotion philosophy

Do not promote a strategy merely because one metric is impressive.

A candidate should have:

- positive expectancy after realistic costs;
- strong PF;
- adequate sample size;
- stable chronology;
- acceptable drawdown;
- survivable loss streaks;
- parameter robustness;
- external-data survival;
- no hidden tail-risk mechanism;
- realistic broker execution;
- useful portfolio contribution.

The exact final gate may differ by strategy family because frequency/payoff distributions differ, but **all gates must be frozen before final holdout/external evaluation**.

---

## 8. Risk philosophy

Research the edge independently from aggressive leverage.

For reporting, show at least 0.25%, 0.50%, and 1.00% nominal risk scenarios. The live default for a new strategy should begin at 0.25-0.50% until forward evidence exists.

No strategy may earn a passing grade only because of high leverage.

---

## 9. Required deliverables

Produce and commit:

- hypothesis register;
- strategy definitions;
- common execution/cost model;
- development/validation/holdout definitions;
- broad prototype screen;
- rejected-family log with reasons;
- survivor parameter-neighborhood analysis;
- yearly/regime breakdowns;
- transaction-cost and slippage stress;
- Monte Carlo results;
- external-data validation;
- pair-level survivor decisions;
- portfolio analysis;
- final recommendation;
- clean Markdown reports following `docs/DOCUMENTATION_STANDARD.md`;
- polished PDF/DOCX formal report once a candidate reaches final validation.

Checkpoint completed research stages so a crash does not destroy progress.

---

## 10. Success condition

The project succeeds if it finds a genuinely robust high-frequency edge **or** if it conclusively rejects the tested families without fooling us.

A truthful `NO ROBUST STRATEGY FOUND` is better than a manufactured monster.

If a true monster appears, the evidence should make that conclusion unavoidable rather than dependent on optimism.
