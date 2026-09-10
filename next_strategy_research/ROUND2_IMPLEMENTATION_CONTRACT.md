# Strategy 2 — Round 2 deterministic implementation contract

**Status:** APPROVED FOR IMPLEMENTATION; NOT YET APPROVED FOR FULL SCREEN  
**Approval:** 10 September 2026  
**Scope:** S2R2-01 through S2R2-12, internal 2013–2020 Dukascopy BID/ASK only. RFBC v1.0 is unchanged.

This document makes the frozen Round 2 prose mechanically testable. These are implementation definitions, not performance-led tuning. They must not be changed after seeing results; any strategic change creates a new round/version.

## Common chronology and execution

- A source M15 row at `T` is the completed signal bar; entry is the next M15 row open.
- Completed H1 state is available only at its timestamp + 1 hour. Completed D1 state is available only at its timestamp + 1 UTC day.
- All trailing medians, ATRs, ranges and volume baselines use only completed prior observations. Missing basket members invalidate the synchronized H1 timestamp; nothing is forward-filled across a missing component bar.
- Long entry = next ASK open + 0.10 pip. Short entry = next BID open - 0.10 pip. Long exits use BID - 0.10 pip; short exits use ASK + 0.10 pip.
- Stop = 1.25 × signal M15 ATR(14), target = 1.50R, maximum hold = 24 M15 bars, Friday 16:00 UTC forced exit. Same-bar stop/target conflicts resolve stop-first.
- One active trade per pair/hypothesis. No averaging, martingale, grid, stop widening or discretionary override.

## State definitions

- **H1 trend:** +1 when completed H1 close > EMA20 > EMA50, -1 when close < EMA20 < EMA50, otherwise 0/neutral.
- **20-day median range:** median of the preceding 20 completed UTC D1 high-low ranges.
- **Same-window 20-day median:** median of the same fixed UTC window over the preceding 20 completed days.
- **USD basket normalized return:** completed H1 open-to-close divided by that pair's completed H1 ATR(14), oriented so positive means USD strength. EURUSD/GBPUSD/AUDUSD/NZDUSD are inverted; USDJPY/USDCAD/USDCHF are not.
- **JPY basket normalized return:** completed H1 open-to-close / H1 ATR, inverted so positive means JPY strength for EURJPY/GBPJPY/AUDJPY/CADJPY/CHFJPY.
- **Correlation-dislocation basket:** median normalized H1 return of the predeclared 15-pair members sharing either currency with the candidate, excluding the candidate itself. The residual is candidate normalized H1 return minus that median.

## Hypothesis mechanics

1. **S2R2-01:** 05:00–06:45 UTC. Neutral H1. Signal only after an M15 excursion beyond prior D1 close ±0.75 signal ATR closes back through that extension boundary in the reversion direction.
2. **S2R2-02:** 14:00–15:45 UTC. Pre-signal realized day range >=1.25× trailing 20-day median. London extreme is the expanding 07:00-to-prior-M15 high/low. Signal bar makes a fresh excursion and closes back inside.
3. **S2R2-03:** The H1 bar beginning 13:00 UTC defines the NY drive and becomes available at 14:00. Body >=0.90 H1 ATR, dominant wick share <=0.25, direction aligned with H1 trend. Freeze its open/high/low/close. The first M15 close retracing 25–50% of its open-to-close impulse arms the setup; a later completed M15 close through the frozen H1 extreme triggers continuation. Only the first armed sequence per UTC day is eligible.
4. **S2R2-04:** 14:00–15:30 UTC. Completed London-so-far and NY-so-far closes must have remained on the same side of prior D1 close. Trigger is a completed M15 close through the preceding four completed M15 highs/lows in that common direction.
5. **S2R2-05:** Freeze the 07:00–09:00 UTC range after 09:00. It must be <=0.80× the preceding-20-day median of that same window. A first excursion through an edge arms that edge; a later distinct excursion through the same edge that closes back inside triggers the fade.
6. **S2R2-06:** 10:00–12:45 UTC. Pre-signal realized day range <=0.55× trailing 20-day median; M15 closes outside prior D1 high/low with aligned H1 trend. Broad participation must be directionally consistent in a predeclared USD or JPY basket; pairs outside those baskets are ineligible for this family rather than receiving an invented proxy.
7. **S2R2-07:** On a completed synchronized H1 boundary, at least three USD-basket members must show oriented USD strength >=+1.00 ATR. Only the seven predeclared USD majors are eligible; signal direction follows USD strength. One signal evaluation per completed H1 boundary.
8. **S2R2-08:** At least three JPY-basket members must show oriented JPY strength >=+0.75 ATR. Eligible JPY cross then requires a completed M15 continuation close below the immediately preceding completed M15 low. Direction is short the cross. First qualifying break while that completed-H1 basket state remains active is eligible.
9. **S2R2-09:** Completed H1 residual >=+1.50 seeks short; <=-1.50 seeks long. Freeze that H1 open/close midpoint. Only the immediately following completed M15 may qualify by closing back through 50% of the frozen impulse.
10. **S2R2-10:** Freeze Asia 00:00 open, 06:45 close, high, low and total volume. Normalized 06:45-close minus 00:00-open must have absolute value >=0.80 H1 ATR; volume <= prior-20-day same-window median. During 07:00–08:30, positive Asia move must fail/reclaim Asia high for short; negative move must fail/reclaim Asia low for long.
11. **S2R2-11:** UTC-day open is fixed. Freeze the first intraday extreme that takes realized day range to >=0.90× trailing 20-day median while H1 trend aligns with the impulse direction. Only the first subsequent entrance into the 38.2–61.8% retracement zone is eligible; it must close in the trend/reclaim direction.
12. **S2R2-12:** Friday 13:00–15:00 UTC. Bars 1–3 have strictly monotonic closes and none of those bars creates a new current-week high or low relative to information available before each bar. Bar 4 must close through bar 3 midpoint in the opposite direction.

## Preliminary promotion gate

A hypothesis may enter parameter-neighborhood work only if all are true across the predeclared universe:

- development expectancy >= +0.10R;
- development PF >= 1.15;
- validation expectancy >= +0.05R;
- validation PF >= 1.10;
- development + validation trades >= 120;
- positive expectancy in at least 8 of 15 pairs.

The 2021+ holdout and HistData external set remain sealed until a candidate passes this gate and the deterministic test suite passes.
