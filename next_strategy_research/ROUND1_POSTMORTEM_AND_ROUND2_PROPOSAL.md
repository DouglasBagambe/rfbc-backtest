# Strategy 2 — Round 1 Post-mortem and Round 2 Proposal

**Date:** 10 September 2026  
**Status:** ROUND 1 REJECTED; ROUND 2 PENDING APPROVAL  
**Scope:** 15-pair Dukascopy UTC M15 BID/ASK development (2013–2017) and validation (2018–2020) only. RFBC v1.0 is unchanged.

## Decision

> **DECISION:** All 20 Round 1 hypotheses failed the frozen preliminary gate. They will not be retuned per pair, promoted, or shown holdout/external data.

## Evidence-led failure diagnosis

| Finding | Evidence | Interpretation |
|---|---|---|
| Failure was broad, not one-pair contamination | 1 positive development-expectancy cell out of 300 pair/hypothesis cells; that cell had PF 1.04 | There is no credible pair-specific survivor to rescue. |
| Directional edge was absent after realistic execution | All 20 combined hypotheses had negative development and validation expectancy; validation range -0.0965R to -0.2515R | The primary problem is signal selection/timing, not a gate near-miss. |
| Cost drag amplifies weak signals | Best combined validation PF was 0.820; high-frequency families produced 8.6–25.4 trades/day across the universe | Spread/slippage matters, but cannot alone explain uniformly weak PF. |
| Stops dominated exits | Across 300 cells: mean SL share 59.3%, TP share 35.8%, time exit 1.7%, Friday exit 3.2% | Fixed short-horizon payoff structures were repeatedly hit before the intended move matured. |
| Session and generic structure filters did not cure it | London, NY, Asia, compression, sweep, momentum and trend families all remained negative in both periods | The Round 1 primitives were too generic for the observed FX microstructure. |
| Regime/pair breadth did not provide a hidden pocket | Best pair-average expectancy was USDJPY at -0.0831R; EURUSD was -0.0887R | No predeclared major/cross provides a defensible exception. |

Raw evidence: [combined screen](../results_next_strategy/m15_preliminary/screen.csv).

## Round 2 design principles

Round 2 is deliberately not a parameter neighborhood around Round 1. It replaces generic EMA, raw breakout and single-pair sweep triggers with predeclared **value anchors**, **realised daily range state**, **session sequencing**, or **cross-pair currency confirmation**. Lower frequency is acceptable; the screen keeps the same realistic BID/ASK and 0.10-pip slippage model.

## Frozen common execution model

- Completed BID M15/H1/D1 information only; next-M15 entry.
- Long entry ASK + 0.10 pip, long exit BID - 0.10 pip; inverse for shorts.
- One concurrent trade per pair/hypothesis; no averaging, martingale, grid, widening stop, or discretionary exit.
- Initial stop: 1.25× completed M15 ATR(14); target: 1.50R; maximum holding: 24 M15 bars; Friday 16:00 UTC forced exit.
- Same-M15 SL/TP conflict: stop first.
- Development: 2013-01-01 through 2017-12-31. Validation: 2018-01-01 through 2020-12-31. Holdout remains unread.

## Proposed frozen hypotheses

The 12 exact strategy families and triggers are recorded in [the hypothesis register](HYPOTHESIS_REGISTER.md#round-2--frozen-pending-approval). No implementation or screening will begin until approval.

## Proposed Round 2 preliminary promotion gate

The Round 1 gate remains unchanged: development expectancy >= +0.10R, development PF >= 1.15, validation expectancy >= +0.05R, validation PF >= 1.10, and at least 120 combined development-plus-validation trades. A Round 2 survivor must also show positive expectancy in at least 8 of 15 pairs before parameter-neighborhood work.

> **PENDING:** Approval is required before implementation or any new heavy screen.
