# Strategy 3 Research Plan — S3A Design Only

**Status:** research/data design only. No Strategy 3 empirical test has been run and no 2018+ Strategy 3 outcome has been inspected.

## Boundary

Strategy 3 is a fresh systematic cross-sectional FX family. It must not reuse a Strategy 2 price-pattern hypothesis, parameter, or rescue filter. Chronology is fixed conceptually as development 2013--2017, validation 2018--2020, and sealed holdout 2021+. S3A may inspect only infrastructure and source metadata; it may not download the proposed macro data or produce empirical factor results.

## A. Currency-strength engine

At completed timestamp `t`, for each directed pair `p = B/Q` and lookback `h`, define:

`r[p,t,h] = ln(close[p,t] / close[p,t-h])`

`z[p,t,h] = r[p,t,h] / sigma[p,t,h]`

where `sigma` is a trailing, completed-bar EWMA volatility using the same return horizon. A pair contributes `+z` to base currency `B` and `-z` to quote currency `Q`. Let `P(c)` be the 15-pair universe's incident pairs for currency `c`; the degree-normalised score is:

`S[c,t,h] = sum(sign(c,p) * z[p,t,h] for p in P(c)) / |P(c)|`

with `sign=+1` for the base and `-1` for the quote. Ties are resolved lexically by ISO currency code. No pair-specific weights are permitted.

The later S3B screen may evaluate only these transparent variants:

- normalized multi-pair return: `S` at predeclared H1 and H4 horizons;
- volatility-adjusted momentum: the `z` formulation above;
- rank score: cross-sectional rank of `S` over USD, EUR, GBP, JPY, AUD, NZD, CAD and CHF, scaled to `[-1, +1]`;
- breadth: `B[c] = mean(sign(c,p) * sign(r[p]))`, the constituent-pair agreement share.

There will be no stacked indicator set. A currency score is eligible only when the required constituent pair closes are all available; missing data invalidates the score rather than being forward-filled.

## B. Carry/rates layer

The primary historical carry proxy is the daily BIS Central Bank Policy Rates (CBPOL) series. BIS states that it tracks the main policy instrument (target or, where needed, traded rate), supplies daily and monthly frequency, long history, metadata, and bulk CSV downloads. It covers more than 40 economies, which makes it the only planned primary source for a consistent eight-currency policy-rate panel. Source: [BIS CBPOL overview](https://data.bis.org/topics/CBPOL) and [BIS bulk downloads](https://data.bis.org/bulkdownload).

For a pair `B/Q`, the fixed carry feature is `C[B/Q,t] = policy_rate[B,t] - policy_rate[Q,t]`. Source observations must be applied only from the documented effective date in the BIS metadata, then forward-filled across FX business days. The factor is a slow state/rank, not an intraday announcement signal.

The secondary robustness series, not an S3A requirement, is a monthly short-term market-rate panel from OECD SDMX. It can distinguish a policy-rate proxy from a money-market proxy, but its country definitions and Euro-area mapping must be audited before use. OECD documentation identifies its short-term-interest-rate series and definition changes (for example UK SONIA from 2020); it must therefore never be silently mixed with CBPOL. [OECD rate documentation](https://stats.oecd.org/wbos/fileview2.aspx?IDFile=3040f1bd-c27e-4d36-9051-b51622fba19b).

| Currency | Primary series | Secondary / audit fallback | S3A decision |
| --- | --- | --- | --- |
| USD | BIS US main policy rate | OECD US short-term rate; official Fed/FRED cross-check | Required |
| EUR | BIS ECB/euro-area policy rate | ECB EONIA API historical series | Required |
| GBP | BIS UK policy rate | OECD UK short-term rate / SONIA definition audit | Required |
| JPY | BIS Japan policy rate | OECD Japan short-term rate | Required |
| AUD | BIS Australia policy rate | OECD Australia short-term rate | Required |
| NZD | BIS New Zealand policy rate | OECD New Zealand short-term rate | Required |
| CAD | BIS Canada policy rate | OECD Canada short-term rate; BoC Valet cross-check | Required |
| CHF | BIS Switzerland policy rate | OECD Switzerland short-term rate | Required |

The Bank of Canada Valet API is a useful official reproducibility benchmark for the CAD leg but is not a substitute for a homogeneous eight-currency panel. It is no-cost, keyless, and programmatically exposes financial/economic series. [BoC Valet documentation](https://www.bankofcanada.ca/valet/docs/).

No fabricated overnight, broker-swap, forward-point, or yield series may stand in for missing data. A future live carry implementation must use the broker's actual swap specification separately from the research proxy.

## C. Minimal regime layer

The initial regime is deliberately FX-native: cross-sectional dispersion `D[t] = std(S[c,t,h])` plus portfolio realised FX volatility (median trailing pair volatility). Both are derived from the reusable BID/ASK bars, so they add no external dependency.

No equity, commodity, yield-change, or news dataset is required for S3A. An external risk-sentiment layer may be considered only after a factor survives development and only as a predeclared separate robustness test; it is not a rescue filter. The ECB's EONIA history is useful for EUR rate provenance, not a general risk regime. This keeps the first design to price cross-section, rates, and one volatility state.

## D. Candidate mechanism families

The proposed register contains six economically distinct mechanisms, each deterministic and later subject to one shared execution model. It deliberately excludes candlestick/event-pattern mining:

1. strongest-versus-weakest cross-sectional momentum;
2. rate-differential-aligned strongest-versus-weakest momentum;
3. strength persistence after cross-sectional dispersion expansion;
4. short-horizon pullback into a stable strength-plus-carry ranking;
5. momentum continuation only in a low/normal FX-volatility state;
6. carry-aligned intraday continuation after a bounded pullback.

Exact thresholds, lookbacks, stop/target, costs, and a promotion gate are not frozen in S3A. They must be declared together before any development data is inspected; no rate download or development analysis occurs in this phase.

## E. Frequency objective

The target is several valid portfolio opportunities per week and, if evidence supports it, multiple active-day opportunities. Frequency is an outcome of the ranking and duplicate/risk controls, never a survival criterion. A low-frequency positive mechanism may pass; a frequent negative one may not.

## F. Automation contract

Every later candidate must emit a complete deterministic ticket:

`broker_symbol, BUY/SELL, entry, SL, TP, position_size, valid_until, strategy_id, ranking_timestamp, reason, portfolio_risk_after`.

The current monitoring stack provides a reusable Telegram payload formatter, bid/ask fetch pattern, and basic risk calculations, but only has broker mappings for USDJPY and AUDJPY. Strategy 3 will require a validated 15-symbol broker-specification map, live account equity, contract size, tick/point value, min/max/step volume, stop-distance rules, swaps, trading-session status, duplicate IDs, and portfolio currency/exposure caps before any alert can be described as executable. MT5 execution is expressly out of scope until those controls are validated.

## Reusable repository assets and limits

- Reuse: 15-pair Dukascopy-derived BID/ASK M15, H1, H4 and D1 bars in `data_independent/derived_m15` (~869 MB); the manifest shows coverage through 2026-09-01 and bid/ask alignment metadata.
- Reuse: `independent_data/build_bars.py` for validation/alignment, and monitor/Telegram formatting patterns.
- Do not reuse: Strategy 2 signals, gates, outputs, or empirical conclusions.
- Later readers must hard-stop before the selected chronology boundary before feature construction; the Strategy 2 chunk-reader caveat must not be repeated.

## S3A exit criteria

S3A ends after the data requirements and hypothesis register are committed. The next authorized action is a small, checksummed BIS policy-rate acquisition and a source-coverage audit; it is not authorized by this document to run factor research or inspect validation/holdout results.
