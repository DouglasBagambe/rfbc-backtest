# RFBC USDJPYc Manual Execution Specification

Status: **MANUAL / PHONE EXECUTION ONLY**

This specification operationalizes the frozen RFBC USDJPY v1.0 External Survivor for the Exness Standard Cent symbol `USDJPYc` without changing strategy logic.

Any change to signal logic, entry logic, SL, TP, breakeven, timing, or pair selection creates a new strategy version and requires revalidation.

## Scope

- Trade **USDJPYc only**.
- No EURUSDc, GBPUSDc, or AUDUSDc live/manual execution.
- Execution is manual from the MT5 mobile app.
- No automated order placement yet.
- Fixed trade volume: **0.01**.
- Estimated initial risk must be **<= 1.00% of current equity** or the trade is skipped.
- Do not increase volume above 0.01 to compensate for a narrow stop or small account.

## Broker facts currently confirmed from MT5 mobile

- Symbol: `USDJPYc`
- Digits: 3
- Contract size: 1,000 USD
- Spread: floating
- Stops level: 0
- Minimum volume: 0.01
- Maximum volume: 200
- Volume step: 0.01
- Chart mode: Bid
- Execution: Market Execution
- Swap type: points
- Swap long: 0
- Swap short: -13.2
- Triple swap: Wednesday
- Trading session Friday extends beyond the RFBC 16:00 UTC cutoff, so broker hours do not prevent the frozen Friday exit.

## Frozen signal rules

- D1 EMA50 above EMA200 for longs, below for shorts.
- EMA50 five-completed-D1-bar slope must agree with direction.
- Completed D1 candles only.
- H4 ATR(14).
- Strict breakout of the previous 20 completed H4 bars.
- Signal H4 true range <= 2.0 x signal ATR.
- Eligible H4 signal closes, UTC:
  - Monday-Thursday: 08:00, 12:00, 16:00
  - Friday: 08:00, 12:00
- Entry at the next H4 open.
- Cancel if adverse next-H4 displacement from signal close > 0.20 x signal ATR.
- Initial SL = 1.50 x signal ATR.
- TP = 2.50R.
- Move SL to cost-adjusted breakeven only after a completed H4 close reaches >= +1.50R.
- Flat Friday at 16:00 UTC.

## Manual pre-trade gate

Before every order, all items below must be true:

1. Symbol is exactly `USDJPYc`.
2. Signal comes from the frozen rules above.
3. Signal timestamp is one of the eligible UTC closes.
4. Entry is still the next H4 open; signal is not stale.
5. No-chase test passes.
6. Volume is exactly 0.01.
7. Estimated risk using the proposed SL is <= 1.00% of current equity.
8. Current spread is not obviously abnormal relative to normal observed `USDJPYc` conditions.
9. There is no existing RFBC position already open.
10. It is not after the Friday 16:00 UTC flat cutoff.

If any item fails: **SKIP**.

## Alert / instruction format

Every actionable alert must use this exact structure:

```
RFBC USDJPYc — TRADE
Direction: BUY | SELL
Entry: <price or market at next H4 open>
Volume: 0.01
SL: <price>
TP: <price>
Signal ATR: <value>
Initial risk: <amount and % of equity>
No-chase: PASS
Spread check: PASS
Valid until: <entry-window timestamp UTC>
Reason: frozen RFBC USDJPY v1.0 signal
```

If the setup fails a gate:

```
RFBC USDJPYc — SKIP
Reason: <risk >1% | no-chase failed | stale | abnormal spread | duplicate position | Friday cutoff | other frozen-rule failure>
```

## Position management alerts

When a completed H4 close reaches >= +1.50R:

```
RFBC USDJPYc — MOVE SL TO BE
Position: BUY | SELL
New SL: <cost-adjusted breakeven price>
Reason: completed H4 close >= +1.50R
```

Friday at 16:00 UTC, if a position remains open:

```
RFBC USDJPYc — CLOSE NOW
Reason: frozen Friday 16:00 UTC cutoff
```

After exit:

```
RFBC USDJPYc — CLOSED
Exit reason: TP | SL | BE | FRIDAY
Realized R: <value>
```

## Risk policy for current small account

- 0.01 is the broker minimum and the only permitted live/manual volume for now.
- Target risk is variable because the account is too small to finely size every ATR stop.
- Hard cap: estimated initial risk **must not exceed 1.00% equity**.
- A setup below the cap may be taken even if risk is below 0.50%.
- No trade is enlarged to force a target risk percentage.
- No averaging down, martingale, recovery sizing, or additional RFBC entry while one RFBC position is open.

## Current phase

This document defines execution mechanics only. Automated monitoring/order placement remains a separate later phase. Until then, every order is manually entered from MT5 mobile after a valid alert.
