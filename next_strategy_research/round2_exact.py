#!/usr/bin/env python3
"""Exact deterministic Strategy 2 Round 2 screening engine.

Internal screen only: 2013-01-01 <= timestamp < 2021-01-01. The 2021+ holdout
is excluded in the reader before any feature construction.
"""
from __future__ import annotations

import argparse
import gc
import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
PAIRS=("EURUSD","GBPUSD","USDJPY","AUDUSD","NZDUSD","USDCAD","USDCHF","EURJPY","GBPJPY","AUDJPY","CADJPY","CHFJPY","EURGBP","EURAUD","GBPAUD")
USD_DIRECT=("EURUSD","GBPUSD","AUDUSD","NZDUSD")
USD_INVERSE=("USDJPY","USDCAD","USDCHF")
USD_BASKET=USD_DIRECT+USD_INVERSE
JPY_BASKET=("EURJPY","GBPJPY","AUDJPY","CADJPY","CHFJPY")
DEV_START=pd.Timestamp("2013-01-01",tz="UTC")
DEV_END=pd.Timestamp("2018-01-01",tz="UTC")
END=pd.Timestamp("2021-01-01",tz="UTC")
GATE={"development_expectancy_r":.10,"development_profit_factor":1.15,"validation_expectancy_r":.05,"validation_profit_factor":1.10,"minimum_combined_trades":120,"minimum_positive_pairs":8}
COLS=("hypothesis","family","pair","signal_dt","entry_dt","exit_dt","side","r","reason","ambiguous_stop_first")

@dataclass(frozen=True)
class Spec:
    hypothesis:str
    family:str

SPECS=tuple(Spec(f"S2R2-{i:02d}",n) for i,n in enumerate((
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
    x["h1_norm_oc"]=(x.close-x.open)/x.h1_atr
    x["available"]=x.index+pd.Timedelta(hours=1)
    return x


def fixed_window_baseline(f,start_h,end_h,kind):
    mask=(f.index.hour>=start_h)&(f.index.hour<end_h); g=f.loc[mask].groupby(f.loc[mask].index.normalize())
    if kind=="volume": v=g.volume.sum()
    else:
        z=g.agg({"high":"max","low":"min"}); v=z.high-z.low
    return f.index.normalize().map(v.shift(1).rolling(20,min_periods=20).median()).astype(float)


def _merge_available(left,right,prefix=None):
    r=right.copy()
    if prefix:
        r=r.rename(columns={c:prefix+c for c in r.columns if c!="available"})
    out=pd.merge_asof(left.reset_index().sort_values("dt"),r.reset_index(drop=True).sort_values("available"),left_on="dt",right_on="available",direction="backward")
    return out.drop(columns="available").set_index("dt")


def _freeze_expansion(f):
    f["r2_impulse_dir"]=0; f["r2_impulse_open"]=np.nan; f["r2_impulse_extreme"]=np.nan; f["r2_impulse_time"]=pd.NaT
    for day,idx in f.groupby("date").groups.items():
        pos=f.index.get_indexer(idx); o=float(f.open.iloc[pos[0]]); hi=-np.inf; lo=np.inf; frozen=False
        for j in pos:
            hi=max(hi,float(f.high.iloc[j])); lo=min(lo,float(f.low.iloc[j]))
            if frozen: continue
            med=f.range_med20.iloc[j]
            if not np.isfinite(med) or hi-lo < .9*float(med): continue
            trend=int(f.h1_trend.iloc[j]) if np.isfinite(f.h1_trend.iloc[j]) else 0
            if trend==1 and float(f.high.iloc[j])>=hi:
                f.iloc[j:,f.columns.get_loc("r2_impulse_dir")]=np.where(f.date.iloc[j:]==day,1,f.r2_impulse_dir.iloc[j:])
                f.iloc[j:,f.columns.get_loc("r2_impulse_open")]=np.where(f.date.iloc[j:]==day,o,f.r2_impulse_open.iloc[j:])
                f.iloc[j:,f.columns.get_loc("r2_impulse_extreme")]=np.where(f.date.iloc[j:]==day,hi,f.r2_impulse_extreme.iloc[j:])
                f.loc[f.index[j]:, "r2_impulse_time"]=f["r2_impulse_time"].loc[f.index[j]:].where(f.date.loc[f.index[j]:]!=day,f.index[j]); frozen=True
            elif trend==-1 and float(f.low.iloc[j])<=lo:
                f.iloc[j:,f.columns.get_loc("r2_impulse_dir")]=np.where(f.date.iloc[j:]==day,-1,f.r2_impulse_dir.iloc[j:])
                f.iloc[j:,f.columns.get_loc("r2_impulse_open")]=np.where(f.date.iloc[j:]==day,o,f.r2_impulse_open.iloc[j:])
                f.iloc[j:,f.columns.get_loc("r2_impulse_extreme")]=np.where(f.date.iloc[j:]==day,lo,f.r2_impulse_extreme.iloc[j:])
                f.loc[f.index[j]:, "r2_impulse_time"]=f["r2_impulse_time"].loc[f.index[j]:].where(f.date.loc[f.index[j]:]!=day,f.index[j]); frozen=True
    return f


def prepare(root,pair):
    d=root/pair; b=read(d/f"{pair}_bid_m15.csv"); a=read(d/f"{pair}_ask_m15.csv"); h=read(d/f"{pair}_bid_h1.csv"); daily=read(d/f"{pair}_bid_d1.csv")
    if not b.index.equals(a.index): raise RuntimeError(f"{pair}: BID/ASK M15 misalignment")
    f=b.add_prefix("bid_").join(a.add_prefix("ask_"))
    for c in ("open","high","low","close","volume"): f[c]=f[f"bid_{c}"]
    f["atr15"]=atr(f); f["hour"]=f.index.hour; f["minute"]=f.index.minute; f["weekday"]=f.index.weekday; f["date"]=f.index.normalize()

    hs=h1_state(h)
    general=hs[["open","high","low","close","h1_atr","h1_trend","h1_body","h1_wick_share","h1_norm_oc","available"]]
    f=_merge_available(f,general,"h1_")

    ny=hs[hs.index.hour==13][["open","high","low","close","h1_atr","h1_trend","h1_body","h1_wick_share","available"]].copy(); ny["ny_date"]=ny.index.normalize()
    f=_merge_available(f,ny,"ny13_")

    dd=daily[["open","high","low","close"]].copy(); dd["available"]=dd.index+pd.Timedelta(days=1)
    f=_merge_available(f,dd,"prior_day_")

    dr=daily.high-daily.low; dm=pd.DataFrame({"range_med20":dr.shift(1).rolling(20,min_periods=20).median(),"available":daily.index})
    f=_merge_available(f,dm)

    f["day_hi_prev"]=f.groupby("date").high.transform(lambda s:s.expanding().max()).shift(1); f["day_lo_prev"]=f.groupby("date").low.transform(lambda s:s.expanding().min()).shift(1); f["day_range_prev"]=f.day_hi_prev-f.day_lo_prev
    asia=f.hour<7; london=(f.hour>=7)&(f.hour<16)
    f["asia_hi_prev"]=f.high.where(asia).groupby(f.date).transform(lambda s:s.expanding().max()).shift(1); f["asia_lo_prev"]=f.low.where(asia).groupby(f.date).transform(lambda s:s.expanding().min()).shift(1)
    f["london_hi_prev"]=f.high.where(london).groupby(f.date).transform(lambda s:s.expanding().max()).shift(1); f["london_lo_prev"]=f.low.where(london).groupby(f.date).transform(lambda s:s.expanding().min()).shift(1)
    f["asia_volume_med20"]=fixed_window_baseline(f,0,7,"volume"); f["london_0709_range_med20"]=fixed_window_baseline(f,7,9,"range")

    wk=f.index.to_period("W-SUN"); f["week_hi_prev"]=f.high.groupby(wk).transform(lambda s:s.expanding().max()).shift(1); f["week_lo_prev"]=f.low.groupby(wk).transform(lambda s:s.expanding().min()).shift(1)
    f["new_week_extreme"]=(f.high>f.week_hi_prev)|(f.low<f.week_lo_prev)
    return _freeze_expansion(f)


def synchronized_norm(root,members):
    cols=[]
    for p in members:
        h=read(root/p/f"{p}_bid_h1.csv"); cols.append(((h.close-h.open)/atr(h)).rename(p))
    return pd.concat(cols,axis=1,join="inner").dropna()


def build_cross_maps(root):
    usd=synchronized_norm(root,USD_BASKET); u=pd.DataFrame(index=usd.index)
    for p in USD_DIRECT: u[p]=-usd[p]
    for p in USD_INVERSE: u[p]=usd[p]
    u["strong_count"]=(u[USD_BASKET]>=1.0).sum(axis=1); u["weak_count"]=(u[USD_BASKET]<=-1.0).sum(axis=1); u["source_h1"]=u.index; u["available"]=u.index+pd.Timedelta(hours=1)

    j=synchronized_norm(root,JPY_BASKET); jj=-j; jj["strong_count"]=(jj[JPY_BASKET]>=.75).sum(axis=1); jj["weak_count"]=(jj[JPY_BASKET]<=-.75).sum(axis=1); jj["source_h1"]=jj.index; jj["available"]=jj.index+pd.Timedelta(hours=1)

    alln=synchronized_norm(root,PAIRS); out={"usd":u,"jpy":jj}
    for pair in PAIRS:
        b,q=pair[:3],pair[3:]; members=[p for p in PAIRS if p!=pair and (b in (p[:3],p[3:]) or q in (p[:3],p[3:]))]
        x=alln[[pair]+members].copy(); x["basket_median"]=x[members].median(axis=1); x["residual"]=x[pair]-x.basket_median; x["source_h1"]=x.index; x["available"]=x.index+pd.Timedelta(hours=1)
        out[f"dis:{pair}"]=x[[pair,"basket_median","residual","source_h1","available"]]
    return out


def attach_cross(f,pair,maps):
    f=_merge_available(f,maps["usd"],"usd_"); f=_merge_available(f,maps["jpy"],"jpy_"); return _merge_available(f,maps[f"dis:{pair}"],"dis_")


def sided(long,short):
    long=pd.Series(long,index=long.index if hasattr(long,"index") else None).fillna(False) if not isinstance(long,pd.Series) else long.fillna(False)
    short=pd.Series(short,index=short.index if hasattr(short,"index") else None).fillna(False) if not isinstance(short,pd.Series) else short.fillna(False)
    return np.where(long,1,np.where(short,-1,0))


def _first_true_per_group(mask,group):
    m=pd.Series(mask,index=group.index).fillna(False)
    return m & (m.groupby(group).cumsum()==1)


def sig(f,pair,fam):
    h,m=f.hour,f.minute; bull=f.close>f.open; bear=f.close<f.open; neutral=f.h1_h1_trend.eq(0)
    if fam=="prior_day_value":
        w=(h==5)|(h==6); ext=.75*f.atr15
        return sided(w&neutral&(f.low<f.prior_day_close-ext)&(f.close>=f.prior_day_close-ext)&bull,w&neutral&(f.high>f.prior_day_close+ext)&(f.close<=f.prior_day_close+ext)&bear)
    if fam=="late_london_exhaustion":
        w=(h==14)|(h==15); e=f.day_range_prev>=1.25*f.range_med20
        return sided(w&e&(f.low<f.london_lo_prev)&(f.close>f.london_lo_prev),w&e&(f.high>f.london_hi_prev)&(f.close<f.london_hi_prev))
    if fam=="ny_opening_drive":
        same_day=f.ny13_ny_date.eq(f.date); d=np.sign(f.ny13_close-f.ny13_open); valid=same_day&(f.ny13_h1_body>=.9*f.ny13_h1_atr)&(f.ny13_h1_wick_share<=.25)&(d==f.ny13_h1_trend)&((h==14)|(h==15)); impulse=(f.ny13_close-f.ny13_open).abs()
        retr=np.where(d>0,(f.ny13_close-f.close)/impulse,np.where(d<0,(f.close-f.ny13_close)/impulse,np.nan)); pull=valid&(retr>=.25)&(retr<=.50)
        armed=pull.groupby(f.date).transform(lambda s:s.shift(1).cummax().fillna(False)); raw_long=armed&(d>0)&(f.close>f.ny13_high); raw_short=armed&(d<0)&(f.close<f.ny13_low)
        return sided(_first_true_per_group(raw_long,f.date),_first_true_per_group(raw_short,f.date))
    if fam=="post_overlap_drift":
        w=((h==14)|(h==15))&~((h==15)&(m>30)); side=np.sign(f.close.shift(1)-f.prior_day_close); ls=side.rolling(8,min_periods=8).apply(lambda x:1 if np.all(x>0) else (-1 if np.all(x<0) else 0)); ns=side.rolling(4,min_periods=4).apply(lambda x:1 if np.all(x>0) else (-1 if np.all(x<0) else 0)); d=np.where((ls==ns)&(ls!=0),ls,0)
        return sided(w&(d==1)&(f.close>f.high.shift(1).rolling(4).max()),w&(d==-1)&(f.close<f.low.shift(1).rolling(4).min()))
    if fam=="two_hour_fade":
        mask=(h>=7)&(h<9); orh=f.high.where(mask).groupby(f.date).transform("max"); orl=f.low.where(mask).groupby(f.date).transform("min"); narrow=(orh-orl)<=.8*f.london_0709_range_med20; w=(h==9)|(h==10); up=(f.high>orh).astype(int); dn=(f.low<orl).astype(int); pu=up.groupby(f.date).cumsum().shift(1).fillna(0)>=1; pdn=dn.groupby(f.date).cumsum().shift(1).fillna(0)>=1
        return sided(w&narrow&pdn&(f.low<orl)&(f.close>orl),w&narrow&pu&(f.high>orh)&(f.close<orh))
    if fam=="daily_expansion":
        w=(h>=10)&(h<=12); quiet=f.day_range_prev<=.55*f.range_med20; long=w&quiet&(f.close>f.prior_day_high)&f.h1_h1_trend.eq(1); short=w&quiet&(f.close<f.prior_day_low)&f.h1_h1_trend.eq(-1)
        if pair in USD_DIRECT: long&=f.usd_weak_count>=3; short&=f.usd_strong_count>=3
        elif pair in USD_INVERSE: long&=f.usd_strong_count>=3; short&=f.usd_weak_count>=3
        elif pair in JPY_BASKET: long&=f.jpy_weak_count>=3; short&=f.jpy_strong_count>=3
        else: return np.zeros(len(f),dtype=int)
        return sided(long,short)
    if fam=="usd_basket":
        if pair not in USD_BASKET: return np.zeros(len(f),dtype=int)
        active=(f.usd_strong_count>=3)&m.eq(0); return np.where(active,-1 if pair in USD_DIRECT else 1,0)
    if fam=="jpy_basket":
        if pair not in JPY_BASKET: return np.zeros(len(f),dtype=int)
        raw=(f.jpy_strong_count>=3)&(f.close<f.low.shift(1)); first=_first_true_per_group(raw,f.jpy_source_h1); return np.where(first,-1,0)
    if fam=="correlation_dislocation":
        mid=(f.h1_open+f.h1_close)/2; first=m.eq(0); return sided(first&(f.dis_residual<=-1.5)&(f.close>=mid),first&(f.dis_residual>=1.5)&(f.close<=mid))
    if fam=="overnight_unwind":
        ao=f.open.where((h==0)&(m==0)).groupby(f.date).transform("first"); ac=f.close.where((h==6)&(m==45)).groupby(f.date).transform("last"); av=f.volume.where(h<7).groupby(f.date).transform("sum"); move=(ac-ao)/f.h1_h1_atr; low=av<=f.asia_volume_med20; w=(h==7)|((h==8)&(m<=30))
        return sided(w&low&(move<=-.8)&(f.low<f.asia_lo_prev)&(f.close>f.asia_lo_prev),w&low&(move>=.8)&(f.high>f.asia_hi_prev)&(f.close<f.asia_hi_prev))
    if fam=="realised_trend_pullback":
        after=pd.to_datetime(f.r2_impulse_time,utc=True,errors="coerce")<f.index; upmove=(f.r2_impulse_extreme-f.r2_impulse_open).replace(0,np.nan); dnmove=(f.r2_impulse_open-f.r2_impulse_extreme).replace(0,np.nan); ur=(f.r2_impulse_extreme-f.close)/upmove; dr=(f.close-f.r2_impulse_extreme)/dnmove; w=(h>=10)&(h<=14)
        lzone=w&after&f.r2_impulse_dir.eq(1)&ur.between(.382,.618); szone=w&after&f.r2_impulse_dir.eq(-1)&dr.between(.382,.618); lfirst=_first_true_per_group(lzone,f.date)&bull; sfirst=_first_true_per_group(szone,f.date)&bear
        return sided(lfirst,sfirst)
    if fam=="friday_fade":
        w=f.weekday.eq(4)&(h>=13)&(h<=15); c1,c2,c3=f.close.shift(3),f.close.shift(2),f.close.shift(1); up=(c1<c2)&(c2<c3); dn=(c1>c2)&(c2>c3); noext=f.new_week_extreme.shift(1).rolling(3,min_periods=3).sum().eq(0); mid=(f.open.shift(1)+f.close.shift(1))/2
        return sided(w&dn&noext&(f.close>mid),w&up&noext&(f.close<mid))
    raise ValueError(fam)


def execute(f,pair,spec):
    s=sig(f,pair,spec.family); slip=.10*pip(pair); out=[]; ok=pd.Timestamp.min.tz_localize("UTC"); ix=f.index; av=f.atr15.to_numpy(); bo,ao=f.bid_open.to_numpy(),f.ask_open.to_numpy(); bh,bl,bc=f.bid_high.to_numpy(),f.bid_low.to_numpy(),f.bid_close.to_numpy(); ah,al,ac=f.ask_high.to_numpy(),f.ask_low.to_numpy(),f.ask_close.to_numpy()
    for i in np.flatnonzero(s):
        if i+1>=len(f) or ix[i]<DEV_START or ix[i]>=END or ix[i]<ok or not np.isfinite(av[i]): continue
        side=int(s[i]); entry=float(ao[i+1]+slip if side==1 else bo[i+1]-slip); risk=1.25*float(av[i]); stop=entry-side*risk; target=entry+side*1.5*risk; px=None; reason="TIME"; amb=False; jend=min(i+24,len(f)-1)
        for j in range(i+1,jend+1):
            if ix[j].weekday()==4 and ix[j].hour>=16: jend=j; reason="FRIDAY"; break
            hi=float(bh[j] if side==1 else ah[j]); lo=float(bl[j] if side==1 else al[j]); sh=lo<=stop if side==1 else hi>=stop; th=hi>=target if side==1 else lo<=target
            if sh or th: jend=j; amb=bool(sh and th); reason="SL" if sh else "TP"; px=stop if sh else target; break
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
    t=pd.concat(all_t,ignore_index=True) if all_t else pd.DataFrame(columns=COLS); t.to_csv(out/"trades.csv",index=False); s=summarize(t); s.to_csv(out/"screen.csv",index=False)
    with open(out/"gate.json","w",encoding="utf-8") as fh: json.dump(GATE,fh,indent=2)
    print(s.to_string(index=False))

if __name__=="__main__": main()
