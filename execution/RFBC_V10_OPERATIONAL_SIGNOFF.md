# RFBC v1.0 Operational Sign-off

> **Status:** LIVE-READY FOR SMALL MANUAL FORWARD TRADING  
> **Symbols:** `USDJPYc`, `AUDJPYc`  
> **Execution:** Telegram alert -> manual MT5 mobile  
> **Signed off:** 9 September 2026

---

## Final decision

RFBC v1.0 is authorized for **small manual forward trading** on `USDJPYc` and `AUDJPYc` only, under the frozen strategy rules and documented tiny-account execution overlay.

This sign-off does **not** authorize unattended/full-auto order placement.

---

## Production verification

| Item | Result |
|---|---|
| Independent research validation | PASS |
| USDJPYc broker qualification | PASS |
| AUDJPYc broker qualification | PASS |
| Fresh account equity | PASS - $10.01 / 1,001 USC |
| 0.01 volume sizing | PASS |
| Individual risk cap <=1% | PASS |
| Aggregate initial open-risk cap <=1% | PASS |
| Same-checkpoint conflict handling | PASS |
| AUDJPY -> USD risk conversion | PASS |
| No-chase rule | PASS |
| MOVE_BE checkpoint handling | PASS |
| Friday 16:00 UTC close handling | PASS |
| Direct Render -> Telegram delivery | PASS - received on phone |
| Startup fail-closed decision-path self-test | PASS |
| H4 wake/check cadence | PASS - every completed H4 checkpoint |
| Journal / review procedure | PASS |
| Formal validation + live operations documentation | PASS |

---

## Production revision

Production monitor revision verified on Render:

`98dfafa19af408631210518ef6a6ee3a1d050efd`

Render deploy:

`dep-dagpdn5g1s2s73f8j3m0`

Startup self-test returned `ok: True` and explicitly passed:

- `TRADE`
- `SKIP_RISK`
- `SKIP_CHASE`
- `SKIP_PORTFOLIO_RISK`
- existing-open-risk blocking
- `MOVE_BE`
- `FRIDAY_CLOSE`
- `STALE`
- operator-facing alert formatting

The production wrapper `monitor/rfbc_monitor_live.py` corrects the breakeven notification edge case so `MOVE_BE` is emitted exactly on the first completed H4 close that reaches the frozen +1.50R threshold, without repeated later alerts.

---

## Live operator obligations

Because the current phase uses manual MT5 mobile execution and the monitor has no authenticated broker-account API, the operator must continue to verify actual account-state controls before every entry:

- daily realized RFBC loss < 1%;
- weekly realized RFBC loss < 2%;
- closed-balance drawdown below the 3% review threshold and 5% hard-kill threshold;
- Render equity input remains materially current after closed trades, deposits or withdrawals.

This is an explicit manual-forward limitation, not missing strategy logic.

---

## Fail-closed rule

If the alert is `SKIP_RISK`, `SKIP_CHASE`, `SKIP_PORTFOLIO_RISK`, `STALE`, or `ERROR`, **do not trade**.

If the alert path is unavailable or account state is uncertain, **do not trade**.

No discretionary override is permitted.

---

## Remaining natural-market checkpoint

The first naturally occurring live `TRADE` ticket should be visually sanity-checked against MT5 before pressing Buy/Sell. This cannot be completed before a genuine eligible market signal exists and is not an engineering blocker.

After that first ticket, normal forward evidence collection continues under `execution/RFBC_V10_LIVE_JOURNAL_AND_REVIEW.md`.

---

## Authorization boundary

**Authorized now:** small manual forward trading on `USDJPYc` + `AUDJPYc` only.

**Not authorized now:** full-auto execution, higher volume, additional RFBC pairs, retuned RFBC rules, martingale/grid/averaging, or discretionary overrides.

Future automation should move timing and order placement to an MT5 EA/VPS/dedicated scheduler so ChatGPT is not in the critical execution path.
