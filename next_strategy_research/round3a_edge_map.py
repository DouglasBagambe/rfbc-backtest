#!/usr/bin/env python3
"""Round 3A development-only descriptive FX edge map; never simulates trades."""
from __future__ import annotations

import argparse
from pathlib import Path
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
START=pd.Timestamp("2013-01-01",tz="UTC")
END=pd.Timestamp("2018-01-01",tz="UTC")
PAIRS=("EURUSD","GBPUSD","USDJPY","AUDUSD","NZDUSD","USDCAD","USDCHF","EURJPY","GBPJPY","AUDJPY","CADJPY","CHFJPY","EURGBP","EURAUD","GBPAUD")
USD_DIRECT=("EURUSD","GBPUSD","AUDUSD","NZDUSD"); USD_INVERSE=("USDJPY","USDCAD","USDCHF")
JPY=("EURJPY","GBPJPY","AUDJPY","CADJPY","CHFJPY")
HORIZONS=(1,2,4,8,16)

def atr(f,n=14):
    prev=f.close.shift(); tr=pd.concat((f.high-f.low,(f.high-prev).abs(),(f.low-prev).abs()),axis=1).max(axis=1)
    return tr.ewm(alpha=1/n,adjust=False,min_periods=n).mean()

def read(path):
    chunks=[]
    for x in pd.read_csv(path,usecols=["dt","open","high","low","close","volume"],parse_dates=["dt"],chunksize=40000,dtype={k:"float32" for k in ("open","high","low","close","volume")}):
        x.dt=pd.to_datetime(x.dt,utc=True)
        # The filter deliberately occurs before concatenation/features.
        chunks.append(x[(x.dt>=START)&(x.dt<END)])
    if not chunks: raise RuntimeError(f"no development rows: {path}")
    return pd.concat(chunks,ignore_index=True).set_index("dt").sort_index()

def h1_available(h):
    x=h.copy(); x["h1_atr"]=atr(x); e20=x.close.ewm(span=20,adjust=False).mean(); e50=x.close.ewm(span=50,adjust=False).mean()
    x["h1_trend"]=np.where(e20>e50,1,np.where(e20<e50,-1,0)); x["h1_norm"]=(x.close-x.open)/x.h1_atr; x["available"]=x.index+pd.Timedelta(hours=1)
    return x[["h1_atr","h1_trend","h1_norm","available"]]

def attach_h1(f,h):
    left=f.copy(); left.index.name="dt"
    return pd.merge_asof(left.reset_index().sort_values("dt"),h.reset_index(drop=True).sort_values("available"),left_on="dt",right_on="available",direction="backward").drop(columns="available").set_index("dt")

def trailing_rank(s,window=252):
    # Current observation is ranked only against prior completed observations.
    return s.shift(1).rolling(window,min_periods=window).apply(lambda x: pd.Series(x).rank(pct=True).iloc[-1])

def prepare(root,pair):
    d=root/pair; f=read(d/f"{pair}_bid_m15.csv"); h=read(d/f"{pair}_bid_h1.csv")
    f["atr15"]=atr(f); f["atr_pct"]=trailing_rank(f.atr15); f["date"]=f.index.normalize(); f["hour"]=f.index.hour; f["minute"]=f.index.minute; f["year"]=f.index.year
    f=attach_h1(f,h1_available(h)); f["h1_atr_pct"]=trailing_rank(f.h1_atr)
    daily=f.groupby("date").agg(high=("high","max"),low=("low","min")); daily["prior_high"]=daily.high.shift(); daily["prior_low"]=daily.low.shift()
    f=f.join(daily[["prior_high","prior_low"]],on="date")
    asia=(f.hour<7); f["asia_hi"]=f.high.where(asia).groupby(f.date).transform("max"); f["asia_lo"]=f.low.where(asia).groupby(f.date).transform("min")
    return f

def session_code(f):
    h,m=f.hour,f.minute; out=np.full(len(f),"other",dtype=object)
    out[(h<7)|((h==6)&(m<=45))]="asia"; out[(h>=7)&(h<=8)]="london_open"; out[(h>=9)&(h<=12)]="london_body"; out[(h>=13)&(h<=14)]="ny_open"; out[(h>=13)&(h<=15)]=np.where(out[(h>=13)&(h<=15)]=="ny_open","ny_open","overlap")
    return out

def event_masks(f):
    p4h=f.high.shift(1).rolling(4).max(); p4l=f.low.shift(1).rolling(4).min(); s=f.session
    bullish_fvg=f.low>f.high.shift(2); bearish_fvg=f.high<f.low.shift(2)
    asia_done=f.hour>=7
    masks={
      "mss_up":f.close>p4h, "mss_down":f.close<p4l,
      "fvg_up":bullish_fvg, "fvg_down":bearish_fvg,
      "asia_sweep_reclaim_low":asia_done&(f.low<f.asia_lo)&(f.close>=f.asia_lo),
      "asia_sweep_reclaim_high":asia_done&(f.high>f.asia_hi)&(f.close<=f.asia_hi),
      "prior_day_sweep_reclaim_low":(f.low<f.prior_low)&(f.close>=f.prior_low),
      "prior_day_sweep_reclaim_high":(f.high>f.prior_high)&(f.close<=f.prior_high),
      "ob_candidate_up":(f.close>p4h)&(f.close.shift(1)<f.open.shift(1)),
      "ob_candidate_down":(f.close<p4l)&(f.close.shift(1)>f.open.shift(1)),
      "breaker_up":(f.close>p4h)&(f.close.shift(1)<p4l.shift(1)),
      "breaker_down":(f.close<p4l)&(f.close.shift(1)>p4h.shift(1)),
      "ote_up":(f.low<=f.low.shift(1)+.38*(f.high.shift(1)-f.low.shift(4)))&(f.low>=f.low.shift(1)+.21*(f.high.shift(1)-f.low.shift(4))),
      "ote_down":(f.high>=f.high.shift(1)-.38*(f.high.shift(4)-f.low.shift(1)))&(f.high<=f.high.shift(1)-.21*(f.high.shift(4)-f.low.shift(1))),
      "shock_0_5_1_0":((f.close-f.close.shift()).abs()/f.atr15).between(.5,1.0,inclusive="left"),
      "shock_1_0_1_5":((f.close-f.close.shift()).abs()/f.atr15).between(1.0,1.5,inclusive="left"),
      "shock_1_5_2_0":((f.close-f.close.shift()).abs()/f.atr15).between(1.5,2.0,inclusive="left"),
      "shock_gt_2_0":((f.close-f.close.shift()).abs()/f.atr15)>=2.0,
      "atr_compression":f.atr_pct<=.20, "atr_expansion":f.atr_pct>=.80,
      "h1_atr_compression":f.h1_atr_pct<=.20, "h1_atr_expansion":f.h1_atr_pct>=.80,
    }
    # Small, predeclared interactions.
    masks["fvg_up_h1_up"]=masks["fvg_up"]&f.h1_trend.eq(1); masks["fvg_down_h1_down"]=masks["fvg_down"]&f.h1_trend.eq(-1)
    masks["sweep_low_mss_up"]=masks["asia_sweep_reclaim_low"]&masks["mss_up"]; masks["sweep_high_mss_down"]=masks["asia_sweep_reclaim_high"]&masks["mss_down"]
    for label in ("atr_compression","atr_expansion"):
        for sess in ("london_open","london_body","ny_open","overlap"): masks[f"{label}_{sess}"]=masks[label]&s.eq(sess)
    return masks

def labeled_events(f,pair):
    f=f.copy(); f["session"]=session_code(f); masks=event_masks(f); rows=[]
    for name,mask in masks.items():
        for horizon in HORIZONS:
            valid=mask&f.atr15.notna()&f.close.shift(-horizon).notna()
            z=((f.close.shift(-horizon)-f.close)/f.atr15).where(valid)
            for dt,v in z.dropna().items(): rows.append((name,pair,dt,f.year.loc[dt],horizon,float(v)))
    return pd.DataFrame(rows,columns=["event","pair","dt","year","horizon","forward_atr_return"]), masks

def summarize(x,groups):
    def one(g):
        v=g.forward_atr_return; n=len(v); mean=v.mean(); se=v.std(ddof=1)/np.sqrt(n) if n>1 else np.nan
        return pd.Series({"event_count":n,"mean_forward_return":mean,"median_forward_return":v.median(),"standard_error":se,"t_statistic":mean/se if se and np.isfinite(se) else np.nan,"directional_probability":(v>0).mean(),"p25":v.quantile(.25),"p50":v.quantile(.5),"p75":v.quantile(.75)})
    return x.groupby(groups,dropna=False).apply(one,include_groups=False).reset_index()

def cross_events(root):
    """Strictly synchronized H1 basket/residual events; no forward fill."""
    h={p:read(root/p/f"{p}_bid_h1.csv") for p in PAIRS}
    norm={p:((v.close-v.open)/atr(v)).rename(p) for p,v in h.items()}
    rows=[]
    for members,name,orient in [(USD_DIRECT+USD_INVERSE,"usd",{**{p:-1 for p in USD_DIRECT},**{p:1 for p in USD_INVERSE}}),(JPY,"jpy",{p:-1 for p in JPY})]:
        x=pd.concat([norm[p]*orient[p] for p in members],axis=1,join="inner").dropna(); med=x.median(axis=1); breadth=(x>0).sum(axis=1)-(x<0).sum(axis=1)
        strongest=x.abs().idxmax(axis=1)
        for k in (1,2,4):
            for dt in x.index[:-k]:
                p=strongest.loc[dt]
                rows.append((f"{name}_strongest_forward",p,dt,dt.year,k,float(x[p].shift(-k).loc[dt])))
                rows.append((f"{name}_median_forward",name,dt,dt.year,k,float(med.shift(-k).loc[dt])))
        for dt in x.index: rows.append((f"{name}_breadth",name,dt,dt.year,0,float(breadth.loc[dt])))
    for a,b in (("EURUSD","GBPUSD"),("AUDUSD","NZDUSD"),("EURJPY","GBPJPY")):
        x=pd.concat((norm[a],norm[b]),axis=1,join="inner").dropna(); residual=x[a]-x[b]
        for k in (1,2,4):
            for dt in residual.index[:-k]: rows.append((f"divergence_change_{a}_{b}",a,dt,dt.year,k,float(residual.shift(-k).loc[dt]-residual.loc[dt])))
    return pd.DataFrame(rows,columns=["event","pair","dt","year","horizon","forward_atr_return"])

def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--data",default=str(ROOT/"data_independent/derived_m15")); ap.add_argument("--out",default=str(ROOT/"results_next_strategy/round3a")); ap.add_argument("--pairs",nargs="+",default=list(PAIRS)); args=ap.parse_args()
    out=Path(args.out); out.mkdir(parents=True,exist_ok=True); chunks=[]; counts=[]
    for pair in args.pairs:
        events,masks=labeled_events(prepare(Path(args.data),pair),pair); chunks.append(events)
        counts.extend((name,pair,int(mask.sum())) for name,mask in masks.items())
    chunks.append(cross_events(Path(args.data)))
    x=pd.concat(chunks,ignore_index=True); edge=summarize(x,["event","horizon"]); by_pair=summarize(x,["event","horizon","pair"]); by_year=summarize(x,["event","horizon","year"])
    for z in (edge,by_pair,by_year): z["pair_breadth_same_sign"]=z.groupby(["event","horizon"])["mean_forward_return"].transform(lambda v:(np.sign(v)==np.sign(v.mean())).sum())
    edge.to_csv(out/"edge_map.csv",index=False); by_pair.to_csv(out/"by_pair.csv",index=False); by_year.to_csv(out/"by_year.csv",index=False); pd.DataFrame(counts,columns=["event","pair","event_count"]).to_csv(out/"event_counts.csv",index=False)
    (ROOT/"ROUND3A_EDGE_MAP_REPORT.md").write_text("# Round 3A Edge Map Report\n\nRun `round3a_edge_map.py` to generate descriptive development-only evidence. This is not strategy P&L or a promotion decision.\n",encoding="utf-8")

if __name__=="__main__": main()
