# Round 3B Frozen Hypothesis Register

**Status:** frozen after the authoritative Round 3A corrected review

## Global execution convention

These rules are fixed for the later validation stage. They are design assumptions, not claimed Round 3A results.

- **Bar and timing:** evaluate a registered event at the close of its M15 event bar; enter at the next M15 bar open. A signal whose next open is unavailable is skipped.
- **Risk unit:** use the event bar's already-available M15 ATR. Each position risks one ATR from entry to stop.
- **Stop and target:** fixed 1.0 ATR protective stop and fixed 1.0 ATR target, with no trailing stop or discretionary exit.
- **Time stop:** exit at the close of the 16th M15 bar after entry if neither stop nor target has filled.
- **Costs/slippage:** deduct a fixed 0.10 ATR round-trip cost from every completed trade: 0.03 ATR spread/commission plus 0.02 ATR slippage on each side and 0.03 ATR residual execution allowance. This same assumption applies to each single-pair trade; a two-leg peer trade pays it per leg (0.20 ATR total).
- **Duplicate control:** at most one live position per instrument and directional branch. After exit, do not re-enter that branch until its event condition has been false for one complete M15 bar and then fires again. Simultaneous mutually exclusive branches on one instrument are not netted; the first valid branch in register order is taken and the other is ignored while the position is live.
- **Friday rule:** no entry at or after Friday 16:00 UTC; force-close any open position at Friday 20:45 UTC. No weekend carry.
- **Frequency reporting:** the frequency ranges below are raw event-label incidences from `event_counts.csv`, divided by the five development years. They are explicitly not forecasts of post-duplicate-control trades, which cannot be derived without running the frozen execution simulation.

## H1 — Market-structure-shift reversal

- **Event condition:** the frozen Round 3A detector emits `mss_up` or `mss_down` for an instrument on an M15 bar.
- **Directional interpretation:** short `mss_up`; long `mss_down`.
- **Entry timing / filter:** global convention; no additional session or regime filter.
- **Stop / target / holding:** global 1.0 ATR stop, 1.0 ATR target, and 16-M15-bar maximum.
- **Costs / duplicate / Friday:** global convention.
- **Development evidence:** at H4/H8, `mss_up` is -0.0501/-0.0560 ATR and `mss_down` is +0.0631/+0.0672 ATR. Both sides are same-sign in 15/15 pairs and 5/5 years at H4; no 2018+ result was used.
- **Expected raw frequency:** 28,100--31,750 event labels per pair-year across the two sides (444,880 labels/year over the 15-pair universe). This is an upper-bound signal incidence, not expected filled trades.

## H2 — Order-block-candidate reversal

- **Event condition:** the frozen Round 3A detector emits `ob_candidate_up` or `ob_candidate_down` for an instrument on an M15 bar.
- **Directional interpretation:** short `ob_candidate_up`; long `ob_candidate_down`.
- **Entry timing / filter:** global convention; no extra session or regime filter.
- **Stop / target / holding:** global convention.
- **Costs / duplicate / Friday:** global convention.
- **Development evidence:** H8 is -0.0572 ATR for up and +0.0691 ATR for down, with 14/15 and 15/15 pairs and 5/5 years. The H4/H8/H16 shapes are consistent in sign.
- **Expected raw frequency:** 24,757--27,848 labels per pair-year across the two sides (393,503 labels/year over the universe), before duplicate control.

## H3 — M15 shock reversal, restricted branches

- **Event condition:** only one of these frozen branches may fire: `m15_shock_down_0_5_1_0`, `m15_shock_down_1_0_1_5`, or `m15_shock_up_1_0_1_5`. No other shock band, including `*_gt_2_0`, belongs to this hypothesis.
- **Directional interpretation:** long either approved down-shock branch; short the approved 1.0--1.5 ATR up-shock branch.
- **Entry timing / filter:** global convention; no additional session or regime filter.
- **Stop / target / holding:** global convention.
- **Costs / duplicate / Friday:** global convention; different approved shock branches on the same instrument are mutually exclusive while a position is live.
- **Development evidence:** the down 0.5--1.0 branch is +0.0500 ATR at H4 and +0.0619 at H16; the up 1.0--1.5 branch is -0.0533/-0.0539/-0.0637 at H4/H8/H16. Their breadth is 11--15/15 pairs and 4--5/5 years at qualifying horizons.
- **Expected raw frequency:** 23,979--27,108 labels per pair-year for the three approved branches combined (380,438 labels/year over the universe), before duplicate control.

## H4 — London-open sweep reversal

- **Event condition:** the frozen Round 3A detector emits `london_open_sweep_high` or `london_open_sweep_low` on an M15 bar. This event label is itself the required London-open session filter; no separate session extension is permitted.
- **Directional interpretation:** long after `london_open_sweep_high`; short after `london_open_sweep_low`.
- **Entry timing / filter:** global convention, restricted to the labelled London-open event.
- **Stop / target / holding:** global convention. The 16-bar time stop is deliberate because the qualifying evidence is H16, not a claim of immediate mean reversion.
- **Costs / duplicate / Friday:** global convention.
- **Development evidence:** H16 is +0.0620/-0.0540 ATR, with 12/15 and 10/15 same-sign pairs and 5/5 and 4/5 same-sign years respectively. H8 is directionally consistent but just below 0.05 ATR on both sides.
- **Expected raw frequency:** 8,653--11,257 labels per pair-year across the two sides (149,264 labels/year over the universe), before duplicate control.

## H5 — Fixed-peer divergence convergence

- **Event condition:** the frozen detector emits one of: `divergence_EURUSD_GBPUSD_convergence`, `divergence_AUDUSD_NZDUSD_convergence`, or `divergence_EURJPY_GBPJPY_convergence`.
- **Directional interpretation:** execute the named convergence construction as a market-neutral pair: long the contemporaneous laggard leg and short the leader leg, using equal ATR risk per leg. Do not express it as an unhedged directional FX trade.
- **Entry timing / filter:** global convention; the named peer group is the required cross-sectional filter. The three groups are the complete permitted set.
- **Stop / target / holding:** apply the global 1.0 ATR stop and target independently to the two-leg position on equal risk; close the whole pair when either pair-level 1.0 ATR stop/target equivalent is reached, or at 16 M15 bars. This rule is fixed for validation; no leg substitution is allowed.
- **Costs / duplicate / Friday:** global duplicate and Friday rules; charge 0.20 ATR total round-trip cost for the two legs. Only one live convergence position per named peer group.
- **Development evidence:** all 3/3 groups replicate. At H4/H8/H16, the group effects are +0.486/+0.464/+0.471 ATR (EURUSD/GBPUSD), +0.366/+0.355/+0.354 (AUDUSD/NZDUSD), and +0.371/+0.356/+0.360 (EURJPY/GBPJPY); every group is same-sign in 5/5 years.
- **Expected raw frequency:** 18,295--18,310 labels per peer group-year (54,902 labels/year across the three peer groups), before duplicate control. This is label incidence, not pairs of fills.

## Frozen exclusions

No other Round 3A row, horizon, pair-specific anomaly, shock band, session pattern, or basket result is authorized for Round 3B. In particular, OTE is excluded for N below 300; breaker, FVG, ATR, prior-sweep, sweep-then-MSS, Asia, London-body, New York, and non-listed shock branches are excluded for failing the full mechanism-level criteria; and basket metrics are descriptive only until a separately predeclared, directly tradable construction satisfies peer replication.

Round 3C validation is deliberately not implemented by this register.
