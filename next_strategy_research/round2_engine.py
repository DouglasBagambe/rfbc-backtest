#!/usr/bin/env python3
"""Frozen Round 2 M15/H1 engine.  It deliberately rejects all data >= 2021."""
from __future__ import annotations

import argparse
import gc
from dataclasses import dataclass
from pathlib import Path
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
PAIRS=("EURUSD","GBPUSD","USDJPY","AUDUSD","NZDUSD","USDCAD","USDCHF","EURJPY","GBPJPY","AUDJPY","CADJPY","CHFJPY","EURGBP","EURAUD","GBPAUD")
DEV_END=pd.Timestamp("2018-01-01",tz="UTC"); END=pd.Timestamp("2021-01-01",tz="UTC")
GATE={"development_expectancy_r":.10,"development_profit_factor":1.15,"validation_expectancy_r":.05,"validation_profit_factor":1.10,"minimum_combined_trades":120,"minimum_positive_pairs":8}
COLS=("hypothesis","family","pair","signal_dt","entry_dt","exit_dt","side","r","reason","ambiguous_stop_first")
@dataclass(frozen=True)
class Spec: hypothesis:str; family:str
SPECS=tuple(Spec(f"S2R2-{i:02d}",n) for i,n in enumerate(("prior_day_value","late_london_exhaustion","ny_opening_drive","post_overlap_drift","two_hour_fade","daily_expansion","usd_basket","jpy_basket","correlation_dislocation","overnight_unwind","realised_trend_pullback","friday_fade"),1))

def pip(pair): return .01 if pair.endswith("JPY") else .0001
def atr(f,n=14):
 p=f.close.shift(); return pd.concat((f.high-f.low,(f.high-p).abs(),(f.low-p).abs()),axis=1).max(axis=1).rolling(n).mean().shift()
def read(path):
 parts=[]
 for x in pd.read_csv(path,usecols=["dt","open","high","low","close","volume"],parse_dates=["dt"],dtype={k:"float32" for k in ("open","high","low","close","volume")},chunksize=40000): parts.append(x[x.dt<END])
 f=pd.concat(parts,ignore_index=True); f.dt=pd.to_datetime(f.dt,utc=True); return f.set_index("dt").sort_index()
def synchronized_normalized_h1(root, members):
 """Strict inner join: an absent member bar invalidates that timestamp."""
 cols=[]
 for pair in members:
  h=read(root/pair/f"{pair}_bid_h1.csv"); h["atr"]=atr(h); h["norm"]=(h.close-h.open)/h.atr
  cols.append(h[["norm"]].rename(columns={"norm":pair}))
 return pd.concat(cols,axis=1,join="inner").dropna()
def basket_median(root,members,invert=()):
 x=synchronized_normalized_h1(root,members).copy()
 for pair in invert: x[pair]=-x[pair]
 return x.assign(basket=x.median(axis=1))
def basket_candidate(row, threshold):
 eligible=row.drop(labels="basket"); eligible=eligible[eligible.abs()>=threshold]
 return None if eligible.empty else eligible.abs().idxmax()
def prepare(root,pair):
 d=root/pair; b=read(d/f"{pair}_bid_m15.csv"); a=read(d/f"{pair}_ask_m15.csv"); h=read(d/f"{pair}_bid_h1.csv"); daily=read(d/f"{pair}_bid_d1.csv")
 if not b.index.equals(a.index): raise RuntimeError(f"{pair} BID/ASK misalignment")
 f=b.add_prefix("bid_").join(a.add_prefix("ask_"));
 for c in ("open","high","low","close","volume"): f[c]=f[f"bid_{c}"]
 f["atr"]=atr(f); f["hour"]=f.index.hour; f["weekday"]=f.index.weekday; f["date"]=f.index.normalize(); f["tr"]=pd.concat((f.high-f.low,(f.high-f.close.shift()).abs(),(f.low-f.close.shift()).abs()),axis=1).max(axis=1)
 f["day_range"]=f.groupby("date").tr.transform(lambda x:x.expanding().sum()).shift(); f["range_med20"]=f["day_range"].shift().rolling(20*96,min_periods=96).median()
 f["prior_day_close"]=pd.merge_asof(f.reset_index(),daily[["close"]].shift().rename(columns={"close":"prior_day_close"}).assign(avail=daily.index+pd.Timedelta(days=1)).reset_index(drop=True).sort_values("avail"),left_on="dt",right_on="avail",direction="backward").set_index("dt")["prior_day_close"]
 h["atr"]=atr(h); h["ret"]=h.close.pct_change(); h["trend"]=np.where(h.close>h.close.ewm(span=20,adjust=False).mean(),1,-1); h["available"]=h.index+pd.Timedelta(hours=1)
 f=pd.merge_asof(f.reset_index().sort_values("dt"),h[["ret","atr","trend","available"]].reset_index(drop=True).sort_values("available"),left_on="dt",right_on="available",direction="backward").set_index("dt")
 f["asia_hi"]=f.groupby("date").high.transform(lambda x:x.where(x.index.hour<7).expanding().max()).shift(); f["asia_lo"]=f.groupby("date").low.transform(lambda x:x.where(x.index.hour<7).expanding().min()).shift()
 f["london_hi"]=f.groupby("date").high.transform(lambda x:x.where((x.index.hour>=7)&(x.index.hour<14)).expanding().max()).shift(); f["london_lo"]=f.groupby("date").low.transform(lambda x:x.where((x.index.hour>=7)&(x.index.hour<14)).expanding().min()).shift()
 return f
def sig(f,fam):
 bull=f.close>f.open; bear=f.close<f.open; neutral=f.trend.eq(0); h=f.hour
 if fam=="prior_day_value": return np.where((h.between(5,6)&neutral&(f.close<f.prior_day_close-.75*f.atr)&bull),1,np.where(h.between(5,6)&neutral&(f.close>f.prior_day_close+.75*f.atr)&bear,-1,0))
 if fam=="late_london_exhaustion": return np.where(h.between(14,15)&(f.day_range>=1.25*f.range_med20)&(f.high>f.london_hi)&(f.close<f.london_hi),-1,np.where(h.between(14,15)&(f.day_range>=1.25*f.range_med20)&(f.low<f.london_lo)&(f.close>f.london_lo),1,0))
 if fam=="ny_opening_drive": return np.where(h.between(14,16)&(f.trend==1)&bull&(f.close>f.close.shift(4)),1,np.where(h.between(14,16)&(f.trend==-1)&bear&(f.close<f.close.shift(4)),-1,0))
 if fam=="post_overlap_drift": return np.where(h.between(14,15)&(f.close>f.prior_day_close)&(f.close>f.high.shift().rolling(4).max()),1,np.where(h.between(14,15)&(f.close<f.prior_day_close)&(f.close<f.low.shift().rolling(4).min()),-1,0))
 if fam=="two_hour_fade": return np.where(h.between(9,10)&(f.high>f.asia_hi)&(f.close<f.asia_hi),-1,np.where(h.between(9,10)&(f.low<f.asia_lo)&(f.close>f.asia_lo),1,0))
 if fam=="daily_expansion": return np.where(h.between(10,12)&(f.day_range<=.55*f.range_med20)&(f.close>f.prior_day_close)&(f.trend==1),1,np.where(h.between(10,12)&(f.day_range<=.55*f.range_med20)&(f.close<f.prior_day_close)&(f.trend==-1),-1,0))
 if fam in ("usd_basket","jpy_basket","correlation_dislocation"): return np.zeros(len(f),dtype=int) # attached only after timestamp-safe basket construction
 if fam=="overnight_unwind": return np.where(h.between(7,8)&(f.close>f.asia_lo)&(f.low<f.asia_lo),1,np.where(h.between(7,8)&(f.close<f.asia_hi)&(f.high>f.asia_hi),-1,0))
 if fam=="realised_trend_pullback": return np.where(h.between(10,14)&(f.day_range>=.9*f.range_med20)&(f.trend==1)&bull,1,np.where(h.between(10,14)&(f.day_range>=.9*f.range_med20)&(f.trend==-1)&bear,-1,0))
 if fam=="friday_fade": return np.where((f.weekday==4)&h.between(13,15)&bear,-1,np.where((f.weekday==4)&h.between(13,15)&bull,1,0))
 raise ValueError(fam)
def execute(f,pair,spec):
 s=sig(f,spec.family); out=[]; ok=pd.Timestamp.min.tz_localize("UTC"); ix=f.index
 for i in np.flatnonzero(s):
  if i+1>=len(f) or ix[i]>=END or ix[i]<ok or not np.isfinite(f.atr.iat[i]): continue
  side=int(s[i]); sl=.1*pip(pair); entry=float(f.ask_open.iat[i+1]+sl if side==1 else f.bid_open.iat[i+1]-sl); risk=1.25*float(f.atr.iat[i]); stop=entry-side*risk; target=entry+side*1.5*risk; px=None; reason="TIME"; amb=False; jend=min(i+24,len(f)-1)
  for j in range(i+1,jend+1):
   if ix[j].weekday()==4 and ix[j].hour>=16: jend=j; reason="FRIDAY"; break
   hi=float(f.bid_high.iat[j] if side==1 else f.ask_high.iat[j]); lo=float(f.bid_low.iat[j] if side==1 else f.ask_low.iat[j]); sh=lo<=stop if side==1 else hi>=stop; th=hi>=target if side==1 else lo<=target
   if sh or th: jend=j; amb=sh and th; reason="SL" if sh else "TP"; px=stop if sh else target; break
  if px is None: px=float(f.bid_close.iat[jend]-sl if side==1 else f.ask_close.iat[jend]+sl)
  out.append((spec.hypothesis,spec.family,pair,ix[i],ix[i+1],ix[jend],side,side*(px-entry)/risk,reason,amb)); ok=ix[jend]
 return pd.DataFrame(out,columns=COLS)
def main():
 ap=argparse.ArgumentParser(); ap.add_argument("--data",default=str(ROOT/"data_independent/derived_m15")); ap.add_argument("--out",default=str(ROOT/"results_next_strategy/round2")); ap.add_argument("--pairs",nargs="+",default=PAIRS); a=ap.parse_args(); out=Path(a.out); out.mkdir(parents=True,exist_ok=True)
 for pair in a.pairs:
  f=prepare(Path(a.data),pair)
  for x in SPECS: execute(f,pair,x).to_csv(out/f"checkpoint_{pair}_{x.hypothesis}.csv",index=False)
  del f; gc.collect()
if __name__=="__main__": main()
