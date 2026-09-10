# Strategy 2 — Round 2 fidelity audit

**Status:** COMPLETE — corrected implementation awaits a fresh internal screen
**Date:** 10 September 2026
**Scope:** Frozen S2R2 rules versus `round2_exact.py`, `round2_runtime.py`, tests and implementation contract. No 2021+ data was read.

> **DECISION:** The earlier 15-pair result set is preserved under `results_next_strategy/round2/` as diagnostic runtime output only. It cannot be used for promotion because it was generated before the corrections below.

| Area / hypotheses | Finding in diagnostic implementation | Fidelity correction | Deterministic coverage |
|---|---|---|---|
| ATR / H1 state | ATR used a simple rolling mean; H1 trend required close beyond EMA20. | Wilder RMA(14); EMA20/EMA50-only alignment and explicit neutral precedence. H1 is still attached only after completion. | ATR value/availability and trend-state tests. |
| Session state | Core grouped shifts could bleed a prior UTC day; strict runtime patch already corrected the active path. | Retained strict per-day/per-week expanding state and UTC impulse dtype. | Boundary/no-bleed and UTC timestamp tests. |
| S2R2-01 | Used wick excursion and extension-boundary close. | Uses previous completed M15 close, its ATR extension, and current close-through rule. | Close-only/timing tests. |
| S2R2-02 | Window included all 15:xx; inside test was unnecessarily strict. | Exact 14:00–15:45 window and pre-signal range; signal sweep closes inside. | Window/extreme tests. |
| S2R2-03 | Triggered H1 extreme instead of preceding M15 high/low. | First retrace arms; close past impulse extreme cancels; later prior-M15 break enters. | Arm/cancel/trigger tests. |
| S2R2-04 | Used rolling 8/4 approximation rather than both full session histories. | Requires every 07:00-to-current and 12:00-to-current close on common prior-D1 side. | Session-history and four-bar tests. |
| S2R2-05 | First excursion was not required to close inside; range was not explicitly frozen. | Frozen 07:00–09:00 range and two distinct same-edge sweep/reclaims. | Two-event test. |
| S2R2-06 | Added USD/JPY breadth filter not frozen in the rule. | Removed all cross-pair breadth gating. | Pair-neutral daily-expansion test. |
| S2R2-07 | Candidate could be selected from disagreeing members; tie was implicit. | Median threshold, same-sign count, selected agreeing candidate and lexical tie-break. | Alignment, missing member, sign, median, selection tests. |
| S2R2-08 | Added an unfrozen weakness side and omitted continuation break. | Restored pre-data register: JPY-strength side only, selected member and first continuation-low break. | Direction/continuation/one-state test. |
| S2R2-09 | Used dynamic currency-sharing/all-15 comparison. | Exact four USD majors, candidate excluded, other-three median, immediately-following M15 only. | Residual/membership/timestamp tests. |
| S2R2-10 to 12 | Required exact endpoint and Friday-window review. | Retained Asia values only after 06:45; exact windows; Friday through 15:45. | Asia, expansion and Friday boundary tests. |
| Execution | Non-positive ATR could divide by zero. | Invalid ATR/risk signals skip before stop/target/R calculation. | Non-positive ATR and stop-first tests. |

## Non-negotiable controls verified in code

- All cross-pair maps use inner joins; missing component H1 timestamps are not filled.
- Normalisation is trailing, per pair and no later than the completed H1 source bar.
- Cross-map availability is source H1 plus one hour; S2R2-09 is restricted to that exact first M15.
- Candidate selection is one basket candidate per source timestamp with an explicit lexical tie-break.
- Reader rejects 2021-01-01 and later rows before feature construction.

## Follow-up

Run a new complete internal 2013–2020 screen before evaluating the frozen promotion gate. Do not compare or aggregate the diagnostic screen with the corrected run.
