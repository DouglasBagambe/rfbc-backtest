# Strategy 2 — Round 2 rejection record

**Status:** REJECTED
**Date:** 10 September 2026
**Scope:** Internal Dukascopy M15 BID/ASK screen, development 2013–2017 and validation 2018–2020. RFBC v1.0 is unaffected.

> **DECISION:** Strategy 2 Round 2 is closed as **REJECTED**. All 12 preregistered hypotheses failed the frozen preliminary promotion gate. There are no Round 2 survivors, no parameter-neighborhood work, no holdout access, and no HistData external validation.

---

## Preserved evidence

The complete runtime output is retained unchanged in `results_next_strategy/round2/`:

- `screen.csv` — consolidated gate result;
- `trades.csv` — complete generated trade ledger;
- `checkpoint_<PAIR>_<HYPOTHESIS>.csv` — 180 pair/hypothesis checkpoints;
- `gate.json` — frozen gate values.

The files are an archival evidence snapshot. They must not be overwritten, merged with later rounds, retuned, or used to select variants.

## Frozen-gate result

| Hypothesis | Development expectancy R | Development PF | Validation expectancy R | Validation PF | Positive pairs | Gate result |
|---|---:|---:|---:|---:|---:|---|
| S2R2-01 | -0.2480 | 0.6442 | -0.1939 | 0.7138 | 0 | Fail |
| S2R2-02 | -0.1251 | 0.7669 | -0.0688 | 0.8727 | 0 | Fail |
| S2R2-03 | -0.1503 | 0.7214 | -0.2811 | 0.5461 | 1 | Fail |
| S2R2-04 | -0.1316 | 0.7745 | -0.1292 | 0.7813 | 0 | Fail |
| S2R2-05 | -0.1442 | 0.7791 | -0.1333 | 0.7948 | 0 | Fail |
| S2R2-06 | -0.1329 | 0.7950 | -0.1234 | 0.8084 | 0 | Fail |
| S2R2-07 | -0.0827 | 0.8568 | -0.0723 | 0.8744 | 3 | Fail |
| S2R2-08 | -0.1252 | 0.7947 | -0.1021 | 0.8285 | 0 | Fail |
| S2R2-09 | -0.1663 | 0.7404 | -0.0593 | 0.8980 | 0 | Fail |
| S2R2-10 | -0.1237 | 0.8087 | -0.1806 | 0.7311 | 2 | Fail |
| S2R2-11 | -0.0697 | 0.8834 | -0.0462 | 0.9239 | 5 | Fail |
| S2R2-12 | -0.0795 | 0.8315 | -0.1097 | 0.7863 | 1 | Fail |

## Method boundary

Runtime/UTC/ATR fidelity fixes are retained in the codebase. The evidence snapshot above is not reinterpreted after the fact, and no rule, threshold, basket membership, pair subset or execution assumption will be changed to rescue Round 2.

The 2021+ Dukascopy holdout and HistData data remain sealed. Round 3 is a separate preregistered research round with no result-derived selection from Round 2.
