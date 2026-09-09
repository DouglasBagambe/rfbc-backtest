#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path
import pandas as pd


REQUIRED_COLUMNS = {"dt", "open", "high", "low", "close"}


def load_side(root: Path, pair: str, side: str, start: pd.Timestamp, end: pd.Timestamp) -> tuple[pd.DataFrame, dict]:
    files = sorted((root / pair / side).glob("*.csv"))
    if not files:
        raise FileNotFoundError(f"No {pair} {side} files under {root}")
    chunks=[]
    malformed_rows = 0
    for f in files:
        df=pd.read_csv(f)
        if df.empty:
            raise RuntimeError(f"Empty checkpoint: {f}")
        missing = REQUIRED_COLUMNS.difference(df.columns)
        if missing:
            raise RuntimeError(f"Malformed checkpoint {f}: missing {sorted(missing)}")
        df["dt"]=pd.to_datetime(df["dt"], utc=True, errors="coerce")
        invalid = df[["dt", "open", "high", "low", "close"]].isna().any(axis=1)
        malformed_rows += int(invalid.sum())
        chunks.append(df.loc[~invalid])
    if not chunks:
        raise RuntimeError(f"No usable rows for {pair} {side}")
    out=pd.concat(chunks,ignore_index=True).sort_values("dt")
    duplicates = int(out["dt"].duplicated().sum())
    if duplicates:
        price_columns = [column for column in ("open", "high", "low", "close", "volume") if column in out.columns]
        conflicting = sum(
            len(group[price_columns].drop_duplicates()) > 1
            for _, group in out.loc[out["dt"].duplicated(keep=False)].groupby("dt")
        )
        if conflicting:
            raise RuntimeError(f"{pair} {side} has {conflicting} conflicting duplicate timestamps")
        # Dukascopy monthly fetches overlap at boundaries. Exact duplicate records
        # are safe to collapse, but their count remains in the manifest.
        out = out.drop_duplicates("dt", keep="first")
    if malformed_rows:
        raise RuntimeError(
            f"{pair} {side} source is not clean: malformed_rows={malformed_rows}"
        )
    out=out[(out["dt"] >= start) & (out["dt"] < end)]
    if out.empty:
        raise RuntimeError(f"No in-range rows for {pair} {side}")
    return out.set_index("dt"), {"raw_files": len(files), "malformed_rows": malformed_rows, "duplicate_timestamps": duplicates}


def resample_ohlc(df: pd.DataFrame, rule: str, expected_rows: int | None = None) -> pd.DataFrame:
    agg={"open":"first","high":"max","low":"min","close":"last"}
    if "volume" in df.columns: agg["volume"]="sum"
    grouped=df.resample(rule,label="left",closed="left")
    out=grouped.agg(agg)
    if expected_rows is not None:
        out=out[grouped["open"].count().eq(expected_rows)]
    return out.dropna(subset=["open","high","low","close"])


def resample_d1(df: pd.DataFrame, source_rows_per_hour: int) -> pd.DataFrame:
    """Build forex D1 bars on UTC weekdays; do not turn Sunday fragments into EMA days."""
    agg={"open":"first","high":"max","low":"min","close":"last"}
    if "volume" in df.columns: agg["volume"]="sum"
    grouped=df.resample("1D",label="left",closed="left")
    out=grouped.agg(agg).dropna(subset=["open","high","low","close"])
    counts=grouped["open"].count()
    out=out[out.index.weekday < 5]
    expected = pd.Series(
        [21 * source_rows_per_hour if ts.weekday() == 4 else 24 * source_rows_per_hour for ts in out.index],
        index=out.index,
    )
    return out[counts.loc[out.index].eq(expected)]


def expected_weekday_slots(start: pd.Timestamp, end: pd.Timestamp, interval_minutes: int) -> pd.DatetimeIndex:
    all_slots = pd.date_range(start.floor("D"), end.ceil("D"), freq=f"{interval_minutes}min", inclusive="left", tz="UTC")
    return all_slots[(all_slots.weekday < 4) | ((all_slots.weekday == 4) & (all_slots.hour < 21))]


def validate_pair_alignment(bid: pd.DataFrame, ask: pd.DataFrame, pair: str, source_interval: str, audit: dict) -> dict:
    common=bid.index.intersection(ask.index)
    if len(common)==0:
        raise RuntimeError(f"No overlapping BID/ASK rows for {pair}")
    b=bid.loc[common]; a=ask.loc[common]
    spread_open=(a.open-b.open)
    crossed=int((spread_open<0).sum())
    interval_minutes = 15 if source_interval == "m15" else 60
    expected = expected_weekday_slots(common.min(), common.max() + pd.Timedelta(minutes=interval_minutes), interval_minutes)
    missing = expected.difference(common)
    return {
        "pair":pair,
        "bid_rows":len(bid),"ask_rows":len(ask),"overlap_rows":len(common),
        "first":str(common.min()),"last":str(common.max()),
        "crossed_open_spreads":crossed,
        "median_open_spread":float(spread_open.median()),
        "p95_open_spread":float(spread_open.quantile(.95)),
        "missing_expected_source_bars": len(missing),
        "first_missing_expected_source_bar": str(missing.min()) if len(missing) else "",
        **audit,
    }


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--pairs",nargs="+",default=["USDJPY"])
    ap.add_argument("--root")
    ap.add_argument("--out",default="data_independent/derived")
    ap.add_argument("--source-interval", choices=("h1", "m15"), default="h1")
    ap.add_argument("--start",default="2013-01-01")
    ap.add_argument("--end",default="2026-09-01")
    args=ap.parse_args()
    root=Path(args.root or f"data_independent/dukascopy_{args.source_interval}"); out=Path(args.out); out.mkdir(parents=True,exist_ok=True)
    start=pd.Timestamp(args.start, tz="UTC"); end=pd.Timestamp(args.end, tz="UTC") + pd.Timedelta(days=1)
    rows=[]
    for pair in args.pairs:
        bid, bid_audit=load_side(root,pair,"bid",start,end); ask, ask_audit=load_side(root,pair,"ask",start,end)
        audit={f"bid_{key}":value for key,value in bid_audit.items()} | {f"ask_{key}":value for key,value in ask_audit.items()}
        rows.append(validate_pair_alignment(bid,ask,pair,args.source_interval,audit))
        pairdir=out/pair; pairdir.mkdir(parents=True,exist_ok=True)
        for side,df in (("bid",bid),("ask",ask)):
            if args.source_interval == "m15":
                df.to_csv(pairdir/f"{pair}_{side}_m15.csv")
                resample_ohlc(df,"1h",expected_rows=4).to_csv(pairdir/f"{pair}_{side}_h1.csv")
                resample_ohlc(df,"4h",expected_rows=16).to_csv(pairdir/f"{pair}_{side}_h4.csv")
            else:
                df.to_csv(pairdir/f"{pair}_{side}_h1.csv")
                resample_ohlc(df,"4h",expected_rows=4).to_csv(pairdir/f"{pair}_{side}_h4.csv")
            source_rows_per_hour = 4 if args.source_interval == "m15" else 1
            resample_d1(df, source_rows_per_hour).to_csv(pairdir/f"{pair}_{side}_d1.csv")
    pd.DataFrame(rows).to_csv(out/"dataset_manifest.csv",index=False)
    print(pd.DataFrame(rows).to_string(index=False))

if __name__=="__main__": main()
