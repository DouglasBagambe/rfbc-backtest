#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path
import pandas as pd


def load_side(root: Path, pair: str, side: str, start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    files = sorted((root / pair / side).glob("*.csv"))
    if not files:
        raise FileNotFoundError(f"No {pair} {side} files under {root}")
    chunks=[]
    for f in files:
        df=pd.read_csv(f)
        if df.empty:
            continue
        df["dt"]=pd.to_datetime(df["dt"], utc=True, errors="coerce")
        chunks.append(df.dropna(subset=["dt","open","high","low","close"]))
    if not chunks:
        raise RuntimeError(f"No usable rows for {pair} {side}")
    out=pd.concat(chunks,ignore_index=True).sort_values("dt").drop_duplicates("dt")
    out=out[(out["dt"] >= start) & (out["dt"] < end)]
    return out.set_index("dt")


def resample_ohlc(df: pd.DataFrame, rule: str, expected_rows: int | None = None) -> pd.DataFrame:
    agg={"open":"first","high":"max","low":"min","close":"last"}
    if "volume" in df.columns: agg["volume"]="sum"
    grouped=df.resample(rule,label="left",closed="left")
    out=grouped.agg(agg)
    if expected_rows is not None:
        out=out[grouped["open"].count().eq(expected_rows)]
    return out.dropna(subset=["open","high","low","close"])


def resample_d1(df: pd.DataFrame) -> pd.DataFrame:
    """Build forex D1 bars on UTC weekdays; do not turn Sunday fragments into EMA days."""
    agg={"open":"first","high":"max","low":"min","close":"last"}
    if "volume" in df.columns: agg["volume"]="sum"
    grouped=df.resample("1D",label="left",closed="left")
    out=grouped.agg(agg).dropna(subset=["open","high","low","close"])
    counts=grouped["open"].count()
    out=out[out.index.weekday < 5]
    # The requested end date can end before its final H1 bucket closes.
    if not out.empty:
        last=out.index[-1]
        expected=21 if last.weekday()==4 else 24
        if counts.loc[last] < expected:
            out=out.iloc[:-1]
    return out


def validate_pair_alignment(bid: pd.DataFrame, ask: pd.DataFrame, pair: str) -> dict:
    common=bid.index.intersection(ask.index)
    if len(common)==0:
        raise RuntimeError(f"No overlapping BID/ASK rows for {pair}")
    b=bid.loc[common]; a=ask.loc[common]
    spread_open=(a.open-b.open)
    crossed=int((spread_open<0).sum())
    return {
        "pair":pair,
        "bid_rows":len(bid),"ask_rows":len(ask),"overlap_rows":len(common),
        "first":str(common.min()),"last":str(common.max()),
        "crossed_open_spreads":crossed,
        "median_open_spread":float(spread_open.median()),
        "p95_open_spread":float(spread_open.quantile(.95)),
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
        bid=load_side(root,pair,"bid",start,end); ask=load_side(root,pair,"ask",start,end)
        rows.append(validate_pair_alignment(bid,ask,pair))
        pairdir=out/pair; pairdir.mkdir(parents=True,exist_ok=True)
        for side,df in (("bid",bid),("ask",ask)):
            if args.source_interval == "m15":
                df.to_csv(pairdir/f"{pair}_{side}_m15.csv")
                resample_ohlc(df,"1h",expected_rows=4).to_csv(pairdir/f"{pair}_{side}_h1.csv")
                resample_ohlc(df,"4h",expected_rows=16).to_csv(pairdir/f"{pair}_{side}_h4.csv")
            else:
                df.to_csv(pairdir/f"{pair}_{side}_h1.csv")
                resample_ohlc(df,"4h",expected_rows=4).to_csv(pairdir/f"{pair}_{side}_h4.csv")
            resample_d1(df).to_csv(pairdir/f"{pair}_{side}_d1.csv")
    pd.DataFrame(rows).to_csv(out/"dataset_manifest.csv",index=False)
    print(pd.DataFrame(rows).to_string(index=False))

if __name__=="__main__": main()
