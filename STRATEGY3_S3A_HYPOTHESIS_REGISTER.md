# Strategy 3 S3A Proposed Hypothesis Register

**Status:** frozen for S3A family scope; not yet frozen for empirical testing.

All six families use the 15-pair/8-currency universe and the degree-normalised strength score in `STRATEGY3_RESEARCH_PLAN.md`. They are mutually distinct economic claims, not variants selected from price-pattern discovery. The family count and scope are frozen; no entry threshold, lookback, execution parameter, or outcome is approved in this file. Those must be frozen together in S3B before development data is inspected.

| ID | Family | Economic claim | Deterministic later expression | Required data |
| --- | --- | --- | --- | --- |
| S3-01 | Cross-sectional momentum | relative currency strength persists briefly | trade the liquid listed pair expressing highest `S` versus lowest `S`, direction from rank | FX only |
| S3-02 | Carry-confirmed momentum | rate differential reinforces persistent strength | S3-01 only when base-minus-quote CBPOL differential agrees with trade direction | FX + BIS CBPOL |
| S3-03 | Dispersion-expansion persistence | a broad, widening cross-section is more informative than a compressed ranking | S3-01 only when completed strength dispersion is rising by a predeclared rule and winner/loser breadth agrees | FX only |
| S3-04 | Stable-rank pullback | short reversal can be bought/sold against stable macro ranking | fade a bounded short-horizon move only when rank, breadth and carry have stayed aligned for a predeclared completed window | FX + BIS CBPOL |
| S3-05 | Volatility-conditioned momentum | momentum quality varies with FX volatility state | S3-01 only in a predeclared low/normal portfolio FX-volatility regime | FX only |
| S3-06 | Carry-aligned intraday continuation | carry/rank alignment improves re-entry after a controlled pullback | continue the rate-aligned rank direction after a bounded, rule-defined pullback; no candlestick/setup taxonomy | FX + BIS CBPOL |

## Non-negotiable exclusions

- No Strategy 2 event/candle/ICT detector, failed branch, or outcome-derived filter.
- No pair-specific threshold, rate-series substitution, dynamic universe, martingale, grid, averaging, recovery sizing, or discretionary chart override.
- No empirical test, parameter sweep, validation access, or holdout access until a subsequent S3B execution contract and development gate are committed.

## Later automation requirement

Any survivor must have one canonical selected pair, direction, pricing basis, stop/target, volume calculation, expiry, duplicate key, and portfolio-risk decision. A rank alone is not a tradable signal.
