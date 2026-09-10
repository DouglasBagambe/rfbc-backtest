# Strategy 2 Hypothesis Register

**Status:** ROUND 1 REJECTED; ROUND 2 PENDING APPROVAL
**Scope:** Separate from **FROZEN** RFBC v1.0
**Data requirement:** completed-information M15/H1 BID/ASK, realistic next-bar execution and stress costs.

## Register

| ID | Family | Causal hypothesis | Falsifiable trigger | Status |
|---|---|---|---|---|
| S2-01 | Trend pullback | Liquid-session pullbacks in an established H1 trend resume after rejection. | H1 trend, M15 pullback/reclaim | **Rejected Round 1** |
| S2-02 | Trend pullback | First pullback after London impulse has less adverse selection than later pullbacks. | First M15 retrace after impulse | Pending |
| S2-03 | Trend pullback | NY continuation is stronger when London remains above its opening range. | M15 pullback with London bias | Pending |
| S2-04 | Opening range | London opening-range breaks continue when H1 range is compressed. | Completed M15 OR break | Pending |
| S2-05 | Opening range | NY breaks of a non-trending London range revert less often with H1 momentum. | NY OR break plus H1 filter | Pending |
| S2-06 | Opening range | Failed London range breaks reclaiming the range have mean-reversion edge. | Sweep then completed reclaim | Pending |
| S2-07 | Mean reversion | Extreme M15 distance from VWAP/rolling mean reverts in low H1 trend regimes. | Z-score extension/reversal | Pending |
| S2-08 | Mean reversion | Asia-range extremes mean-revert before London only in low-volatility conditions. | Asia sweep/reclaim | Pending |
| S2-09 | Mean reversion | Post-news-like H1 overextension has partial mean reversion after spread stress. | ATR shock/rejection | Pending |
| S2-10 | Compression | Multi-bar M15 ATR compression precedes tradable expansion. | Compression then close breakout | Pending |
| S2-11 | Compression | Compression breaks aligned with H1 trend outperform countertrend breaks. | M15 squeeze/H1 bias | Pending |
| S2-12 | Sweep/reclaim | Prior-session high/low sweep and reclaim yields asymmetric reversal. | Sweep/reclaim close | Pending |
| S2-13 | Sweep/reclaim | Equal-high/low sweep followed by displacement has continuation edge. | Sweep plus displacement | Pending |
| S2-14 | Momentum | H1 impulse followed by shallow M15 retrace resumes during overlap. | Impulse/retrace/rebreak | Pending |
| S2-15 | Momentum | Consecutive M15 momentum closes persist only outside rollover/spread stress. | Three-bar momentum | Pending |
| S2-16 | Time-of-day | London fix-window directionality has repeatable, cost-adjusted continuation. | Predeclared UTC window | Pending |
| S2-17 | Time-of-day | NY open direction conditioned on London range position has edge. | Predeclared UTC window | Pending |
| S2-18 | Cross-session | Asia compression followed by London expansion is distinct from generic breakout. | Asia range/London break | Pending |
| S2-19 | Trend pullback | H1 EMA pullback with M15 micro-break needs no discretionary interpretation. | EMA reclaim/micro break | Pending |
| S2-20 | Failed break | M15 failed breakout at weekly high/low reverses under low H1 trend strength. | Failed break/reclaim | **Rejected Round 1** |

> **Promotion discipline:** no member may see holdout or external data until a family definition and gate are frozen. Martingale, grid recovery, averaging into losers, stop widening and pair-specific tuning are prohibited.

## Round 2 — frozen pending approval

| ID | Family | Causal hypothesis | Frozen trigger | Status |
|---|---|---|---|---|
| S2R2-01 | Prior-day value reversion | A quiet Asia session that stays inside yesterday's range can mean-revert toward yesterday's close before London liquidity. | 05:00–06:45 UTC M15 reclaim after 0.75 ATR extension from prior D1 close; H1 trend neutral | Pending approval |
| S2R2-02 | Late-London range exhaustion | A London day already using most of its normal range is more likely to reject a fresh extreme than extend. | 14:00–15:45 UTC sweep of London high/low after realised range >= 1.25× 20-day median; M15 close back inside | Pending approval |
| S2R2-03 | New York opening-drive continuation | An unusually strong, low-wick first NY hour aligned with the completed H1 trend can continue after its first shallow pullback. | 13:00 UTC completed H1 body >= 0.9 H1 ATR, wick <= 25%; first M15 25–50% retrace then break | Pending approval |
| S2R2-04 | Post-overlap drift | When London and NY have both held the same side of the prior D1 close, late overlap order flow can persist into the fix. | 14:00–15:30 UTC, both sessions on same side of prior D1 close, M15 break of preceding 4-bar range | Pending approval |
| S2R2-05 | Two-hour opening-range fade | A failed second attempt through a narrow H1 opening range is a better reversal structure than a one-bar sweep. | London 07:00–09:00 UTC range <= 0.8× 20-day same-window median; two excursions, second closes inside | Pending approval |
| S2R2-06 | Daily volatility expansion | A day that is quiet through London morning but breaks yesterday's range with broad cross-pair participation may trend. | At 10:00–12:00 UTC, current range <= 0.55× 20-day median then M15 close outside prior D1 high/low; H1 trend aligned | Pending approval |
| S2R2-07 | USD basket relative-strength continuation | Synchronous strength in USD majors represents a currency move rather than isolated pair noise. | At least 3 of EURUSD/GBPUSD/AUDUSD/NZDUSD lower and USDJPY/USDCAD/USDCHF higher on completed H1 z-score >= 1; trade aligned liquid major next M15 | Pending approval |
| S2R2-08 | JPY basket risk-off continuation | Concurrent JPY strength across liquid JPY crosses can persist during London/NY overlap. | At least 3 of EURJPY/GBPJPY/AUDJPY/CADJPY/CHFJPY have completed H1 return <= -0.75 ATR; M15 continuation break | Pending approval |
| S2R2-09 | Correlation-dislocation reversion | A single major that diverges sharply from its predeclared currency basket can revert once its M15 close fails to hold the divergence. | Pair H1 return differs from basket median by >= 1.5 ATR; next completed M15 closes back through 50% of impulse | Pending approval |
| S2R2-10 | Overnight inventory unwind | A one-directional Asia move with low participation can unwind at the London handover if it fails to hold its final Asia extreme. | Asia 00:00–06:45 UTC directional range >= 0.8 H1 ATR but volume <= 20-day same-window median; 07:00–08:30 reclaim | Pending approval |
| S2R2-11 | Trend-day pullback after realised expansion | Trend continuation should be attempted only after a proven intraday expansion, not merely an EMA state. | Current day range >= 0.9× 20-day median, H1 trend aligned, first 38–62% M15 retrace and reclaim during 10:00–14:00 UTC | Pending approval |
| S2R2-12 | Friday position-squaring fade | Late-Friday moves that have not made a new weekly extreme are more likely to revert than continue. | Friday 13:00–15:00 UTC, 3 M15 closes in one direction, no new weekly extreme, then opposite close beyond prior bar midpoint | Pending approval |
