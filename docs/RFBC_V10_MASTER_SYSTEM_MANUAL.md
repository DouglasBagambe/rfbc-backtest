# RFBC v1.0
## Master System Manual, Validation Record & Operational Guide

> **Version:** RFBC v1.0  
> **Prepared:** 9 September 2026  
> **Research-qualified pairs:** **USDJPY, AUDJPY**  
> **Broker-qualified symbols:** **USDJPYc, AUDJPYc**  
> **Operational status:** **READY FOR SMALL MANUAL FORWARD TRADING**  
> **Full-auto status:** **NOT ENABLED**

---

## Executive decision

RFBC v1.0 survived independent external testing on exactly **two** instruments: **USDJPY** and **AUDJPY**.

> **DECISION:** The frozen RFBC v1.0 pair set is **USDJPY + AUDJPY**. No arbitrary pair cap was used; the other 13 tested pairs were rejected by the unchanged promotion gate.

RFBC v1.0 is frozen. Do not retune it merely to create more signals, raise the win rate, or force additional pairs.

---

## Frozen strategy rules

| Component | RFBC v1.0 rule |
|---|---|
| D1 regime | EMA50 vs EMA200 + EMA50 slope over 5 completed D1 candles |
| H4 trigger | Strict 20-bar breakout against preceding completed H4 bars |
| Signal candle filter | True range <= 2.0 x ATR(14) |
| Eligible closes | Mon-Thu 08:00 / 12:00 / 16:00 UTC; Fri 08:00 / 12:00 UTC |
| Entry | Next H4 open; cancel if adverse displacement > 0.20 x signal ATR |
| Initial SL | 1.50 x signal ATR |
| TP | 2.50R |
| Breakeven | Completed H4 close >= +1.50R, then cost-adjusted BE |
| Friday rule | Flat at 16:00 UTC |
| Discretionary overrides | Not permitted |

### Strategy integrity

Do not silently add H1 confirmation, D1 invalidation exits, arbitrary time stops, ATR-quantile filters, discretionary early exits, averaging down, pyramiding, stop widening or pair-specific tuning.

Any strategic change creates a **new version** and requires a new evidence chain.

---

## Independent validation evidence

| Pair | Trades | Expectancy | PF | Max DD | Unseen expectancy | Unseen PF | Decision |
|---|---:|---:|---:|---:|---:|---:|---|
| USDJPY | 248 | +0.1833R | 1.403 | 5.22% | +0.2021R | 1.468 | **SURVIVED** |
| AUDJPY | 247 | +0.1998R | 1.426 | 3.70% | +0.1824R | 1.409 | **SURVIVED** |

### Portfolio evidence

| Metric | Result |
|---|---:|
| Return correlation | 0.0227 |
| Drawdown correlation | -0.0850 |
| Overlapping trade pairs | 89 |
| Portfolio MC DD P50 | 3.76% |
| Portfolio MC DD P95 | 6.43% |
| P(portfolio DD >10%) | 0.22% |

> **RISK NOTE:** both survivors contain JPY. Historical return/drawdown correlation is low, but common JPY event exposure remains a live concentration risk.

Raw evidence: `results_external_discovery/`.

---

## Full 15-pair discovery decision

| Pair | Decision | Pair | Decision |
|---|---|---|---|
| EURUSD | REJECTED | EURJPY | REJECTED |
| GBPUSD | REJECTED | GBPJPY | REJECTED |
| AUDUSD | REJECTED | AUDJPY | **SURVIVED** |
| NZDUSD | REJECTED | CADJPY | REJECTED |
| USDCAD | REJECTED | CHFJPY | REJECTED |
| USDCHF | REJECTED | EURGBP | REJECTED |
| USDJPY | **SURVIVED** | EURAUD | REJECTED |
| GBPAUD | REJECTED |  |  |

Promotion gate remained unchanged: full expectancy >= +0.15R, full PF >= 1.30, unseen expectancy > 0.

---

## Broker qualification

### USDJPYc

- Contract size: 1,000 USD
- Minimum volume: 0.01
- Volume step: 0.01
- Digits: 3
- Stops level: 0

### AUDJPYc

Verified from MT5 mobile on 9 September 2026:

- Contract size: 1,000 AUD
- Minimum volume: 0.01
- Volume step: 0.01
- Digits: 3
- Floating spread; observed about 1.1 pips
- Stops level: 0
- Swap long: -0.2 points
- Swap short: -2.1 points
- Triple swap: Wednesday
- Friday session through 20:59
- Chart mode: Bid

AUDJPYc broker evidence is stored in `execution/RFBC_AUDJPYC_BROKER_VALIDATION_CHECKLIST.md` and `broker_validation/output/audjpyc_symbol_properties.json`.

---

## Current account and tiny-account overlay

Fresh account snapshot captured 9 September 2026:

| Field | Value |
|---|---:|
| Balance | 1,001 USC |
| Equity | 1,001 USC |
| USD-equivalent equity | **$10.01** |
| Open positions | None |

Current Render sizing input: `RFBC_EQUITY_USD=10.01`.

| Control | Current rule |
|---|---:|
| Volume | 0.01 maximum per RFBC position |
| Individual new-trade risk | **<= 1.00%** |
| Aggregate initial open risk | **<= 1.00%** |
| Daily realized-loss stop | **-1.00%** |
| Weekly realized-loss stop | **-2.00%** |
| Drawdown warning | **-3.00%** from closed-balance HWM |
| Hard kill for new entries | **-5.00%** from closed-balance HWM |

> **IMPORTANT:** a valid RFBC signal may still be skipped because broker minimum size makes risk too high. This is an execution overlay, not a strategy change.

Because the monitor does not have broker-account API access, actual daily/weekly realized loss and high-water-mark state remain operator-enforced in the manual-forward phase. Every `TRADE` alert reminds the operator to verify these gates.

---

## Deterministic live architecture

```mermaid
flowchart LR
    A[Dukascopy BID/ASK] --> B[RFBC v1.0 monitor]
    B --> C[Individual + aggregate risk gates]
    C --> D[Direct Telegram]
    D --> E[Operator account-state check]
    E --> F[MT5 mobile manual execution]
```

Current production monitor:

- `monitor/rfbc_monitor_multi.py`
- `monitor/webapp.py`
- `monitor/telegram_notify.py`
- `monitor/selftest.py`

It evaluates `USDJPYc` and `AUDJPYc`, calculates 0.01-volume risk, converts AUDJPY JPY risk through USDJPY, applies individual and portfolio risk gates, reconstructs breakeven/Friday management, and emits operator instructions.

### Alert vocabulary

`TRADE`, `SKIP_RISK`, `SKIP_CHASE`, `SKIP_PORTFOLIO_RISK`, `MOVE_BE`, `FRIDAY_CLOSE`, `STALE`, `ERROR`, `NONE`.

---

## Operational verification

- [x] USDJPY research-qualified
- [x] AUDJPY research-qualified
- [x] 15-pair discovery completed
- [x] Portfolio correlation / overlap / Monte Carlo reviewed
- [x] USDJPYc broker-qualified
- [x] AUDJPYc broker-qualified
- [x] Fresh account equity captured
- [x] Individual risk calculation implemented
- [x] Aggregate risk gate implemented
- [x] Same-checkpoint conflict handling implemented
- [x] Direct Telegram secrets configured on Render
- [x] Direct Render -> Telegram test received on phone
- [x] Production startup self-test passed
- [x] Self-test covers all required operator-facing alert actions
- [x] H4 scheduling expanded to every completed H4 checkpoint
- [x] Live journal/review procedure documented
- [x] Live Operations Manual created
- [ ] First naturally occurring live RFBC ticket visually sanity-checked before pressing Buy/Sell

The final unchecked item requires a genuine market signal and is not an engineering blocker.

> **LIVE STATUS:** RFBC v1.0 is **authorized for small manual forward trading on USDJPYc and AUDJPYc only**.

---

## Scheduling and automation boundary

The zero-cost current trigger is an external scheduled wake/check into the free Render service. Render then makes the deterministic decision and sends Telegram directly.

A free Render cron job is not available. A paid cron was deliberately not enabled.

For eventual unattended/full-auto execution, move timing and order placement to an MT5 EA, VPS or dedicated scheduler so ChatGPT is completely outside the critical timing/execution path.

Automation roadmap:

```mermaid
flowchart LR
    A[Manual forward] --> B[Semi-automatic]
    B --> C[Full automatic]
```

Full automatic execution remains a later phase after forward evidence and operational reliability justify it.

---

## Live operations source

Detailed day-to-day instructions: `docs/RFBC_V10_LIVE_OPERATIONS_MANUAL.md`.

Journal and review process: `execution/RFBC_V10_LIVE_JOURNAL_AND_REVIEW.md`.

Portfolio risk policy: `execution/RFBC_V10_PORTFOLIO_RISK_OVERLAY.md`.

---

## Expansion policy

RFBC v1.0 remains frozen. Do not retune it to force more pairs.

Strategy 2 research is separate. Future strategies or pair sets may be added only after independent validation, broker qualification, portfolio analysis and their own operational readiness review. There is no arbitrary five-pair cap.

---

## Documentation rule

All formal RFBC documentation follows `docs/DOCUMENTATION_STANDARD.md`: structured title/status blocks, concise sections, clean tables, callouts, diagrams/checklists where useful, and polished PDF/DOCX equivalents for master and operational documents.
