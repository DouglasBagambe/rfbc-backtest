# Strategy 2 — Round 3 ICT-primitives hypothesis register

**Status:** FROZEN FOR REVIEW — not implemented, not screened
**Date:** 10 September 2026
**Scope:** 10 deterministic M15/H1 hypotheses on the predefined 15-pair universe. RFBC v1.0 is unchanged.

> **DECISION:** This is a new preregistration, designed without reading new Round 3 performance. It is not a retune or continuation of either rejected earlier round. No implementation or screen may begin until this register is approved.

---

## Research boundary and common execution

| Control | Frozen definition |
|---|---|
| Data and dates | Validated Dukascopy BID/ASK M15 and derived H1 bars. Development: 2013-01-01 through 2017-12-31. Validation: 2018-01-01 through 2020-12-31. Reader excludes timestamps from 2021-01-01 onward before any feature construction. |
| Universe | EURUSD, GBPUSD, USDJPY, AUDUSD, NZDUSD, USDCAD, USDCHF, EURJPY, GBPJPY, AUDJPY, CADJPY, CHFJPY, EURGBP, EURAUD, GBPAUD. No pair-specific parameters. |
| Signal/execution | Signal is a completed BID M15 close at `T`; entry is next M15 ASK open +0.10 pip for long or BID open -0.10 pip for short. Long exit prices use BID -0.10 pip; short exit prices use ASK +0.10 pip. |
| Risk | Wilder M15 ATR(14) at `T`; stop is 1.25 ATR; target is 1.50R; maximum hold is 24 M15 bars; Friday 16:00 UTC forced exit; stop-first when both stop and target are executable in one M15 bar. Non-finite/non-positive ATR invalidates signal. |
| Position control | One active trade per pair/hypothesis. A setup id permits at most one signal. No martingale, grid, averaging, recovery sizing, stop widening, time-zone conversion or discretionary override. |
| H1 context | `trend_up = EMA20 > EMA50` and `trend_down = EMA20 < EMA50`, calculated on completed BID H1. H1 state becomes usable one hour after its source timestamp. |
| UTC windows | London kill zone: 07:00–10:45; New York kill zone: 13:00–15:45. Asia range: 00:00–06:45. All endpoints are completed M15 timestamps. |

## Shared objective primitives

| Primitive | Exact definition |
|---|---|
| Four-bar structure break (MSS) | Bullish at `T` if `close[T] > max(high[T-4:T-1])`; bearish if `close[T] < min(low[T-4:T-1])`. It uses only preceding bars and the completed signal close. |
| Fair value gap (FVG) | Bullish FVG formed at completed `T` when `low[T] > high[T-2]`; zone `[high[T-2], low[T]]`. Bearish FVG when `high[T] < low[T-2]`; zone `[high[T], low[T-2]]`. A later mitigation bar touches the zone and closes in the FVG direction: bullish `low <= zone_high` and `close > open`; bearish `high >= zone_low` and `close < open`. |
| Sweep/reclaim | A bar sweeps a defined high if `high > level` and reclaims it if `close <= level`; mirrors for a low: `low < level` and `close >= level`. Wick excursion is explicit only here. |
| Prior-day premium/discount | Prior completed D1 midpoint is `(high + low)/2`. Discount means `close <= midpoint`; premium means `close >= midpoint`. |
| Order block (OB) | Immediately before a qualifying MSS, the OB is the latest opposite-colour completed M15 candle among the four bars preceding the MSS. Its zone is full high-to-low range. A retest touches its zone and closes in MSS direction. |
| Breaker block | A qualified OB is invalidated when a later completed close passes its far edge against MSS direction. Its full range becomes breaker zone. A subsequent retest that touches it and closes in the invalidation direction is the breaker event. |
| OTE | For an accepted directional impulse from `A` to `B`, retracement zone is 62.0%–79.0% of `abs(B-A)`, measured from `B` toward `A`. A completed M15 must touch the zone and close back in impulse direction. |
| SMT pair set | Fixed comparison pairs only: EURUSD/GBPUSD, AUDUSD/NZDUSD and EURJPY/GBPJPY. No dynamic correlation selection. |

---

## Frozen hypotheses

| ID / family | Exact signal, direction and context | Session, entry, invalidation and suppression |
|---|---|---|
| S2R3-01 — H1-aligned FVG mitigation | In H1 trend-up/down, form a same-direction M15 FVG during the window. The first later M15 mitigation of that exact zone, closing in FVG direction, signals long/short. | London or NY kill zone. Entry next M15. Invalidate if a completed close crosses the FVG far edge before first mitigation. One trade per FVG. |
| S2R3-02 — Asia liquidity sweep plus MSS reversal | After Asia range is fully known, sweep/reclaim Asia high then a later bearish MSS signals short; sweep/reclaim Asia low then later bullish MSS signals long. | London kill zone only. MSS must occur after the reclaim and before 10:45. Invalidate if price closes beyond the swept extreme before MSS. One trade per Asia boundary/day. |
| S2R3-03 — MSS order-block retest continuation | A bullish/bearish MSS in H1 trend direction defines its preceding opposite-colour OB. The first later retest touching OB and closing back in MSS direction signals. | London or NY kill zone. Invalidate on completed close through OB far edge before retest. One trade per defining MSS/OB. |
| S2R3-04 — Failed OB breaker reversal | A valid S2R3-03 OB is first invalidated by a close through its far edge. The first later touch-and-close-in-invalidation-direction of that same OB range signals the reversal. | London or NY kill zone. Invalidate if price closes through the breaker far edge before retest. One trade per invalidated OB. |
| S2R3-05 — Prior-day premium/discount liquidity reversal | In premium, sweep/reclaim prior D1 high followed by bearish MSS signals short. In discount, sweep/reclaim prior D1 low followed by bullish MSS signals long. | London or NY kill zone. MSS follows reclaim; invalidate on close past sweep extreme before MSS. One trade per prior-day boundary/day. |
| S2R3-06 — OTE after session MSS continuation | A H1-trend-aligned MSS during a kill zone defines impulse `A`: lowest predecessor-four low for long / highest predecessor-four high for short; `B`: MSS-bar high for long / low for short. First later OTE-zone touch that closes in MSS direction signals continuation. | London or NY kill zone. Invalidate if close crosses `A` before OTE entry. One trade per defining MSS. |
| S2R3-07 — SMT divergence plus sweep/MSS reversal | For either fixed SMT pair, one pair sweeps its Asia high/low while the peer does not exceed its corresponding Asia level. Trade only the sweeping pair after reclaim and opposite-direction MSS. If both qualify, greatest absolute sweep distance divided by M15 ATR wins; exact tie uses lexical pair name. | London kill zone. Invalidate at sweep extreme close before MSS. One trade per fixed pair-group, boundary and UTC day. |
| S2R3-08 — New York FVG after London range run | London range is 07:00–12:45. In NY kill zone, a bar closes beyond its high/low, then forms a same-direction FVG; first mitigation that closes in breakout direction signals. | NY kill zone only. Invalidate if close returns through the opposite London boundary before mitigation. One trade per London boundary/day. |
| S2R3-09 — Asia range run continuation | After 07:00, a completed close breaks Asia high/low in H1 trend direction. The first same-direction FVG formed after that break and first mitigation closing in direction signal continuation. | London kill zone only. Invalidate if close crosses the opposite Asia boundary before entry. One trade per Asia boundary/day. |
| S2R3-10 — Prior-day midpoint displacement/reclaim | In H1 trend-up/down and corresponding discount/premium, a completed M15 MSS crosses the prior D1 midpoint in trend direction. First later retest of midpoint that touches it and closes back in trend direction signals continuation. | London or NY kill zone. Invalidate on completed close through the midpoint opposite the trend after MSS and before retest. One trade per midpoint-crossing MSS/day. |

---

## Screening and promotion

The existing frozen preliminary gate in `M15_SCREEN_GATE.md` remains unchanged. Round 3 must additionally satisfy the existing Round 2 breadth condition: positive expectancy in at least 8 of 15 pairs. Only a passing frozen finalist may enter bounded neighborhood testing, one untouched 2021+ holdout pass, and HistData Generic ASCII Tick BID/ASK external validation.

## Implementation plan

1. Create an isolated `round3_*` engine; do not modify Round 2 code or results.
2. Build UTC-aware primitive/state constructors with setup IDs and per-setup duplicate suppression.
3. Write deterministic synthetic tests for every primitive, session endpoint, BID/ASK path, stop-first case and duplicate rule.
4. Run static/lookahead audit and fast tests before any broad screen.
5. Run the 10×15 resumable internal screen only after separate approval; checkpoint each pair/hypothesis.

## Lookahead and chronology audit plan

- Assert reader exclusion of 2021+ before resampling/features.
- Assert all H1 context is timestamped source H1 plus one hour.
- Assert FVG/OB/MSS state uses only current and preceding completed M15 bars; retests occur strictly later.
- Assert Asia/London/prior-D1 levels are unavailable until their window/D1 completes.
- Assert SMT uses exact inner timestamp joins, fixed peers and no fill-forward.
- Assert session membership and Friday exit use UTC-aware timestamps.
- Assert entry uses only next-bar BID/ASK and no future bar influences signal selection.
