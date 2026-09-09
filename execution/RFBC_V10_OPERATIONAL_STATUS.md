# RFBC v1.0 Operational Status

> **Research status:** QUALIFIED  
> **Broker status:** USDJPYc + AUDJPYc QUALIFIED  
> **Live status:** FINAL END-TO-END TESTING PENDING

---

## Research-qualified set

RFBC v1.0 is research-qualified only on:

- **USDJPY**
- **AUDJPY**

All other tested pairs are rejected for RFBC v1.0.

## Broker/live readiness

### USDJPYc

Status: **BROKER-QUALIFIED** for the current Exness Standard Cent setup.

Known properties include:

- symbol: `USDJPYc`
- contract size: 1,000 USD
- minimum volume: 0.01
- volume step: 0.01
- digits: 3
- stops level: 0

Manual specification: `execution/RFBC_USDJPYC_MANUAL_EXECUTION_SPEC.md`.

### AUDJPYc

Status: **BROKER-QUALIFIED** from MT5 mobile evidence captured 9 September 2026.

Key verified properties:

- symbol: `AUDJPYc`
- contract size: 1,000 AUD
- minimum volume: 0.01
- volume step: 0.01
- digits: 3
- floating spread; observed about 1.1 pips
- stops level: 0
- swap long: -0.2 points
- swap short: -2.1 points
- triple swap: Wednesday
- Friday session through 20:59
- chart mode: Bid

Detailed evidence: `execution/RFBC_AUDJPYC_BROKER_VALIDATION_CHECKLIST.md` and `broker_validation/output/audjpyc_symbol_properties.json`.

## Current account state

Fresh account snapshot captured 9 September 2026:

- balance: **1,001 USC**
- equity: **1,001 USC**
- USD-equivalent equity used for risk calculations: **$10.01**
- open positions at snapshot: none

`RFBC_EQUITY_USD=10.01` is the current configured value. It must be refreshed after closed trades and whenever account equity materially changes.

## Portfolio execution rule

Authoritative overlay: `execution/RFBC_V10_PORTFOLIO_RISK_OVERLAY.md`.

Current small-account controls:

| Control | Rule |
|---|---:|
| Live volume | 0.01 maximum per position |
| Individual entry risk | <= 1.00% |
| Aggregate initial open risk | <= 1.00% |
| Same-checkpoint conflict | lower estimated risk first |
| Exact-risk tie | USDJPYc deterministic tie-break |
| Daily new-entry stop | -1.00% realized RFBC loss |
| Weekly new-entry stop | -2.00% realized RFBC loss |
| DD warning | 3.00% below closed-balance HWM |
| Hard kill | 5.00% below closed-balance HWM |

Both qualified pairs contain JPY, so aggregate risk control remains mandatory despite low historical return/drawdown correlation.

## Monitoring implementation

Two-pair deterministic monitor is now implemented in:

- `monitor/rfbc_monitor_multi.py`
- `monitor/webapp.py`
- `monitor/test_rfbc_monitor_multi.py`

The monitor:

- evaluates `USDJPYc` and `AUDJPYc` using the frozen RFBC v1.0 logic;
- uses Dukascopy BID/ASK data;
- calculates 0.01-volume monetary/account risk using fresh configured equity;
- converts AUDJPY JPY P/L through current USDJPY for account-currency risk;
- applies the 1.00% individual risk cap;
- applies the 1.00% aggregate initial-risk cap;
- resolves same-checkpoint conflicts deterministically;
- emits `TRADE`, `SKIP_RISK`, `SKIP_CHASE`, `SKIP_PORTFOLIO_RISK`, `MOVE_BE`, `FRIDAY_CLOSE`, `STALE`, `ERROR`, or `NONE`.

> **Important:** automated daily/weekly/high-water-mark state must not be fabricated from hypothetical fills. Those controls remain authoritative operational rules, but full automation requires reliable execution-state feedback from actual trades.

## Alert architecture

Preferred final path:

```text
Dukascopy -> deterministic RFBC monitor -> direct Telegram -> manual MT5 mobile
                                      \
                                       -> ChatGPT oversight/diagnostics
```

ChatGPT is deliberately outside the critical execution/alert path.

Direct Render-to-Telegram delivery requires `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` secrets on the monitor service. Until direct delivery is configured and tested, alert reliability is **not yet considered production-ready**.

## Live-enable checklist

- [x] USDJPY research-qualified
- [x] AUDJPY research-qualified
- [x] USDJPYc broker-qualified
- [x] AUDJPYc broker-qualified
- [x] Fresh account equity captured and configured
- [x] Deterministic two-pair monitor implemented
- [x] Individual risk calculation implemented
- [x] Simultaneous/aggregate risk gate implemented
- [x] Multi-pair risk unit tests added
- [ ] Latest two-pair monitor deploy verified live on Render
- [ ] `/health` and `/check` verified end to end after deploy
- [ ] Direct Telegram secrets configured
- [ ] Direct Telegram test alert received on phone
- [ ] `MOVE_BE` management path tested end to end
- [ ] `FRIDAY_CLOSE` management path tested end to end
- [ ] First real manual ticket sanity-checked before submission
- [ ] Daily/weekly/DD state feedback path finalized before relying on automated account-state alerts

## Expansion policy

RFBC v1.0 remains frozen. Do not retune it to force more pairs.

Strategy 2 research is a separate evidence chain and may proceed in parallel. Any future strategy or pair expansion must pass its own independent validation and portfolio checks before live use.
