#!/usr/bin/env python3
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from pathlib import Path
import time

import pandas as pd
import dukascopy_python
from dukascopy_python import instruments

PAIR_TO_INSTRUMENT = {
    "EURUSD": instruments.INSTRUMENT_FX_MAJORS_EUR_USD,
    "GBPUSD": instruments.INSTRUMENT_FX_MAJORS_GBP_USD,
    "USDJPY": instruments.INSTRUMENT_FX_MAJORS_USD_JPY,
    "AUDUSD": instruments.INSTRUMENT_FX_MAJORS_AUD_USD,
}
SIDE_TO_CONST = {
    "bid": dukascopy_python.OFFER_SIDE_BID,
    "ask": dukascopy_python.OFFER_SIDE_ASK,
}


def month_starts(start: pd.Timestamp, end: pd.Timestamp):
    cur = start.normalize().replace(day=1)
    while cur < end:
        nxt = cur + pd.offsets.MonthBegin(1)
        yield cur, min(nxt, end)
        cur = nxt


def normalize_frame(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame(columns=["dt", "open", "high", "low", "close", "volume"])
    out = df.reset_index()
    ts_col = out.columns[0]
    out = out.rename(columns={ts_col: "dt"})
    out["dt"] = pd.to_datetime(out["dt"], utc=True, errors="coerce")
    out = out.dropna(subset=["dt", "open", "high", "low", "close"])
    out = out[[c for c in ["dt", "open", "high", "low", "close", "volume"] if c in out.columns]]
    out = out.sort_values("dt").drop_duplicates("dt")
    return out


def fetch_month(pair: str, side: str, start: pd.Timestamp, end: pd.Timestamp, retries: int = 4) -> pd.DataFrame:
    inst = PAIR_TO_INSTRUMENT[pair]
    offer = SIDE_TO_CONST[side]
    s = start.to_pydatetime().replace(tzinfo=None)
    e = end.to_pydatetime().replace(tzinfo=None)
    last_exc = None
    for attempt in range(1, retries + 1):
        try:
            df = dukascopy_python.fetch(
                instrument=inst,
                interval=dukascopy_python.INTERVAL_HOUR_1,
                offer_side=offer,
                start=s,
                end=e,
                max_retries=3,
                debug=False,
            )
            out = normalize_frame(df)
            if out.empty:
                raise RuntimeError(f"Empty response for {pair} {side} {start:%Y-%m}")
            return out
        except Exception as exc:
            last_exc = exc
            if attempt < retries:
                time.sleep(min(2 ** attempt, 8))
    raise RuntimeError(f"Failed {pair} {side} {start:%Y-%m}: {last_exc}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pairs", nargs="+", default=["USDJPY"], choices=PAIR_TO_INSTRUMENT.keys())
    ap.add_argument("--start", default="2013-01-01")
    ap.add_argument("--end", default="2026-09-01")
    ap.add_argument("--out", default="data_independent/dukascopy_h1")
    ap.add_argument("--sleep", type=float, default=0.05)
    args = ap.parse_args()

    start = pd.Timestamp(args.start, tz="UTC")
    # CLI end dates are inclusive calendar dates; fetch uses an exclusive end.
    end = pd.Timestamp(args.end, tz="UTC") + pd.Timedelta(days=1)
    outroot = Path(args.out)
    outroot.mkdir(parents=True, exist_ok=True)

    print(f"Dukascopy H1 BID/ASK download: {start.date()} to {end.date()}")
    for pair in args.pairs:
        for side in ("bid", "ask"):
            side_dir = outroot / pair / side
            side_dir.mkdir(parents=True, exist_ok=True)
            for mstart, mend in month_starts(start, end):
                if mend <= mstart:
                    continue
                path = side_dir / f"{pair}_{side}_{mstart:%Y_%m}.csv"
                if path.exists() and path.stat().st_size > 100:
                    print("skip", path)
                    continue
                print("fetch", pair, side, mstart.strftime("%Y-%m"))
                df = fetch_month(pair, side, mstart, mend)
                df.to_csv(path, index=False)
                time.sleep(args.sleep)

    print("done")


if __name__ == "__main__":
    main()
