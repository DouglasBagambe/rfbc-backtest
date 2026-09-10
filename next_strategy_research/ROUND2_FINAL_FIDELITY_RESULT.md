# Strategy 2 — Round 2 final fidelity result

**Status:** REJECTED — authoritative corrected evaluation
**Date:** 10 September 2026
**Scope:** Fidelity-corrected frozen implementation; 15-pair Dukascopy BID/ASK M15 internal screen; development 2013–2017 and validation 2018–2020 only.

> **DECISION:** All 12 Round 2 hypotheses failed the unchanged frozen preliminary gate. There are no survivors. The pre-fidelity archive remains diagnostic history only; this document and `results_next_strategy/round2_final_fidelity/` are the authoritative final Round 2 evaluation.

## Execution record

| Item | Result |
|---|---|
| Deterministic suite | `PASS: 19 deterministic Round 2 tests` |
| Checkpoints | 180/180 (12 hypotheses × 15 pairs) |
| Elapsed | 43:00.70 |
| Maximum RSS | 322,192 KB |
| Holdout access | None; reader excluded 2021-01-01 onward |
| Output archive | `results_next_strategy/round2_final_fidelity/` |
| Pre-fidelity archive | `results_next_strategy/round2/` (preserved separately) |

## Frozen-gate results

| Hypothesis | Development expectancy R | Development PF | Validation expectancy R | Validation PF | Positive pairs | Gate result |
|---|---:|---:|---:|---:|---:|---|
| S2R2-01 | -0.2230 | 0.6753 | -0.2108 | 0.6908 | 0 | Fail |
| S2R2-02 | -0.1295 | 0.7655 | -0.0694 | 0.8753 | 0 | Fail |
| S2R2-03 | -0.1009 | 0.8156 | -0.0771 | 0.8525 | 4 | Fail |
| S2R2-04 | -0.1318 | 0.7798 | -0.1152 | 0.8075 | 0 | Fail |
| S2R2-05 | -0.1867 | 0.7216 | -0.1030 | 0.8390 | 0 | Fail |
| S2R2-06 | -0.7376 | 0.1750 | -0.1108 | 0.8272 | 0 | Fail |
| S2R2-07 | -0.0799 | 0.8655 | -0.0809 | 0.8633 | 1 | Fail |
| S2R2-08 | -0.1990 | 0.6967 | -0.1697 | 0.7368 | 0 | Fail |
| S2R2-09 | -0.1697 | 0.7380 | -0.0814 | 0.8636 | 0 | Fail |
| S2R2-10 | -0.1328 | 0.7960 | -0.1735 | 0.7405 | 1 | Fail |
| S2R2-11 | -0.0798 | 0.8686 | -0.0158 | 0.9735 | 6 | Fail |
| S2R2-12 | -0.0781 | 0.8383 | -0.1055 | 0.7977 | 1 | Fail |

## Boundary

No Round 2 parameter, gate, universe, execution rule or chronology split was changed after results were observed. No holdout or HistData external validation was run. Round 3 remains preregistered only and is not implemented or screened.
