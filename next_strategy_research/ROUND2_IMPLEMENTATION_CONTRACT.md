# Strategy 2 — Round 2 deterministic implementation contract

**Status:** REJECTED — implementation retained for archival reproducibility
**Date:** 10 September 2026
**Scope:** S2R2-01 to S2R2-12; internal Dukascopy BID/ASK data from 2013 through 2020 only. RFBC v1.0 is unchanged.

> **DECISION:** Round 2 is closed as rejected. The completed screen is retained
> as immutable archival evidence and the fidelity-corrected implementation is
> retained for reproducibility. No threshold, gate, universe, date split or
> strategy mechanism was selected from its results.

---

## Common state, chronology and execution

| Item | Frozen implementation |
|---|---|
| Time | All source indexes and state timestamps are UTC-aware. M15 `T` is completed information; any order enters at next-M15 `T+1`. |
| ATR | Wilder ATR/RMA(14). Signal M15 ATR includes the completed signal M15; H1 ATR is attached only after its H1 candle completes. Non-finite or non-positive ATR/risk signals are invalid. |
| H1 state | Aligned long: EMA20 > EMA50. Aligned short: EMA20 < EMA50. Neutral: `abs(EMA20-EMA50) <= 0.20 × H1 ATR(14)`; the neutral band takes precedence. |
| D1/session baselines | Prior D1 is the immediately preceding completed UTC D1. All 20-day medians use the preceding 20 completed UTC trading days, excluding current day. Same-window volume/range uses the identical UTC window. |
| Cross-pair data | Fixed members, inner-joined completed H1 timestamps, own-pair H1 ATR normalization, no forward-fill. Missing member data invalidates that basket timestamp. |
| Execution | Long: next ASK open + 0.10 pip; exits: BID less 0.10 pip. Short: next BID open - 0.10 pip; exits: ASK plus 0.10 pip. Stop = 1.25× M15 ATR; target = 1.50R; max hold = 24 M15 bars; same-bar SL/TP is stop-first. No new signal after Friday 15:45 UTC; Friday 16:00 UTC is forced exit. |

---

## Frozen hypotheses

| ID | Exact deterministic rule |
|---|---|
| S2R2-01 | **05:00–06:45 UTC; H1 neutral.** Previous completed M15 close is at least 0.75 previous-M15 ATR below/above the prior D1 close. The current completed M15 closes through that previous close toward the prior D1 close: long from below, short from above. Wicks are not substitutes. |
| S2R2-02 | **14:00–15:45 UTC.** Pre-signal realized UTC-day range is at least 1.25× trailing 20-day daily-range median. The signal bar sweeps the London-so-far high/low (07:00 through preceding M15) and closes back inside it. |
| S2R2-03 | The completed 13:00–14:00 H1 body is at least 0.90 H1 ATR, dominant wick share is at most 0.25, and its direction is H1-trend aligned. After availability, the first M15 close entering the 25–50% retracement zone arms it. A close through the H1 impulse extreme cancels before entry. A later completed M15 close through the **preceding M15 high/low** triggers in the impulse direction. First sequence only, per UTC day. |
| S2R2-04 | **14:00–15:30 UTC.** Every completed M15 close from 07:00 through current and from 12:00 through current is on the same side of the prior D1 close. Current close breaks the preceding four completed M15 highs/lows in that direction. |
| S2R2-05 | Freeze the 07:00–09:00 range. It must be at most 0.80× preceding-20-day same-window median. From 09:00–10:45, the first sweep-and-close-inside of one frozen boundary arms that boundary; a later distinct sweep-and-close-inside of the same boundary fades it. |
| S2R2-06 | **10:00–12:45 UTC.** Pre-signal day range is at most 0.55× trailing 20-day daily-range median; M15 closes outside prior D1 high/low with aligned H1 trend. There is no cross-pair breadth filter. |
| S2R2-07 | USD basket members: EURUSD, GBPUSD, AUDUSD, NZDUSD (inverted), USDJPY, USDCAD, USDCHF (direct). Median oriented normalized H1 return is at least +1.00 or at most -1.00 and at least three members share that sign. Select one agreeing member: greatest absolute normalized return, lexical tie-break. Strength sells inverted/direct-quote pairs and buys USD-base pairs; weakness reverses it. One selected trade candidate per completed basket H1 timestamp. |
| S2R2-08 | JPY basket members: EURJPY, GBPJPY, AUDJPY, CADJPY, CHFJPY. The pre-data register froze only the JPY-strength risk-off side: basket median normalized return <= -0.75 and at least three members negative. Select the greatest-absolute negative member, lexical tie-break. Its first M15 continuation close below preceding M15 low while that H1 state remains active is short. This continuation condition is from the pre-data register. |
| S2R2-09 | Universe is exactly EURUSD, GBPUSD, AUDUSD, NZDUSD. Candidate H1 normalized open-to-close return less median of the other three equals residual. Residual >= +1.50 seeks short; <= -1.50 seeks long. Only the immediately following completed M15 may close through that H1 impulse midpoint. |
| S2R2-10 | Asia is 00:00 opening price through 06:45 close/high/low/volume. Its 06:45-close minus 00:00-open, divided by current H1 ATR, has absolute value >=0.80 and volume is <= prior-20-day same-window median. During 07:00–08:30, a positive move sweeps/fails Asia high for short; a negative move sweeps/fails Asia low for long. |
| S2R2-11 | Freeze day open to the first new intraday extreme making day range >=0.90× trailing 20-day daily median while H1 trend is aligned. During 10:00–14:45 only the first subsequent 38.2–61.8% retracement is eligible and it must close in reclaim/trend direction. |
| S2R2-12 | Friday 13:00–15:45 UTC. Three preceding completed M15 closes are strictly monotonic; none made a new current-week extreme relative to data available before it. Bar four closes through bar three midpoint in the opposite direction. |

---

## Promotion gate

Development expectancy >= +0.10R; development PF >= 1.15; validation expectancy >= +0.05R; validation PF >= 1.10; at least 120 combined trades; and positive expectancy in at least 8 of 15 pairs. The 2021+ holdout and HistData remain sealed unless this gate passes.
