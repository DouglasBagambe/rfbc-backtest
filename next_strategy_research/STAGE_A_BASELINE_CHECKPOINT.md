# Strategy 2 — Stage A Baseline Checkpoint

**Status:** REJECTED BASELINE FAMILIES
**Scope:** H4 exploratory screen only; not final Strategy 2 validation
**RFBC v1.0:** FROZEN and unchanged

## Decision

> **DECISION:** Reject all six pre-existing H4 baseline prototypes. None reached the predeclared development/validation promotion gate; none may proceed to holdout, external validation, broker qualification, or live consideration.

| Family | Trades | Development expectancy R | Validation expectancy R | Full PF | Decision |
|---|---:|---:|---:|---:|---|
| trend_pullback | 1,776 | -0.0862 | +0.0067 | 0.940 | REJECTED |
| breakout_retest | 498 | -0.1416 | -0.0511 | 0.759 | REJECTED |
| mtf_momentum | 1,763 | -0.0636 | -0.0541 | 0.939 | REJECTED |
| contraction_expansion | 245 | -0.0890 | -0.0663 | 0.876 | REJECTED |
| range_mean_reversion | 351 | -0.1460 | -0.0892 | 0.769 | REJECTED |
| session_momentum | 149 | +0.0021 | -0.2216 | 0.855 | REJECTED |

## Evidence

- [Prototype screen](../results_next_strategy/prototype_screen.csv)
- [Existing exploratory report](../results_next_strategy/NEXT_STRATEGY_RESEARCH_REPORT.md)
- [Hypothesis register](HYPOTHESIS_REGISTER.md)

## Important limitation

This baseline uses four pairs and H4 source bars. It does **not** satisfy the charter's M15/H1 BID/ASK, full-universe, frozen-holdout, or independent-external validation requirements. It is a cheap family-falsification checkpoint only. No final Strategy 2 conclusion is permitted from this checkpoint.

## Next required stage

Build the common M15/H1 BID/ASK engine and run the entire 20-hypothesis register on the predeclared 15-pair universe before freezing any candidate definition or final promotion gate.
