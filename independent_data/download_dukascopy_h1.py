#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path
import time
import re

import pandas as pd
import dukascopy_python
from dukascopy_python import instruments

PAIR_TO_INSTRUMENT = {
    "EURUSD": instruments.INSTRUMENT_FX_MAJORS_EUR_USD,
    "GBPUSD": instruments.INSTRUMENT_FX_MAJORS_GBP_USD,
    "USDJPY": instruments.INSTRUMENT_FX_MAJORS_USD_JPY,
    "AUDUSD": instruments.INSTRUMENT_FX_MAJORS_AUD_USD,
    "NZDUSD": instruments.INSTRUMENT_FX_MAJORS_NZD_USD,
    "USDCAD": instruments.INSTRUMENT_FX_MAJORS_USD_CAD,
    "USDCHF": instruments.INSTRUMENT_FX_MAJORS_USD_CHF,
    "EURJPY": instruments.INSTRUMENT_FX_CROSSES_EUR_JPY,
    "GBPJPY": instruments.INSTRUMENT_FX_CROSSES_GBP_JPY,
    "AUDJPY": instruments.INSTRUMENT_FX_CROSSES_AUD_JPY,
    "CADJPY": instruments.INSTRUMENT_FX_CROSSES_CAD_JPY,
    "CHFJPY": instruments.INSTRUMENT_FX_CROSSES_CHF_JPY,
    "EURGBP": instruments.INSTRUMENT_FX_CROSSES_EUR_GBP,
    "EURAUD": instruments.INSTRUMENT_FX_CROSSES_EUR_AUD,
    "GBPAUD": instruments.INSTRUMENT_FX_CROSSES_GBP_AUD,
}
SIDE_TO_CONST = {
    "bid": dukascopy_python.OFFER_SIDE_BID,
    "ask": dukascopy_python.OFFER_SIDE_ASK,
}
INTERVALS = {
    "h1": dukascopy_python.INTERVAL_HOUR_1,
    "m15": dukascopy_python.INTERVAL_MIN_15,
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


def fetch_month(pair: str, side: str, interval: str, start: pd.Timestamp, end: pd.Timestamp, retries: int = 4) -> pd.DataFrame:
    inst = PAIR_TO_INSTRUMENT[pair]
    offer = SIDE_TO_CONST[side]
    s = start.to_pydatetime().replace(tzinfo=None)
    e = end.to_pydatetime().replace(tzinfo=None)
    last_exc = None
    for attempt in range(1, retries + 1):
        try:
            df = dukascopy_python.fetch(
                instrument=inst,
                interval=INTERVALS[interval],
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


def checkpoint_valid(path: Path, start: pd.Timestamp, end: pd.Timestamp) -> bool:
    """Reject empty, malformed, duplicate, or clearly truncated monthly checkpoints."""
    try:
        frame = pd.read_csv(path, usecols=["dt"])
        dt = pd.to_datetime(frame["dt"], utc=True, errors="coerce")
        return bool(
            not frame.empty and not dt.isna().any() and not dt.duplicated().any()
            and dt.min() < start + pd.Timedelta(days=8)
            and dt.max() >= end - pd.Timedelta(days=8)
        )
    except Exception:
        return False


def available_memory_mb() -> float:
    for line in Path("/proc/meminfo").read_text().splitlines():
        if line.startswith("MemAvailable:"):
            return int(re.findall(r"\d+", line)[0]) / 1024
    return 0.0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pairs", nargs="+", default=["USDJPY"], choices=PAIR_TO_INSTRUMENT.keys())
    ap.add_argument("--start", default="2013-01-01")
    ap.add_argument("--end", default="2026-09-01")
    ap.add_argument("--interval", choices=INTERVALS, default="h1")
    ap.add_argument("--sides", nargs="+", choices=SIDE_TO_CONST, default=("bid", "ask"))
    ap.add_argument("--out")
    ap.add_argument("--sleep", type=float, default=0.05)
    ap.add_argument("--min-available-mb", type=float, default=0.0)
    args = ap.parse_args()

    start = pd.Timestamp(args.start, tz="UTC")
    end = pd.Timestamp(args.end, tz="UTC") + pd.Timedelta(days=1)
    outroot = Path(args.out or f"data_independent/dukascopy_{args.interval}")
    outroot.mkdir(parents=True, exist_ok=True)

    print(f"Dukascopy {args.interval.upper()} BID/ASK download: {start.date()} to {end.date()}")
    for pair in args.pairs:
        for side in args.sides:
            side_dir = outroot / pair / side
            side_dir.mkdir(parents=True, exist_ok=True)
            for mstart, mend in month_starts(start, end):
                if mend <= mstart:
                    continue
                path = side_dir / f"{pair}_{side}_{mstart:%Y_%m}.csv"
                if path.exists() and checkpoint_valid(path, mstart, mend):
                    print("skip", path)
                    continue
                if path.exists():
                    print("refetch invalid checkpoint", path, flush=True)
                if args.min_available_mb and available_memory_mb() < args.min_available_mb:
                    raise RuntimeError(f"Available RAM {available_memory_mb():.0f} MB below {args.min_available_mb:.0f} MB safety floor")
                print("fetch", pair, side, mstart.strftime("%Y-%m"), flush=True)
                df = fetch_month(pair, side, args.interval, mstart, mend)
                df.to_csv(path, index=False)
                time.sleep(args.sleep)

    print("done")


if __name__ == "__main__":
    main()
