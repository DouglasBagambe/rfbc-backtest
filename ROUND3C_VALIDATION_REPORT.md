# Round 3C Validation Report

**Decision:** all five frozen Round 3B hypotheses are **REJECTED**. Strategy 2 price-pattern discovery stops here. No Round 3D candidate exists; no Round 4, 2021+ holdout, or HistData validation is authorized.

## Frozen-run controls

- Validation event window: 2018-01-01 through 2020-12-31 UTC only.
- A December 2017 warm-up supplied ATR and session-state initialization only; it created no trade or result.
- Execution and gate were frozen in `ROUND3C_VALIDATION_GATE.md` before the run.
- The unchanged Round 3A detector functions supplied MSS, OB, shock, and London-sweep events. H5 used only EURUSD/GBPUSD, AUDUSD/NZDUSD, and EURJPY/GBPJPY.
- Single-pair results deduct 0.10 R per round trip; H5 deducts 0.20 R per two-leg round trip. Same-bar stop/target conflicts are stop-first.
- 2021+ rows were excluded before being retained for feature construction; no 2021+ row contributed to a signal, trade, metric, or selection.

## Aggregate validation result

| Hypothesis | Classification | Trades | Expectancy R | PF | Win rate | Avg win / loss R | Max DD R | Total R | Trades/year | Trades/month |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| H1 MSS reversal | REJECTED | 149,318 | -0.0639 | 0.8779 | 51.68% | +0.8890 / -1.0829 | 9,557.80 | -9,539.55 | 49,772.67 | 4,147.72 |
| H2 OB-candidate reversal | REJECTED | 140,958 | -0.0642 | 0.8773 | 51.65% | +0.8892 / -1.0826 | 9,066.92 | -9,053.18 | 46,986.00 | 3,915.50 |
| H3 restricted M15 shock reversal | REJECTED | 174,528 | -0.0711 | 0.8654 | 51.31% | +0.8913 / -1.0854 | 12,428.92 | -12,416.82 | 58,176.00 | 4,848.00 |
| H4 London-open sweep reversal | REJECTED | 49,797 | -0.0860 | 0.8396 | 50.56% | +0.8909 / -1.0852 | 4,288.23 | -4,284.08 | 16,599.00 | 1,383.25 |
| H5 fixed-peer convergence | REJECTED | 23,433 | -0.2768 | 0.5352 | 43.14% | +0.7389 / -1.0474 | 6,488.81 | -6,487.14 | 7,811.00 | 650.92 |

Every hypothesis has negative net expectancy, PF below 1.0, and drawdown far beyond the frozen 20 R limit. The results therefore fail the gate independently of breadth or year-stability considerations.

## Year stability

| Hypothesis | 2018 R / expectancy | 2019 R / expectancy | 2020 R / expectancy |
| --- | --- | --- | --- |
| H1 | -3,245.00 / -0.0653 | -2,473.25 / -0.0502 | -3,821.30 / -0.0758 |
| H2 | -3,085.55 / -0.0659 | -2,267.08 / -0.0488 | -3,700.55 / -0.0777 |
| H3 | -4,129.85 / -0.0714 | -3,822.96 / -0.0669 | -4,464.01 / -0.0750 |
| H4 | -1,418.87 / -0.0866 | -1,399.47 / -0.0835 | -1,465.74 / -0.0881 |
| H5 | -2,106.86 / -0.2816 | -2,179.50 / -0.2706 | -2,200.78 / -0.2788 |

All five are negative in every validation year. There is no favorable-year rescue case.

## Breadth and branch evidence

`results_next_strategy/round3c/by_pair.csv` contains the required result for every single-pair branch and every H5 fixed peer group. It does not show a generalizable positive-universe result: aggregate expectancy is negative for each mechanism, and H5 is negative across its fixed-group construction. The three approved H3 branches and both directional sides of H1, H2, and H4 remain separately reported there; none was added, removed, or tuned after validation began.

## Artifacts and run record

- `results_next_strategy/round3c/summary.csv`
- `results_next_strategy/round3c/by_year.csv`
- `results_next_strategy/round3c/by_pair.csv`
- Local detailed trade ledger: `results_next_strategy/round3c/trades.csv` (preserved locally and intentionally ignored because it is a 95 MB reproducible intermediate, not a requested publication artifact)
- Deterministic test result: `PASS: 9 deterministic Round 3C validation tests`
- Run time: `28:15.75`; max RSS: `822,672 KB`; no swap observed during the run.

No further strategy discovery or validation work was started after this rejection.
