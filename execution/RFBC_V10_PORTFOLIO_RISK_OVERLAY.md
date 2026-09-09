# RFBC v1.0 Portfolio Risk Overlay

## Scope

This document defines the live-account risk controls applied on top of frozen RFBC v1.0 signals for the validated pair set:

- USDJPYc
- AUDJPYc, once broker-qualified

These controls do not change RFBC signal generation, entry timing, stop distance, target distance, breakeven logic, or Friday-flat logic. They decide only whether an otherwise valid broker-executable trade may be taken on the current account.

## Current small-account mode

The current Exness Standard Cent account is constrained by the broker minimum volume of 0.01. Because exact 0.50% sizing is often impossible at that granularity, the execution layer uses the following rules:

1. Volume is fixed at 0.01 while this small-account mode is active.
2. Never increase above 0.01 in order to reach a target risk percentage.
3. Calculate actual account risk from current equity, executable entry, RFBC stop distance, contract size, and symbol conversion before every order.
4. A single trade is rejected if estimated initial account risk exceeds 1.00%.
5. Account equity must be refreshed after every closed trade and before sizing a new trade after any balance/equity change.

The long-run target remains approximately 0.50% risk per trade when account size and broker volume granularity make that possible.

## Aggregate open-risk cap

While operating the current small account, total initial risk across all simultaneously open RFBC positions must not exceed 1.00% of current account equity.

Therefore:

- if no RFBC position is open, an otherwise valid trade may be taken if its estimated risk is <= 1.00%;
- if one RFBC position is already open, a second signal may be taken only if the sum of remaining initial risk on the open position plus initial risk on the new position is <= 1.00%;
- if the broker minimum volume makes that impossible, the later trade is skipped;
- once an existing position has been moved to cost-adjusted breakeven, its remaining initial-risk contribution is treated as approximately zero for this portfolio gate, although gap/slippage risk still exists.

This conservative cap prevents two individually acceptable 1% JPY positions from creating an unintended 2% initial-risk event.

## Simultaneous-signal ordering

If USDJPYc and AUDJPYc produce eligible signals at different times, process them chronologically. The earlier executable signal consumes portfolio risk first.

If both produce executable signals at the same RFBC checkpoint:

1. calculate actual risk for both at 0.01 volume;
2. if both together fit under the 1.00% aggregate open-risk cap, both may be taken;
3. otherwise take only the signal with the lower estimated account-risk percentage;
4. if estimated risk is effectively equal, prefer USDJPYc as the deterministic tie-break because it was the first independently validated external survivor;
5. mark the other valid signal `SKIP_PORTFOLIO_RISK`.

The skipped signal is not chased later. RFBC has no delayed-entry substitution rule.

## Daily and weekly loss stops

Risk controls are measured from equity reference points and include realized trading P/L for RFBC activity.

### Daily stop

- Daily reference equity: account equity at 00:00 UTC or, if unavailable, the first verified equity snapshot before the day's first RFBC action.
- If realized RFBC loss for the UTC day reaches or exceeds 1.00% of that reference equity, take no new RFBC entries until the next UTC day.
- Existing positions continue to follow their frozen SL/TP/breakeven/Friday-close rules. Do not close them merely because the daily new-entry stop was reached unless another hard-risk rule below requires intervention.

### Weekly stop

- Weekly reference equity: account equity at the start of Monday UTC or the first verified equity snapshot before that week's first RFBC action.
- If realized RFBC loss for the week reaches or exceeds 2.00% of that reference equity, take no new RFBC entries until the next Monday UTC.
- Existing positions remain managed by the frozen strategy rules unless the hard kill below is triggered.

## Drawdown controls

Track drawdown from the highest verified account equity since live RFBC forward execution began.

### 3.00% drawdown warning

At >= 3.00% drawdown from the live high-water mark:

- send a `DRAWDOWN_WARNING` alert;
- do not increase volume or loosen any risk limit;
- keep small-account volume fixed at 0.01;
- perform an operational review of broker fills, missed alerts, data freshness, and live-vs-validated behavior before continuing new entries.

This is a warning/review threshold, not a strategy retuning trigger.

### 5.00% hard kill

At >= 5.00% drawdown from the live high-water mark:

- disable all new RFBC entries;
- send a `HARD_KILL` alert;
- manage already-open positions only according to their existing protective stops and mandatory Friday close unless emergency broker/account conditions require manual risk reduction;
- do not resume live RFBC trading until the cause is reviewed and the system is explicitly re-enabled.

Do not modify RFBC parameters to recover from the drawdown.

## Prohibited execution behavior

The live overlay forbids:

- averaging down;
- adding to a losing position;
- pyramiding beyond the original validated trade;
- widening RFBC stops;
- removing a stop;
- discretionary take-profit changes;
- chasing a canceled or portfolio-skipped entry;
- carrying positions past the frozen Friday close;
- increasing size after losses;
- overriding `SKIP_RISK`, `SKIP_CHASE`, `SKIP_PORTFOLIO_RISK`, daily-stop, weekly-stop, or hard-kill states.

## Required alert states

The operational monitor should eventually be able to emit at least:

- `TRADE`
- `NONE`
- `SKIP_RISK`
- `SKIP_CHASE`
- `SKIP_PORTFOLIO_RISK`
- `MOVE_BE`
- `FRIDAY_CLOSE`
- `DAILY_STOP`
- `WEEKLY_STOP`
- `DRAWDOWN_WARNING`
- `HARD_KILL`
- `STALE`
- `ERROR`

## Reassessment

This execution overlay may be revised when account size materially increases, but any revision must remain separate from frozen RFBC signal logic and should be documented before being used live.
