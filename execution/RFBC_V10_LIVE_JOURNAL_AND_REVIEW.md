# RFBC v1.0 Live Journal and Review Procedure

## Purpose

The first live phase is a forward-execution validation of the already frozen RFBC v1.0 system. It is not a new optimization cycle.

The journal exists to answer four questions:

1. Did the live signal exactly match frozen RFBC logic?
2. Did the broker/manual execution match the intended order?
3. Did realized costs materially differ from assumptions?
4. Is live behavior still consistent with the independently validated distribution?

## What to record for every checkpoint

For every eligible RFBC H4 checkpoint, save:

- UTC checkpoint time
- symbol
- signal state: none / long / short
- latest completed H4 timestamp
- D1 regime state
- signal ATR
- signal close
- breakout threshold
- current Bid and Ask used by the execution layer
- chase displacement and 0.20 ATR threshold
- proposed 0.01-volume entry, SL and TP
- estimated monetary risk and account-risk percentage
- aggregate open RFBC risk before the decision
- daily and weekly loss-stop state
- current high-water-mark drawdown
- final action: `NONE`, `TRADE`, or exact skip reason

## What to record for every executed trade

At entry:

- symbol
- direction
- signal timestamp UTC
- order timestamp UTC
- requested entry
- actual fill
- entry slippage
- volume
- SL
- TP
- actual spread at/near entry
- account equity before entry
- estimated initial risk USD/account currency
- estimated initial risk %
- whether another RFBC position was already open

During management:

- every completed H4 close while the trade is open
- whether +1.50R breakeven condition was met
- time and value of any cost-adjusted BE move
- any alert delay or missed alert
- any manual/broker issue

At exit:

- exit timestamp UTC
- exit reason: SL / TP / BE / FRIDAY / other broker emergency
- requested vs actual exit if applicable
- realized P/L
- realized R
- spread/slippage notes
- swap/commission if any
- account equity after exit
- updated daily/weekly loss state
- updated high-water-mark drawdown

## Non-negotiable classification

Every discrepancy must be classified as one of:

- `STRATEGY_MATCH`
- `DATA_FEED_DIFFERENCE`
- `BROKER_EXECUTION_DIFFERENCE`
- `ALERT_DELIVERY_FAILURE`
- `MANUAL_EXECUTION_ERROR`
- `SOFTWARE_BUG`
- `UNEXPLAINED`

Do not hide or retroactively rewrite bad live outcomes.

## Review cadence

### After every trade

Perform a short execution audit. This is operational only; do not tune RFBC.

### Weekly

Review:

- number of valid signals
- number taken
- skip reasons
- realized R
- average spread and slippage
- maximum simultaneous exposure
- alert reliability
- any missed Friday/BE action
- daily/weekly stop events
- drawdown from live high-water mark

### First formal forward review

Do not make performance conclusions from a handful of trades. The first formal review should occur only after either:

- at least 30 completed live/forward RFBC trades across the enabled pair set, or
- six months of forward operation,

whichever comes first.

The review compares execution quality and distribution drift. It does not automatically authorize strategy retuning.

## Pause conditions

Pause new entries immediately for operational review if any of the following occurs:

- data timestamps are stale or malformed;
- the monitor generates a signal inconsistent with frozen RFBC logic;
- SL/TP/BE calculations differ materially from the frozen specification;
- the broker rejects normal RFBC protection levels;
- two or more meaningful alert-delivery failures occur around eligible checkpoints;
- a software bug affects a live decision;
- the 5.00% hard-kill drawdown is reached.

## Relationship to Strategy 2 research

Separate strategy research may run while RFBC is forward-traded, but RFBC live rules remain frozen. Findings from Strategy 2 must never be back-injected into RFBC v1.0 without creating a separately named/versioned strategy and validating it independently.
