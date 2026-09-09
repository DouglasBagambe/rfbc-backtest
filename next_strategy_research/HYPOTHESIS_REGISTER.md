# Strategy 2 Hypothesis Register

**Status:** PENDING BROAD SCREEN
**Scope:** Separate from **FROZEN** RFBC v1.0
**Data requirement:** completed-information M15/H1 BID/ASK, realistic next-bar execution and stress costs.

## Register

| ID | Family | Causal hypothesis | Falsifiable trigger | Status |
|---|---|---|---|---|
| S2-01 | Trend pullback | Liquid-session pullbacks in an established H1 trend resume after rejection. | H1 trend, M15 pullback/reclaim | Pending |
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
| S2-20 | Failed break | M15 failed breakout at weekly high/low reverses under low H1 trend strength. | Failed break/reclaim | Pending |

> **Promotion discipline:** no member may see holdout or external data until a family definition and gate are frozen. Martingale, grid recovery, averaging into losers, stop widening and pair-specific tuning are prohibited.
