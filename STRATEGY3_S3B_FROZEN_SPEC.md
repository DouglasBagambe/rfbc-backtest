# Strategy 3 S3B frozen development specification

This document was written before any Strategy 3 development result was
calculated. It is the sole definition used by `strategy3/s3b_development.py`.
No parameter in this document may be changed based on the 2013--2017 screen.

## Data boundary

The screen uses completed hourly bars from `data_independent/derived_m15` and
the retained BIS policy-rate extract. The feature reader stops at the first
timestamp at or after `2018-01-01T00:00:00Z`; it does not parse or retain a
post-boundary OHLC value. Development observations are 2013-01-01 through
2017-12-31. The initial 60 hourly observations are warm-up only.

## Common feature definitions

For pair `p=B/Q`, let `m_t=(bid_close_t+ask_close_t)/2` and let
`r4=ln(m_t/m_(t-4))`. Its scale is the trailing, completed 60-observation
sample standard deviation of `r4`. The pair contribution is `z=r4/sigma4`.
For each currency c:

`S_c = mean(sign(c,p) * z_p)` across its available constituent pairs, where
`sign` is +1 for the base and -1 for the quote. Breadth is the corresponding
mean of `sign(c,p)*sign(r4_p)`. Ranks sort `S` descending; ties use ISO code.

At each timestamp the candidate is the listed universe pair with the largest
absolute `S_base-S_quote`; ties use the literal pair code. Direction is BUY
when `S_base>S_quote`, otherwise SELL. This deliberately selects from the
fixed 15-pair universe rather than inventing synthetic crosses.

`atr1` is the 14-completed-hour mean true range of midpoint bars. The outcome
at horizons 4 and 8 hours is `direction*(m_(t+h)-m_t)/atr1_t`. Both horizons
are reported, but mechanism ranking treats them as one discovery.

Carry is the BIS daily end-of-period policy rate, forward-filled only over
subsequent calendar days *within the retained extract*. It is never filled
through a BIS missing value. For B/Q it is `rate_B-rate_Q`; confirmation means
that its sign equals the candidate direction. BIS records Japan as having no
policy rate from 2013-04-04 through 2016-09-20, so mechanisms requiring carry
are ineligible for a JPY candidate during that interval.

Dispersion is the cross-sectional sample standard deviation of the eight
currency strengths. Portfolio volatility is the median pair `sigma4`. Its
percentile is measured against the preceding 120 completed hourly values.

## Six frozen mechanisms

All candidate events are evaluated once per completed H1 timestamp. No
pair-specific parameter or post-result filter is permitted.

| ID | Event condition | Direction | Horizons |
| --- | --- | --- | --- |
| S3-01 | Candidate from the common rank rule. | Rank direction. | 4, 8 H1 |
| S3-02 | S3-01 and carry confirmation. | Rank direction. | 4, 8 H1 |
| S3-03 | S3-01; dispersion is greater than its value 24 completed hours earlier; breadth of both candidate currencies is at least 0.60. | Rank direction. | 4, 8 H1 |
| S3-04 | S3-01; carry confirmation; the same base/quote rank direction is selected at t, t-1 and t-2; the signed one-hour pair return is negative but not below -0.75 times its 60-hour one-hour-return scale. | Rank direction after the pullback. | 4, 8 H1 |
| S3-05 | S3-01; portfolio volatility is at or below its trailing 120-hour 80th percentile. | Rank direction. | 4, 8 H1 |
| S3-06 | S3-01; carry confirmation; signed one-hour pair return is positive and no greater than +1.00 times its 60-hour one-hour-return scale. | Rank direction. | 4, 8 H1 |

## Development nomination gate

A mechanism can be nominated only if at least one predeclared horizon meets
all of: N >= 300; directional mean >= 0.05 ATR; t-statistic >= 2.0; positive
mean in at least four of the five calendar years; and positive mean in at
least eight of the fifteen listed pairs which each contribute at least 30
events. It must also have a non-negative result at the adjacent frozen horizon
when that horizon has at least 300 events. These are evidence-screen criteria,
not a final execution strategy or SL/TP design.
