# Independent Dukascopy Dataset

Purpose: build a lightweight, versioned external validation dataset without touching the original RFBC research data.

## Design

- Source: Dukascopy historical data
- Resolution downloaded: H1
- Offer sides: BID and ASK separately
- Timezone: UTC
- Derived bars: H4 and D1, constructed locally from H1 with UTC boundaries
- Signals should use BID bars for comparability with the original bid-style dataset
- Execution should use the economically correct side: long entries at ASK / exits at BID; short entries at BID / exits at ASK
- First target: USDJPY only, 2013-01-01 through 2026-09-01
- Expand to EURUSD/GBPUSD/AUDUSD only after the USDJPY external replication is evaluated

Why H1 instead of decade-scale tick/M1: RFBC is an H4/D1 strategy and the laptop is resource constrained. H1 BID/ASK materially improves execution realism while keeping downloads and memory manageable. Tick/M1 remains a later confirmation layer if a candidate survives.

## Run order

```bash
python3 -m pip install -r independent_data/requirements.txt --break-system-packages
python3 independent_data/download_dukascopy_h1.py --pairs USDJPY --start 2013-01-01 --end 2026-09-01
python3 independent_data/build_bars.py --pairs USDJPY
```

The downloader is monthly and resumable. Existing non-empty files are skipped.

## Validation requirements before any strategy result is accepted

1. BID and ASK ranges overlap and no negative/crossed opening spreads appear except clearly explainable data anomalies.
2. H1 timestamps remain UTC.
3. H4 bars begin at 00:00, 04:00, 08:00, 12:00, 16:00, 20:00 UTC.
4. D1 bars begin at 00:00 UTC.
5. No silent timezone shifting.
6. No lookahead while mapping completed D1/H4 bars.
7. Compare overlapping 2013-2022 price structure with the original source, but do not require exact equality because vendors differ.
8. Preserve 2022-03 onward as genuinely unseen external history for the RFBC candidate decision.

## Promotion rule

The existing RFBC USDJPY candidates must be rerun unchanged. Do not optimize against this dataset before the external decision.
