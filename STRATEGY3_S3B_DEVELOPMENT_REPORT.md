# Strategy 3 S3B development report

## Scope and integrity

This is one frozen development screen over 2013-01-01 through 2017-12-31 only.
The feature definitions and nomination gate were committed to
`STRATEGY3_S3B_FROZEN_SPEC.md` before results. The hourly reader stops at the
2018 boundary before it parses an OHLC value; no 2018+ outcome was inspected.
The retained rate input is the official BIS CBPOL extract documented in
`STRATEGY3_BIS_CBPOL_PROVENANCE.md`. No stop/target strategy was built.

## Results

| Mechanism | N | 4h mean ATR / t | 8h mean ATR / t | Raw signals/week | Carry effect / conclusion |
| --- | ---: | ---: | ---: | ---: | --- |
| S3-01 strongest/weakest momentum | 30,775 | -0.013 / -1.51 | -0.034 / -2.80 | 118.0 | Base signal negative; reject. |
| S3-02 carry-confirmed momentum | 10,632 | -0.018 / -1.22 | -0.042 / -1.97 | 40.8 | Carry worsened the base mean at both horizons; reject. |
| S3-03 dispersion persistence | 6,330 | -0.043 / -2.33 | -0.034 / -1.28 | 24.3 | Negative, including 2014/15/17; reject. |
| S3-04 stable-rank pullback | 417 | +0.067 / +1.04 | -0.054 / -0.58 | 1.6 | Insufficient significance, unstable years and horizon reversal; reject. |
| S3-05 volatility-conditioned momentum | 22,486 | -0.011 / -1.07 | -0.042 / -2.89 | 86.2 | Volatility condition did not repair the base; reject. |
| S3-06 carry-aligned intraday continuation | 4,591 | -0.029 / -1.35 | -0.058 / -1.87 | 17.6 | Carry/continuation worsened the base; reject. |

`summary.csv`, `by_year.csv`, `by_pair.csv`, `by_currency.csv`, and
`frequency.csv` under `results_next_strategy/strategy3_s3b/` contain the
complete figures. Pair breadth is not supportive: no mechanism has the
required eight positive eligible pairs at a nominated horizon. The only
positive aggregate candidate (S3-04 4h) misses the t-stat, has a negative
adjacent horizon, and is positive in only three years. Therefore **0 of 6
mechanisms are nominated**. Strategy 3 does not proceed to validation from
this frozen screen.
