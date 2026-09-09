# Track 1: Independent RFBC Replication Status

Status: **NOT COMPLETED — RFBC survival unknown.**

The three unchanged USDJPY candidates remain defined in
`results_v11_research/`:

1. Frozen USDJPY RFBC v1.0 subset.
2. USDJPY 25-H4 breakout, 1.50 ATR stop, 3.00R target.
3. USDJPY 25-H4 breakout, 1.75 ATR stop, 2.50R target.

No candidate was retuned.

## Independent-data investigation

HistData exposes independent M1 bid-price archives intended for resampling;
Dukascopy also offers historical bid/ask export. In this constrained run, the
HistData archive request path did not produce a reliable machine-downloadable
multi-year payload, and decade-scale M1 download/resampling would exceed the
intended lightweight workflow. Therefore no independent candles were mixed
with the existing research dataset and no external-replication result is
claimed.

## Required next execution

Use a versioned independent bid/ask source, save a manifest/checksum, and:

1. Normalize timestamps to UTC and document the broker/session convention.
2. Build D1/H4 bars from source M1 or verified native bars.
3. Audit missing bars and weekend/holiday gaps.
4. Apply bid/ask or a documented realistic spread model.
5. Run the three candidates unchanged and report only the prescribed metrics.

If that replication fails, archive RFBC without further rescue work.
