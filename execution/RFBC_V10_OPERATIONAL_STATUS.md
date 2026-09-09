# RFBC v1.0 Operational Status

> **Research status:** QUALIFIED  
> **Broker status:** USDJPYc + AUDJPYc QUALIFIED  
> **Operational status:** **READY FOR SMALL MANUAL FORWARD TRADING**  
> **Full-auto status:** NOT ENABLED

---

## Final live set

RFBC v1.0 is frozen and live-qualified for the current manual-forward phase on exactly:

| Research pair | Exness symbol | Status |
|---|---|---|
| USDJPY | `USDJPYc` | **READY** |
| AUDJPY | `AUDJPYc` | **READY** |

All other tested RFBC v1.0 pairs remain rejected. No strategy rule was retuned to create this live set.

---

## Broker qualification

### USDJPYc

- Contract size: 1,000 USD
- Minimum volume: 0.01
- Volume step: 0.01
- Digits: 3
- Stops level: 0
- Manual specification: `execution/RFBC_USDJPYC_MANUAL_EXECUTION_SPEC.md`

### AUDJPYc

MT5 mobile evidence captured 9 September 2026 confirms:

- Contract size: 1,000 AUD
- Minimum volume: 0.01
- Volume step: 0.01
- Digits: 3
- Floating spread; observed about 1.1 pips
- Stops level: 0
- Chart mode: Bid
- Swap long: -0.2 points
- Swap short: -2.1 points
- Triple swap: Wednesday
- Friday session through 20:59

Evidence: `execution/RFBC_AUDJPYC_BROKER_VALIDATION_CHECKLIST.md` and `broker_validation/output/audjpyc_symbol_properties.json`.

---

## Account snapshot and sizing

Fresh snapshot captured 9 September 2026:

| Field | Value |
|---|---:|
| Balance | 1,001 USC |
| Equity | 1,001 USC |
| USD-equivalent equity | **$10.01** |
| Open positions | None |

Render currently uses `RFBC_EQUITY_USD=10.01`.

> **MANDATORY:** after every closed trade, deposit, withdrawal, or material equity change, refresh the configured equity before acting on another `TRADE` alert. A valid signal must be skipped if the sizing input is stale or materially wrong.

---

## Portfolio risk overlay

Authoritative rules: `execution/RFBC_V10_PORTFOLIO_RISK_OVERLAY.md`.

| Control | Current rule |
|---|---:|
| Volume | 0.01 maximum per RFBC position |
| Individual new-trade risk | **<= 1.00%** |
| Aggregate initial open risk | **<= 1.00%** |
| Same-checkpoint conflict | lower estimated risk first |
| Exact-risk tie | USDJPYc deterministic tie-break |
| Daily realized-loss stop | **-1.00%** |
| Weekly realized-loss stop | **-2.00%** |
| Drawdown warning | **-3.00%** from closed-balance HWM |
| Hard kill for new entries | **-5.00%** from closed-balance HWM |

Both live pairs contain JPY. Historical portfolio correlation was low, but common JPY event exposure remains real, so the aggregate cap is mandatory.

### Current-account reference amounts

At $10.01 equity, approximately:

- 1% = $0.1001 = 10.01 USC
- 2% = $0.2002 = 20.02 USC
- 3% = $0.3003 = 30.03 USC
- 5% = $0.5005 = 50.05 USC

These are reference amounts only. Percentage rules remain authoritative as equity changes.

> **STATE LIMITATION:** because execution is manual on MT5 mobile and the monitor has no broker-account API, actual daily/weekly realized loss and high-water-mark state cannot be safely fabricated by the cloud monitor. Those four account-state gates are operator-enforced in the current manual-forward phase. Every `TRADE` Telegram alert explicitly reminds the operator to verify them before entry.

---

## Deterministic monitor

Production monitor files:

- `monitor/rfbc_monitor_multi.py`
- `monitor/webapp.py`
- `monitor/telegram_notify.py`
- `monitor/test_rfbc_monitor_multi.py`
- `monitor/selftest.py`

The monitor:

- evaluates both qualified pairs with frozen RFBC v1.0 logic;
- uses completed Dukascopy BID/ASK data;
- preserves broker suffixes `USDJPYc` and `AUDJPYc` in operator alerts;
- applies realistic BUY/SELL price-side handling;
- applies the frozen 0.20 ATR no-chase rule;
- calculates 0.01-volume account risk;
- converts AUDJPY JPY risk through current USDJPY;
- enforces <=1% individual risk;
- enforces <=1% aggregate initial open risk;
- handles simultaneous signals deterministically;
- reconstructs open-trade management for breakeven and Friday flat.

### Action vocabulary

`TRADE`  
`SKIP_RISK`  
`SKIP_CHASE`  
`SKIP_PORTFOLIO_RISK`  
`MOVE_BE`  
`FRIDAY_CLOSE`  
`STALE`  
`ERROR`  
`NONE`

---

## Operational verification completed

### Direct Telegram

**PASS.** Direct Render -> Telegram delivery was tested on 9 September 2026 and the test message was received on the phone.

Path:

```text
Render RFBC monitor -> Telegram Bot API -> G's Fx 101 -> phone
```

Telegram credentials are stored as Render environment secrets and are not committed to GitHub.

### Startup safety self-test

**PASS.** Production deploy startup self-test covers:

- USDJPYc/AUDJPYc mapping;
- 0.01 volume;
- 1% individual and aggregate caps;
- USDJPY risk conversion;
- AUDJPY -> USD risk conversion through USDJPY;
- same-checkpoint portfolio conflict handling;
- existing-open-risk blocking;
- alert formatting for `TRADE`, `SKIP_RISK`, `SKIP_CHASE`, `SKIP_PORTFOLIO_RISK`, `MOVE_BE`, `FRIDAY_CLOSE`, `STALE`, and `ERROR`.

Render log recorded `RFBC_OPERATIONAL_SELFTEST ... ok: True` on the live production deploy.

### Production service

Render service `rfbc-usdjpy-monitor` is live on the free plan. Despite the legacy service name, it now monitors **both USDJPYc and AUDJPYc**.

### H4 checking cadence

The free web service has no free Render cron-job option. A paid cron job was deliberately **not** enabled. Current zero-cost scheduling is therefore:

```text
ChatGPT scheduled wake/check -> Render deterministic monitor -> direct Telegram
```

Checks cover every completed UTC H4 checkpoint (00:00, 04:00, 08:00, 12:00, 16:00, 20:00) on trading weekdays, with a wake attempt shortly beforehand and retry logic for free-tier cold starts.

ChatGPT may also surface a backup diagnostic notification, but it does not decide the trade. The deterministic Render code is the RFBC decision engine.

> For eventual full automation, replace the free scheduling trigger with an always-on VPS/MT5 EA/dedicated scheduler so ChatGPT is completely outside the timing path.

---

## Operator response rules

| Alert | Required action |
|---|---|
| `TRADE` | Verify account-state gates, then place exactly the supplied direction, 0.01 volume, SL and TP on MT5 mobile |
| `SKIP_RISK` | Do not trade |
| `SKIP_CHASE` | Do not chase; do not trade |
| `SKIP_PORTFOLIO_RISK` | Do not add the blocked position |
| `MOVE_BE` | Move SL to the supplied cost-adjusted breakeven level only |
| `FRIDAY_CLOSE` | Close the stated RFBC position immediately |
| `STALE` | Do not trade from stale data |
| `ERROR` | Do not trade until the monitor is healthy |
| `NONE` | Do nothing |

No discretionary override is permitted.

---

## Live-enable checklist

- [x] USDJPY independently research-qualified
- [x] AUDJPY independently research-qualified
- [x] USDJPYc broker-qualified
- [x] AUDJPYc broker-qualified
- [x] Fresh current account equity captured
- [x] Two-pair deterministic monitor implemented
- [x] Individual 1% risk gate implemented
- [x] Aggregate 1% portfolio gate implemented
- [x] Same-checkpoint conflict handling implemented
- [x] AUDJPY currency conversion implemented
- [x] Breakeven management logic implemented
- [x] Friday-close management logic implemented
- [x] Telegram direct credentials configured
- [x] Direct Telegram delivery received on phone
- [x] Production startup self-test passed
- [x] All required alert types covered by deterministic self-test
- [x] H4 wake/check scheduling expanded to every H4 checkpoint
- [x] Manual journal/review procedure documented
- [x] Daily/weekly/DD operator gate documented for broker-state limitation
- [ ] First naturally occurring live RFBC ticket visually sanity-checked before pressing Buy/Sell

The final unchecked item can only occur when the market generates the first genuine eligible live signal. It is not an engineering blocker and must not be simulated as a real trade.

---

## Current authorization

**RFBC v1.0 is authorized for small manual forward trading on USDJPYc and AUDJPYc only, under the documented tiny-account risk overlay.**

It is **not** authorized for unattended/full-auto order placement yet. That remains a later phase after sufficient forward evidence and a non-ChatGPT critical execution scheduler are available.

---

## Expansion policy

RFBC v1.0 remains frozen. Do not retune it to force more pairs.

Strategy 2 is a separate research track. Future strategies/pairs may be added only after independent validation, broker qualification, portfolio analysis and their own operational readiness review.
