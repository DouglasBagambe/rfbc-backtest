#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path
import pandas as pd


def load_side(root: Path, pair: str, side: str) -> pd.DataFrame:
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
    return out.set_index("dt")


def resample_ohlc(df: pd.DataFrame, rule: str) -> pd.DataFrame:
    agg={"open":"first","high":"max","low":"min","close":"last"}
    if "volume" in df.columns: agg["volume"]="sum"
    out=df.resample(rule,label="left",closed="left",origin="epoch").agg(agg)
    return out.dropna(subset=["open","high","low","close"])


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
    ap.add_argument("--root",default="data_independent/dukascopy_h1")
    ap.add_argument("--out",default="data_independent/derived")
    args=ap.parse_args()
    root=Path(args.root); out=Path(args.out); out.mkdir(parents=True,exist_ok=True)
    rows=[]
    for pair in args.pairs:
        bid=load_side(root,pair,"bid"); ask=load_side(root,pair,"ask")
        rows.append(validate_pair_alignment(bid,ask,pair))
        pairdir=out/pair; pairdir.mkdir(parents=True,exist_ok=True)
        for side,df in (("bid",bid),("ask",ask)):
            df.to_csv(pairdir/f"{pair}_{side}_h1.csv")
            resample_ohlc(df,"4h").to_csv(pairdir/f"{pair}_{side}_h4.csv")
            resample_ohlc(df,"1D").to_csv(pairdir/f"{pair}_{side}_d1.csv")
    pd.DataFrame(rows).to_csv(out/"dataset_manifest.csv",index=False)
    print(pd.DataFrame(rows).to_string(index=False))

if __name__=="__main__": main()
