# Strategy 2 — Round 2 Lookahead Audit

**Status:** IMPLEMENTATION GATE  
**Scope:** S2R2-01 through S2R2-12; 2013–2020 internal data only

## Decision

> **REQUIRED:** Every signal is calculated at completed M15 timestamp `T`; entry is the executable next-M15 open at `T+1`. No source row at `T+1` may participate in the signal.

## Controls

| Area | Control |
|---|---|
| D1/H1 state | Merge only after completed-bar availability: D1 + one UTC day, H1 + one hour. |
| Session ranges | Expanding high/low is shifted one M15 bar before use; no session-end aggregate is mapped back into the session. |
| Prior-day/weekly values | Shift one complete D1/week before merge. |
| ATR, range medians, volume baselines, z-scores | Trailing rolling windows are shifted one completed bar. No global mean, standard deviation or quantile is permitted. |
| Cross-pair baskets | Components are aligned on their shared completed H1 timestamp; basket value is shifted one H1 and becomes available only at the next H1 boundary. Missing components invalidate that timestamp; they are never filled. |
| Cross-pair divergence | Pair and basket normalisation use independent trailing ATR values shifted one H1. |
| Execution | Long entry ASK + 0.10 pip; long stop/target/exit BID - 0.10 pip. Shorts are inverse. |
| Intrabar ambiguity | If executable SL and TP are both reachable in an M15 bar, stop first. |

## Hypothesis-specific assessment

| IDs | Inputs | Audit result |
|---|---|---|
| S2R2-01 to 06, 10 to 12 | Prior D1, trailing ATR/range/volume, completed sessions | Must use shifted session and trailing features only. |
| S2R2-07 USD basket | Six completed H1 returns/ATRs | Shared timestamp plus one-H1 availability lag required. |
| S2R2-08 JPY basket | Five completed H1 returns/ATRs | Shared timestamp plus one-H1 availability lag required. |
| S2R2-09 dislocation | Pair plus predeclared basket median | Trailing component returns only; no cross-sectional future normalisation. |

> **PENDING:** Unit tests must enforce these controls before any full screen is run.
