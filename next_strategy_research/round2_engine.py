#!/usr/bin/env python3
"""Deterministic Strategy 2 Round 2 M15/H1 screen.

The runner rejects all rows >= 2021-01-01 so the holdout cannot leak into
preliminary screening. Signals use completed information at T and execute at the
next M15 open with executable BID/ASK pricing and fixed 0.10 pip slippage.
"""
from __future__ import annotations

import argparse
import gc
import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
PAIRS = ("EURUSD","GBPUSD","USDJPY","AUDUSD","NZDUSD","USDCAD","USDCHF","EURJPY","GBPJPY","AUDJPY","CADJPY","CHFJPY","EURGBP","EURAUD","GBPAUD")
USD_DIRECT = ("EURUSD","GBPUSD","AUDUSD","NZDUSD")
USD_INVERSE = ("USDJPY","USDCAD","USDCHF")
USD_BASKET = USD_DIRECT + USD_INVERSE
JPY_BASKET = ("EURJPY","GBPJPY","AUDJPY","CADJPY","CHFJPY")
DEV_START = pd.Timestamp("2013-01-01", tz="UTC")
DEV_END = pd.Timestamp("2018-01-01", tz="UTC")
END = pd.Timestamp("2021-01-01", tz="UTC")
GATE = {"development_expectancy_r":.10,"development_profit_factor":1.15,"validation_expectancy_r":.05,"validation_profit_factor":1.10,"minimum_combined_trades":120,"minimum_positive_pairs":8}
COLS = ("hypothesis","family","pair","signal_dt","entry_dt","exit_dt","side","r","reason","ambiguous_stop_first")

@dataclass(frozen=True)
class Spec:
    hypothesis: str
    family: str

SPECS = tuple(Spec(f"S2R2-{i:02d}", n) for i,n in enumerate((
    "prior_day_value","late_london_exhaustion","ny_opening_drive","post_overlap_drift",
    "two_hour_fade","daily_expansion","usd_basket","jpy_basket",
    "correlation_dislocation","overnight_unwind","realised_trend_pullback","friday_fade"),1))


def pip(pair): return .01 if pair.endswith("JPY") else .0001

def tr(f):
    p=f.close.shift()
    return pd.concat((f.high-f.low,(f.high-p).abs(),(f.low-p).abs()),axis=1).max(axis=1)

def atr(f,n=14): return tr(f).rolling(n,min_periods=n).mean()

def read(path):
    parts=[]
    for x in pd.read_csv(path,usecols=["dt","open","high","low","close","volume"],parse_dates=["dt"],dtype={k:"float32" for k in ("open","high","low","close","volume")},chunksize=40000):
        x["dt"]=pd.to_datetime(x.dt,utc=True)
        parts.append(x[(x.dt>=DEV_START)&(x.dt<END)])
    if not parts: raise RuntimeError(f"no data: {path}")
    return pd.concat(parts,ignore_index=True).set_index("dt").sort_index()


def h1_state(h):
    x=h.copy(); x["h1_atr"]=atr(x); e20=x.close.ewm(span=20,adjust=False).mean(); e50=x.close.ewm(span=50,adjust=False).mean()
    x["h1_trend"]=np.select([(x.close>e20)&(e20>e50),(x.close<e20)&(e20<e50)],[1,-1],default=0)
    x["h1_body"]=(x.close-x.open).abs(); rng=(x.high-x.low).replace(0,np.nan)
    upper=x.high-x[["open","close"]].max(axis=1); lower=x[["open","close"]].min(axis=1)-x.low
    x["h1_wick_share"]=pd.concat((upper,lower),axis=1).max(axis=1)/rng
    x["h1_norm_oc"]=(x.close-x.open)/x.h1_atr; x["available"]=x.index+pd.Timedelta(hours=1)
    return x[["open","high","low","close","h1_atr","h1_trend","h1_body","h1_wick_share","h1_norm_oc","available"]].rename(columns={c:f"h1_{c}" for c in ("open","high","low","close")})


def fixed_window_baseline(f,start_h,end_h,kind):
    mask=(f.index.hour>=start_h)&(f.index.hour<end_h)
    g=f.loc[mask].groupby(f.loc[mask].index.normalize())
    if kind=="volume": v=g.volume.sum()
    else:
        z=g.agg({"high":"max","low":"min"}); v=z.high-z.low
    return f.index.normalize().map(v.shift(1).rolling(20,min_periods=20).median()).astype(float)


def prepare(root,pair):
    d=root/pair; b=read(d/f"{pair}_bid_m15.csv"); a=read(d/f"{pair}_ask_m15.csv"); h=read(d/f"{pair}_bid_h1.csv"); daily=read(d/f"{pair}_bid_d1.csv")
    if not b.index.equals(a.index): raise RuntimeError(f"{pair}: BID/ASK M15 misalignment")
    f=b.add_prefix("bid_").join(a.add_prefix("ask_"))
    for c in ("open","high","low","close","volume"): f[c]=f[f"bid_{c}"]
    f["atr15"]=atr(f); f["hour"]=f.index.hour; f["minute"]=f.index.minute; f["weekday"]=f.index.weekday; f["date"]=f.index.normalize()

    hs=h1_state(h)
    f=pd.merge_asof(f.reset_index(),hs.reset_index(drop=True).sort_values("available"),left_on="dt",right_on="available",direction="backward").set_index("dt")

    dd=daily[["open","high","low","close"]].copy(); dd["available"]=dd.index+pd.Timedelta(days=1)
    dd=dd.rename(columns={c:f"prior_day_{c}" for c in ("open","high","low","close")})
    f=pd.merge_asof(f.reset_index(),dd.reset_index(drop=True).sort_values("available"),left_on="dt",right_on="available",direction="backward").set_index("dt")

    dr=(daily.high-daily.low); dm=pd.DataFrame({"range_med20":dr.shift(1).rolling(20,min_periods=20).median(),"available":daily.index})
    f=pd.merge_asof(f.reset_index(),dm.reset_index(drop=True).sort_values("available"),left_on="dt",right_on="available",direction="backward").set_index("dt")

    f["day_hi_prev"]=f.groupby("date").high.transform(lambda s:s.expanding().max()).shift(1); f["day_lo_prev"]=f.groupby("date").low.transform(lambda s:s.expanding().min()).shift(1)
    f["day_range_prev"]=f.day_hi_prev-f.day_lo_prev
    asia=f.hour<7; london=(f.hour>=7)&(f.hour<16)
    f["asia_hi_prev"]=f.high.where(asia).groupby(f.date).transform(lambda s:s.expanding().max()).shift(1); f["asia_lo_prev"]=f.low.where(asia).groupby(f.date).transform(lambda s:s.expanding().min()).shift(1)
    f["london_hi_prev"]=f.high.where(london).groupby(f.date).transform(lambda s:s.expanding().max()).shift(1); f["london_lo_prev"]=f.low.where(london).groupby(f.date).transform(lambda s:s.expanding().min()).shift(1)
    f["asia_volume_med20"]=fixed_window_baseline(f,0,7,"volume"); f["london_0709_range_med20"]=fixed_window_baseline(f,7,9,"range")

    wk=f.groupby(f.index.to_period("W-SUN")).agg(week_hi=("high","max"),week_lo=("low","min")).shift(1); wk["available"]=wk.index.to_timestamp().tz_localize("UTC")
    f=pd.merge_asof(f.reset_index(),wk.reset_index(drop=True).sort_values("available"),left_on="dt",right_on="available",direction="backward").set_index("dt")
    return f


def synchronized_norm(root,members):
    cols=[]
    for p in members:
        h=read(root/p/f"{p}_bid_h1.csv"); cols.append(((h.close-h.open)/atr(h)).rename(p))
    return pd.concat(cols,axis=1,join="inner").dropna()


def build_cross_maps(root):
    usd=synchronized_norm(root,USD_BASKET); u=pd.DataFrame(index=usd.index)
    for p in USD_DIRECT: u[p]=-usd[p]
    for p in USD_INVERSE: u[p]=usd[p]
    u["count"]=(u>=1.0).sum(axis=1); u["available"]=u.index+pd.Timedelta(hours=1)

    j=synchronized_norm(root,JPY_BASKET); jj=-j; jj["count"]=(jj>=.75).sum(axis=1); jj["available"]=jj.index+pd.Timedelta(hours=1)
    alln=synchronized_norm(root,PAIRS); out={"usd":u,"jpy":jj}
    for pair in PAIRS:
        b,q=pair[:3],pair[3:]; members=[p for p in PAIRS if p!=pair and (b in (p[:3],p[3:]) or q in (p[:3],p[3:]))]
        x=alln[[pair]+members].copy(); x["basket_median"]=x[members].median(axis=1); x["residual"]=x[pair]-x.basket_median; x["available"]=x.index+pd.Timedelta(hours=1)
        out[f"dis:{pair}"]=x[[pair,"basket_median","residual","available"]]
    return out


def attach_cross(f,pair,maps):
    out=f.reset_index().sort_values("dt")
    for key,prefix in (("usd","usd_"),("jpy","jpy_"),(f"dis:{pair}","dis_")):
        x=maps[key].rename(columns={c:prefix+c for c in maps[key].columns if c!="available"})
        out=pd.merge_asof(out,x.reset_index(drop=True).sort_values("available"),left_on="dt",right_on="available",direction="backward").drop(columns="available")
    return out.set_index("dt")


def sided(long,short): return np.where(long.fillna(False),1,np.where(short.fillna(False),-1,0))


def sig(f,pair,fam):
    h,m=f.hour,f.minute; bull=f.close>f.open; bear=f.close<f.open; neutral=f.h1_trend.eq(0)
    if fam=="prior_day_value":
        w=(h==5)|(h==6); ext=.75*f.atr15
        return sided(w&neutral&(f.low<f.prior_day_close-ext)&(f.close>=f.prior_day_close-ext)&bull,w&neutral&(f.high>f.prior_day_close+ext)&(f.close<=f.prior_day_close+ext)&bear)
    if fam=="late_london_exhaustion":
        w=(h==14)|(h==15); e=f.day_range_prev>=1.25*f.range_med20
        return sided(w&e&(f.low<f.london_lo_prev)&(f.close>f.london_lo_prev),w&e&(f.high>f.london_hi_prev)&(f.close<f.london_hi_prev))
    if fam=="ny_opening_drive":
        drive=(f.h1_body>=.9*f.h1_atr)&(f.h1_wick_share<=.25); d=np.sign(f.h1_close-f.h1_open); aligned=d==f.h1_trend; impulse=(f.h1_close-f.h1_open).abs()
        retr=np.where(d>0,(f.h1_close-f.close)/impulse,np.where(d<0,(f.close-f.h1_close)/impulse,np.nan)); shallow=(retr>=.25)&(retr<=.50); w=(h==14)|(h==15)
        return sided(w&drive&aligned&(d>0)&shallow&(f.close>f.high.shift(1)),w&drive&aligned&(d<0)&shallow&(f.close<f.low.shift(1)))
    if fam=="post_overlap_drift":
        w=((h==14)|(h==15))&~((h==15)&(m>30)); side=np.sign(f.close.shift(1)-f.prior_day_close)
        l=side.rolling(8,min_periods=8).apply(lambda x:1 if np.all(x>0) else (-1 if np.all(x<0) else 0)); n=side.rolling(4,min_periods=4).apply(lambda x:1 if np.all(x>0) else (-1 if np.all(x<0) else 0)); d=np.where((l==n)&(l!=0),l,0)
        return sided(w&(d==1)&(f.close>f.high.shift(1).rolling(4).max()),w&(d==-1)&(f.close<f.low.shift(1).rolling(4).min()))
    if fam=="two_hour_fade":
        day=f.date; mask=(h>=7)&(h<9); orh=f.high.where(mask).groupby(day).transform("max"); orl=f.low.where(mask).groupby(day).transform("min"); narrow=(orh-orl)<=.8*f.london_0709_range_med20; w=(h==9)|(h==10)
        up=(f.high>orh).astype(int); dn=(f.low<orl).astype(int); pu=up.groupby(day).cumsum().shift(1).fillna(0)>=1; pdn=dn.groupby(day).cumsum().shift(1).fillna(0)>=1
        return sided(w&narrow&pdn&(f.low<orl)&(f.close>orl),w&narrow&pu&(f.high>orh)&(f.close<orh))
    if fam=="daily_expansion":
        w=(h>=10)&(h<=12); quiet=f.day_range_prev<=.55*f.range_med20; long=w&quiet&(f.close>f.prior_day_high)&f.h1_trend.eq(1); short=w&quiet&(f.close<f.prior_day_low)&f.h1_trend.eq(-1)
        breadth=(f.usd_count>=3) if pair in USD_BASKET else ((f.jpy_count>=3) if pair in JPY_BASKET else pd.Series(False,index=f.index))
        return sided(long&breadth,short&breadth)
    if fam=="usd_basket":
        if pair not in USD_BASKET: return np.zeros(len(f),dtype=int)
        return np.where(f.usd_count>=3,-1 if pair in USD_DIRECT else 1,0)
    if fam=="jpy_basket":
        if pair not in JPY_BASKET: return np.zeros(len(f),dtype=int)
        return np.where((f.jpy_count>=3)&(f.close<f.low.shift(1)),-1,0)
    if fam=="correlation_dislocation":
        mid=(f.h1_open+f.h1_close)/2; first=m.eq(0)
        return sided(first&(f.dis_residual<=-1.5)&(f.close>=mid),first&(f.dis_residual>=1.5)&(f.close<=mid))
    if fam=="overnight_unwind":
        ao=f.open.where((h==0)&(m==0)).groupby(f.date).transform("first"); ac=f.close.where((h==6)&(m==45)).groupby(f.date).transform("last"); av=f.volume.where(h<7).groupby(f.date).transform("sum"); move=(ac-ao)/f.h1_atr; low=av<=f.asia_volume_med20; w=(h==7)|(h==8)
        return sided(w&low&(move<=-.8)&(f.low<f.asia_lo_prev)&(f.close>f.asia_lo_prev),w&low&(move>=.8)&(f.high>f.asia_hi_prev)&(f.close<f.asia_hi_prev))
    if fam=="realised_trend_pullback":
        w=(h>=10)&(h<=14); e=f.day_range_prev>=.9*f.range_med20; o=f.open.groupby(f.date).transform("first"); up=(f.day_hi_prev-o).replace(0,np.nan); dn=(o-f.day_lo_prev).replace(0,np.nan); ur=(f.day_hi_prev-f.close)/up; dr=(f.close-f.day_lo_prev)/dn
        return sided(w&e&f.h1_trend.eq(1)&ur.between(.382,.618)&bull,w&e&f.h1_trend.eq(-1)&dr.between(.382,.618)&bear)
    if fam=="friday_fade":
        w=f.weekday.eq(4)&(h>=13)&(h<=15); c1,c2,c3=f.close.shift(3),f.close.shift(2),f.close.shift(1); up=(c1<c2)&(c2<c3); dn=(c1>c2)&(c2>c3); mid=(f.open.shift(1)+f.close.shift(1))/2
        return sided(w&dn&(f.low.shift(1).rolling(3).min()>=f.week_lo)&(f.close>mid),w&up&(f.high.shift(1).rolling(3).max()<=f.week_hi)&(f.close<mid))
    raise ValueError(fam)


def execute(f,pair,spec):
    s=sig(f,pair,spec.family); slip=.10*pip(pair); out=[]; ok=pd.Timestamp.min.tz_localize("UTC"); ix=f.index; av=f.atr15.to_numpy(); bo,ao=f.bid_open.to_numpy(),f.ask_open.to_numpy(); bh,bl,bc=f.bid_high.to_numpy(),f.bid_low.to_numpy(),f.bid_close.to_numpy(); ah,al,ac=f.ask_high.to_numpy(),f.ask_low.to_numpy(),f.ask_close.to_numpy()
    for i in np.flatnonzero(s):
        if i+1>=len(f) or ix[i]<DEV_START or ix[i]>=END or ix[i]<ok or not np.isfinite(av[i]): continue
        side=int(s[i]); entry=float(ao[i+1]+slip if side==1 else bo[i+1]-slip); risk=1.25*float(av[i]); stop=entry-side*risk; target=entry+side*1.5*risk; px=None; reason="TIME"; amb=False; jend=min(i+24,len(f)-1)
        for j in range(i+1,jend+1):
            if ix[j].weekday()==4 and ix[j].hour>=16: jend=j; reason="FRIDAY"; break
            hi=float(bh[j] if side==1 else ah[j]); lo=float(bl[j] if side==1 else al[j]); sh=lo<=stop if side==1 else hi>=stop; th=hi>=target if side==1 else lo<=target
            if sh or th: jend=j; amb=sh and th; reason="SL" if sh else "TP"; px=stop if sh else target; break
        if px is None: px=float(bc[jend]-slip if side==1 else ac[jend]+slip)
        out.append((spec.hypothesis,spec.family,pair,ix[i],ix[i+1],ix[jend],side,side*(px-entry)/risk,reason,amb)); ok=ix[jend]
    return pd.DataFrame(out,columns=COLS)


def pf(r):
    gp=r[r>0].sum(); gl=-r[r<0].sum(); return float(gp/gl) if gl>0 else (float("inf") if gp>0 else 0.0)

def summarize(t):
    rows=[]
    for s in SPECS:
        x=t[t.hypothesis==s.hypothesis]; d=x[x.signal_dt<DEV_END]; v=x[x.signal_dt>=DEV_END]; pe=x.groupby("pair").r.mean()
        rows.append({"hypothesis":s.hypothesis,"family":s.family,"development_trades":len(d),"development_expectancy_r":d.r.mean() if len(d) else np.nan,"development_profit_factor":pf(d.r) if len(d) else np.nan,"validation_trades":len(v),"validation_expectancy_r":v.r.mean() if len(v) else np.nan,"validation_profit_factor":pf(v.r) if len(v) else np.nan,"combined_trades":len(x),"positive_pairs":int((pe>0).sum())})
    z=pd.DataFrame(rows); z["passes_gate"]=(z.development_expectancy_r>=GATE["development_expectancy_r"])&(z.development_profit_factor>=GATE["development_profit_factor"])&(z.validation_expectancy_r>=GATE["validation_expectancy_r"])&(z.validation_profit_factor>=GATE["validation_profit_factor"])&(z.combined_trades>=GATE["minimum_combined_trades"])&(z.positive_pairs>=GATE["minimum_positive_pairs"]); return z


def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--data",default=str(ROOT/"data_independent/derived_m15")); ap.add_argument("--out",default=str(ROOT/"results_next_strategy/round2")); ap.add_argument("--pairs",nargs="+",default=list(PAIRS)); a=ap.parse_args(); root=Path(a.data); out=Path(a.out); out.mkdir(parents=True,exist_ok=True); maps=build_cross_maps(root); all_t=[]
    for pair in a.pairs:
        f=attach_cross(prepare(root,pair),pair,maps)
        for spec in SPECS:
            t=execute(f,pair,spec); t.to_csv(out/f"checkpoint_{pair}_{spec.hypothesis}.csv",index=False); all_t.append(t)
        del f; gc.collect()
    t=pd.concat(all_t,ignore_index=True) if all_t else pd.DataFrame(columns=COLS); t.to_csv(out/"trades.csv",index=False); s=summarize(t); s.to_csv(out/"screen.csv",index=False); json.dump(GATE,open(out/"gate.json","w"),indent=2); print(s.to_string(index=False))

if __name__=="__main__": main()
