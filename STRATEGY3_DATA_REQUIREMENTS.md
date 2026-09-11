# Strategy 3 Data Requirements

**Status:** no new dataset has been downloaded in S3A.

## Reusable local data

| Asset | Location | Use | Status |
| --- | --- | --- | --- |
| 15-pair BID/ASK M15, H1, H4, D1 bars | `data_independent/derived_m15/` | return, volatility, strength, execution simulation | Reusable; ~869 MB |
| Alignment/quality manifest | `data_independent/derived_m15/dataset_manifest.csv` | input audit only | Reusable |
| Raw/derived H1 set | `data_independent/dukascopy_h1/`, `data_independent/derived/` | provenance/cross-check | Reusable; ~390 MB combined |
| Bar builder | `independent_data/build_bars.py` | reproducible source validation | Reusable |
| Monitor and Telegram formatter | `monitor/` | later ticket and alert implementation | Reusable pattern; not Strategy 3 logic |

Strategy 3 needs no new FX price history, no database, and no Node/Docker tooling for S3A.

## Required before S3B research

| Dataset | Purpose | Source and acquisition | Required fields | Expected size |
| --- | --- | --- | --- | ---: |
| BIS CBPOL policy-rate panel | common daily carry/rate state for all 8 currencies | Download one versioned CSV plus its metadata from [BIS CBPOL](https://data.bis.org/topics/CBPOL) / [bulk download](https://data.bis.org/bulkdownload); store raw checksum and source retrieval date | country/area code, date, rate, frequency, effective-date/source metadata | likely under 25 MB raw; under 2 MB filtered |
| CBPOL currency mapping | auditable ISO currency-to-BIS series selection | hand-authored only after reviewing BIS metadata; version in repo | `currency, bis_series, effective_date_rule, notes` | under 10 KB |
| OECD short-term-rate panel | optional secondary robustness comparison, never merged silently with CBPOL | targeted monthly SDMX extract after coverage and definition audit | geography, period, rate, unit, methodology/version | under 5 MB |

The BIS panel is the only new historical dataset required to begin core development research. OECD is a desirable secondary check, not a prerequisite for the first development screen. The ECB EONIA API and Bank of Canada Valet API are source-specific provenance checks, not primary panel inputs. The ECB confirms its historical EONIA dataset is API-accessible, and BoC documents public programmatic access. [ECB EONIA information](https://data.ecb.europa.eu/data/datasets/EON/data-information), [BoC Valet](https://www.bankofcanada.ca/valet/docs/).

## Not required and not approved now

- HistData, broker tick history, or any second FX price vendor;
- equity-index, commodity, VIX, news, COT, options, or ML feature datasets;
- 2021+ Strategy 3 feature/result extraction;
- broker accounts, live trading, or MT5 integration.

## Expected compute and storage burden

The new filtered daily rate panel is negligible relative to the existing FX store. A development-only H1/D1 cross-sectional screen should process one timestamp-aligned 15-pair frame at a time, with a target working set below 500 MB RAM and no database. M15 execution validation should be streamed/checkpointed per pair or portfolio date to stay below 1 GB RAM on this machine. No large download is approved in S3A.

## Data quality and chronology requirements

1. Keep raw downloads immutable, with SHA-256 checksum, URL, HTTP retrieval date, license/terms note, and source release/version metadata.
2. Select rates only after confirming definition, currency/area mapping, coverage from 2013, and documented effective date.
3. Convert the selected daily rate to an FX-business-day state only after its effective date; never backfill an announced rate into earlier timestamps.
4. Freeze all source mappings and availability lags before development outcomes are inspected.
5. Development readers must admit only 2013--2017 before any factor construction. Validation and holdout must remain sealed until the development hypothesis, execution contract, and gate are committed.
