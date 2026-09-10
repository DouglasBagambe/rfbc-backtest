# Round 3A static chronology audit

**Status:** PASS — synthetic/pre-data review only
**Scope:** `round3a_edge_map.py` and `test_round3a_edge_map.py`; no empirical dataset was opened.

| Area | Finding / control |
|---|---|
| Date boundary | `read()` filters each CSV chunk to 2013-01-01 through before 2018-01-01 before concatenation or features. |
| ATR regimes | M15 percentile ranks the current Wilder ATR only against preceding 252 M15 ATR values. H1 percentile is calculated on H1 rows before one-hour-delayed mapping. |
| Forward labels | Labels use exact UTC timestamp lookup at +15/+30/+60/+120/+240 minutes. Missing slots are unavailable, never positional jumps. |
| Sessions | Asia, London open/body, NY open and overlap are independent UTC booleans; NY-open and overlap intentionally overlap. Session extrema are merged only after each source session ends. |
| Cross section | Fixed members and peer sets use strict inner joins. No forward-fill occurs. Cross labels are later exact H1 timestamps only. Cross-sectional dispersion is computed from the synchronized oriented members; its percentile references only prior 252 synchronized timestamps, and low/normal/high regimes are frozen at 20/80. |
| Dispersion outputs | Raw level, percentile and frozen regime accompany cross-sectional rows. Strongest/weakest returns, spread change, residual behavior and basket persistence are conditionally summarized by regime; pair/year breadth is calculated within that same regime. |
| ICT state | FVG and MSS use completed bars; sweep→MSS is ordered within the frozen 8-bar sequence window; OB selection scans the preceding four and breakers require later invalidation. |
| Statistics | Pair breadth is calculated from per-pair effects; year breadth from per-year effects. Aggregate rows merge both values rather than deriving them from aggregate statistics. |
| Resumption | Each pair/cross unit is atomically written with a SHA-256 completion manifest. Invalid, truncated or checksum-mismatched checkpoints cannot be resumed or finalized; the digest covers all checkpoint bytes, so final validation avoids a redundant second line-count scan. Finalization reads each valid checkpoint once, marks each fully partitioned source atomically, then summarizes one edge-level partition at a time. Both source partitions and individual summary payloads are atomically checkpointed, so an interrupted finalizer resumes only unfinished work and never retains the full checkpoint universe in RAM. |
| Performance | Event/horizon row construction is bulk-vectorized with exact timestamp labels precomputed once per horizon. The prior Python row loop is retained only as a synthetic equivalence oracle; no event predicate, output column or statistic changed. |
| Stateful primitives | Order-block invalidation now uses bullish-low and bearish-high heaps, preserving the existing later-close invalidation semantics while removing the prior growing-list scan. A brute-force synthetic oracle verifies identical breaker timestamps. |

> **RESULT:** The mapper remains pre-data. It emits descriptive event statistics only; it contains no order execution, P&L, stop/target or selection logic.
