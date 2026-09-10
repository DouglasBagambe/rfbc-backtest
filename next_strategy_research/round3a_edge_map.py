#!/usr/bin/env python3
"""Round 3A development-only descriptive edge map.  It never simulates orders."""
from __future__ import annotations
import argparse
from pathlib import Path
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]; START=pd.Timestamp("2013-01-01",tz="UTC"); END=pd.Timestamp("2018-01-01",tz="UTC")
PAIRS=("EURUSD","GBPUSD","USDJPY","AUDUSD","NZDUSD","USDCAD","USDCHF","EURJPY","GBPJPY","AUDJPY","CADJPY","CHFJPY","EURGBP","EURAUD","GBPAUD")
USD_DIRECT=("EURUSD","GBPUSD","AUDUSD","NZDUSD"); USD_INVERSE=("USDJPY","USDCAD","USDCHF"); JPY=("EURJPY","GBPJPY","AUDJPY","CADJPY","CHFJPY")
HORIZONS=(1,2,4,8,16); SEQUENCE_BARS=8; RESIDUAL_BUCKET=1.0

def atr(f,n=14):
    p=f.close.shift(); tr=pd.concat((f.high-f.low,(f.high-p).abs(),(f.low-p).abs()),axis=1).max(axis=1)
    return tr.ewm(alpha=1/n,adjust=False,min_periods=n).mean()

def trailing_percentile(s,window=252):
    """Rank current value against exactly the preceding completed values."""
    return s.rolling(window+1,min_periods=window+1).apply(lambda x: np.mean(x[:-1] <= x[-1]),raw=True)

def dispersion_regime(percentile):
    return pd.Series(np.select([percentile<=.20,percentile>=.80],["low","high"],default="normal"),index=percentile.index)

def select_extremes(x):
    """Column-name ordering makes equal normalized returns deterministic."""
    y=x.reindex(sorted(x.columns),axis=1); return y.idxmax(axis=1),y.idxmin(axis=1)

def read(path):
    rows=[]
    for x in pd.read_csv(path,usecols=["dt","open","high","low","close","volume"],parse_dates=["dt"],chunksize=40000,dtype={k:"float32" for k in ("open","high","low","close","volume")}):
        x.dt=pd.to_datetime(x.dt,utc=True); rows.append(x[(x.dt>=START)&(x.dt<END)])
    if not rows: raise RuntimeError(f"no development rows: {path}")
    out=pd.concat(rows,ignore_index=True).set_index("dt").sort_index(); out.index.name="dt"; return out

def h1_state(h):
    x=h.copy(); x["h1_atr"]=atr(x); x["h1_atr_pct"]=trailing_percentile(x.h1_atr)
    e20=x.close.ewm(span=20,adjust=False).mean(); e50=x.close.ewm(span=50,adjust=False).mean(); x["h1_trend"]=np.where(e20>e50,1,np.where(e20<e50,-1,0))
    x["h1_norm_return"]=(x.close-x.open)/x.h1_atr; x["available"]=x.index+pd.Timedelta(hours=1)
    return x[["h1_atr","h1_atr_pct","h1_trend","h1_norm_return","available"]]

def attach_h1(f,h):
    left=f.copy(); left.index.name="dt"
    return pd.merge_asof(left.reset_index().sort_values("dt"),h.reset_index(drop=True).sort_values("available"),left_on="dt",right_on="available",direction="backward").drop(columns="available").set_index("dt")

def exact_forward(f,horizon):
    target=f.index+pd.Timedelta(minutes=15*horizon)
    return pd.Series(f.close.reindex(target).to_numpy(),index=f.index), pd.Series(f.index.isin(target),index=f.index)

def session_flags(index):
    h=index.hour; m=index.minute
    return pd.DataFrame({"asia":(h<6)|((h==6)&(m<=45)),"london_open":(h>=7)&((h<8)|((h==8)&(m<=45))),"london_body":(h>=9)&((h<12)|((h==12)&(m<=45))),"ny_open":(h>=13)&((h<14)|((h==14)&(m<=45))),"overlap":(h>=13)&((h<15)|((h==15)&(m<=45)))},index=index)

def known_session_levels(f):
    flags=session_flags(f.index); out=f.copy(); out["date"]=out.index.normalize()
    for name,flag,end in (("asia",flags.asia,pd.Timedelta(hours=7)),("london_open",flags.london_open,pd.Timedelta(hours=9)),("london_body",flags.london_body,pd.Timedelta(hours=13)),("ny_open",flags.ny_open,pd.Timedelta(hours=15))):
        g=out.loc[flag].groupby("date").agg(high=("high","max"),low=("low","min"),first_open=("open","first"),last_close=("close","last"))
        g=g.rename(columns={c:f"{name}_{c}" for c in g.columns}); g["available"]=g.index+end; z=pd.merge_asof(out.reset_index().sort_values("dt"),g.reset_index(drop=True).sort_values("available"),left_on="dt",right_on="available",direction="backward").set_index("dt")
        for col in ("high","low","first_open","last_close"): out[f"{name}_{col}"]=z[f"{name}_{col}"].to_numpy()
    return out,flags

def add_context(f):
    f["atr15"]=atr(f); f["atr_pct"]=trailing_percentile(f.atr15); f["year"]=f.index.year; f["date"]=f.index.normalize()
    daily=f.groupby("date").agg(high=("high","max"),low=("low","min")); f=f.join(daily.rename(columns={"high":"prior_high","low":"prior_low"}).shift(),on="date")
    return known_session_levels(f)

def primitives(f):
    p4h=f.high.shift(1).rolling(4,min_periods=4).max(); p4l=f.low.shift(1).rolling(4,min_periods=4).min(); out={}
    out["mss_up"]=f.close>p4h; out["mss_down"]=f.close<p4l; out["fvg_up"]=f.low>f.high.shift(2); out["fvg_down"]=f.high<f.low.shift(2)
    out["asia_sweep_low"]=(f.low<f.asia_low)&(f.close>=f.asia_low); out["asia_sweep_high"]=(f.high>f.asia_high)&(f.close<=f.asia_high)
    out["prior_sweep_low"]=(f.low<f.prior_low)&(f.close>=f.prior_low); out["prior_sweep_high"]=(f.high>f.prior_high)&(f.close<=f.prior_high)
    # Statefully define the latest opposite-colour candle in the four bars before an MSS.
    ob_up=pd.Series(False,index=f.index); ob_down=pd.Series(False,index=f.index); br_up=pd.Series(False,index=f.index); br_down=pd.Series(False,index=f.index)
    active=[]
    for i,t in enumerate(f.index):
        for ob in active[:]:
            if (ob["dir"]==1 and f.close.iloc[i]<ob["low"]) or (ob["dir"]==-1 and f.close.iloc[i]>ob["high"]): ob["invalid"]=True
            if ob["invalid"] and i>ob["formed"]: (br_down if ob["dir"]==1 else br_up).iloc[i]=True; active.remove(ob)
        direction=1 if bool(out["mss_up"].iloc[i]) else (-1 if bool(out["mss_down"].iloc[i]) else 0)
        if direction and i>=4:
            candidates=[j for j in range(i-4,i) if (f.close.iloc[j]<f.open.iloc[j]) if direction==1] if direction==1 else [j for j in range(i-4,i) if f.close.iloc[j]>f.open.iloc[j]]
            if candidates:
                j=candidates[-1]; active.append({"dir":direction,"high":f.high.iloc[j],"low":f.low.iloc[j],"formed":i,"invalid":False}); (ob_up if direction==1 else ob_down).iloc[i]=True
    out.update(ob_candidate_up=ob_up,ob_candidate_down=ob_down,breaker_up=br_up,breaker_down=br_down)
    # OTE comes only from accepted four-bar MSS impulse A -> B.
    a_low=f.low.shift(1).rolling(4,min_periods=4).min(); a_high=f.high.shift(1).rolling(4,min_periods=4).max()
    out["ote_up"]=out["mss_up"]&(f.low<=f.high)&((f.close-a_low)/(f.high-a_low).replace(0,np.nan)).between(.21,.38)
    out["ote_down"]=out["mss_down"]&(f.high>=f.low)&((a_high-f.close)/(a_high-f.low).replace(0,np.nan)).between(.21,.38)
    return out

def event_rows(f,pair):
    f,flags=add_context(f); e=primitives(f); p4h=f.high.shift(1).rolling(4).max(); p4l=f.low.shift(1).rolling(4).min()
    # Levels are first used after known_session_levels made them available.
    for name in ("asia","london_open","london_body","ny_open"):
        e[f"{name}_sweep_low"]=(f.low<f[f"{name}_low"])&(f.close>=f[f"{name}_low"]); e[f"{name}_sweep_high"]=(f.high>f[f"{name}_high"])&(f.close<=f[f"{name}_high"])
        e[f"{name}_range_break_up"]=(f.close>f[f"{name}_high"]); e[f"{name}_range_break_down"]=(f.close<f[f"{name}_low"])
        e[f"{name}_extreme_up"]=(f[f"{name}_last_close"]-f[f"{name}_first_open"]>=1.5*f.atr15); e[f"{name}_extreme_down"]=(f[f"{name}_last_close"]-f[f"{name}_first_open"]<=-1.5*f.atr15)
    shock=(f.close-f.close.shift())/f.atr15
    for lo,hi,label in ((.5,1.,"0_5_1_0"),(1.,1.5,"1_0_1_5"),(1.5,2.,"1_5_2_0"),(2.,np.inf,"gt_2_0")):
        e[f"m15_shock_up_{label}"]=(shock>=lo)&(shock<hi); e[f"m15_shock_down_{label}"]=(shock<=-lo)&(shock>-hi)
    e["atr_compression"]=f.atr_pct<=.20; e["atr_expansion"]=f.atr_pct>=.80; e["fvg_up_h1_up"]=e["fvg_up"]&f.h1_trend.eq(1); e["fvg_down_h1_down"]=e["fvg_down"]&f.h1_trend.eq(-1)
    prior_low_sweep=e["asia_sweep_low"].rolling(SEQUENCE_BARS+1,min_periods=1).max().shift(1).fillna(0).astype(bool); prior_high_sweep=e["asia_sweep_high"].rolling(SEQUENCE_BARS+1,min_periods=1).max().shift(1).fillna(0).astype(bool)
    e["sweep_then_mss_up"]=prior_low_sweep&e["mss_up"]; e["sweep_then_mss_down"]=prior_high_sweep&e["mss_down"]
    rows=[]
    for name,mask in e.items():
        direction=-1 if name.endswith(("_down","_high")) else 1
        for h in HORIZONS:
            future,exists=exact_forward(f,h); z=(future-f.close)/f.atr15; valid=mask&exists&f.atr15.gt(0)&z.notna()
            for t,v in z[valid].items(): rows.append((name,pair,t,f.year.loc[t],h,float(v),float(direction*v),np.nan,np.nan,"not_applicable"))
    return pd.DataFrame(rows,columns=["event","pair","dt","year","horizon","forward_atr_return","continuation_atr_return","dispersion_level","dispersion_percentile","dispersion_regime"]),e

def cross_rows(root):
    h={p:h1_state(read(root/p/f"{p}_bid_h1.csv")) for p in PAIRS}; norm={p:h[p].h1_norm_return.rename(p) for p in PAIRS}; rows=[]
    for members,name,sign in ((USD_DIRECT+USD_INVERSE,"usd",{**{p:-1 for p in USD_DIRECT},**{p:1 for p in USD_INVERSE}}),(JPY,"jpy",{p:-1 for p in JPY})):
        x=pd.concat([norm[p]*sign[p] for p in members],axis=1,join="inner").dropna(); med=x.median(axis=1); pos=(x>0).sum(axis=1); neg=(x<0).sum(axis=1); strong,weak=select_extremes(x)
        dispersion=x.std(axis=1,ddof=0); disp_pct=trailing_percentile(dispersion); regime=dispersion_regime(disp_pct)
        for k in HORIZONS:
            for t in x.index:
                target=t+pd.Timedelta(minutes=15*k)
                # H1 labels require exact future H1 availability: only k=4/8/16 is valid.
                if k%4 or target not in x.index or not np.isfinite(disp_pct.loc[t]): continue
                context=(float(dispersion.loc[t]),float(disp_pct.loc[t]),regime.loc[t])
                for label,p in (("strongest",strong.loc[t]),("weakest",weak.loc[t])):
                    v=x.loc[target,p]; rows.append((f"{name}_{label}",p,t,t.year,k,float(v),float(np.sign(x.loc[t,p])*v),*context))
                spread_change=(x.loc[target,strong.loc[t]]-x.loc[target,weak.loc[t]])-(x.loc[t,strong.loc[t]]-x.loc[t,weak.loc[t]])
                rows.append((f"{name}_strong_minus_weak_change",name,t,t.year,k,float(spread_change),np.nan,*context))
                for p in members:
                    residual=x.loc[t,p]-med.loc[t]
                    if abs(residual)>=RESIDUAL_BUCKET: rows.append((f"{name}_residual_{'positive' if residual>0 else 'negative'}",p,t,t.year,k,float(x.loc[target,p]),float(np.sign(residual)*x.loc[target,p]),*context))
                rows.append((f"{name}_basket_persistence",name,t,t.year,k,float(med.loc[target]),float(np.sign(med.loc[t])*med.loc[target]),*context))
        for t in x.index: rows.append((f"{name}_breadth_pos_minus_neg",name,t,t.year,0,float(pos.loc[t]-neg.loc[t]),np.nan,float(dispersion.loc[t]),float(disp_pct.loc[t]),regime.loc[t]))
    for a,b in (("EURUSD","GBPUSD"),("AUDUSD","NZDUSD"),("EURJPY","GBPJPY")):
        x=pd.concat((norm[a],norm[b]),axis=1,join="inner").dropna(); diff=x[a]-x[b]
        for k in HORIZONS:
            for t in x.index:
                target=t+pd.Timedelta(minutes=15*k)
                if k%4 or target not in x.index: continue
                lead=a if diff.loc[t]>=0 else b; lag=b if lead==a else a; change=diff.loc[target]-diff.loc[t]
                rows += [(f"divergence_{a}_{b}_convergence",a,t,t.year,k,float(-np.sign(diff.loc[t])*change),np.nan,np.nan,np.nan,"not_applicable"),(f"divergence_{a}_{b}_leader",lead,t,t.year,k,float(x.loc[target,lead]),float(np.sign(x.loc[t,lead])*x.loc[target,lead]),np.nan,np.nan,"not_applicable"),(f"divergence_{a}_{b}_laggard",lag,t,t.year,k,float(x.loc[target,lag]),float(np.sign(x.loc[t,lag])*x.loc[target,lag]),np.nan,np.nan,"not_applicable")]
    return pd.DataFrame(rows,columns=["event","pair","dt","year","horizon","forward_atr_return","continuation_atr_return","dispersion_level","dispersion_percentile","dispersion_regime"])

def summarize(x,groups):
    def s(g):
        v=g.forward_atr_return.dropna(); n=len(v); mean=v.mean(); se=v.std(ddof=1)/np.sqrt(n) if n>1 else np.nan
        return pd.Series({"event_count":n,"mean_forward_return":mean,"median_forward_return":v.median(),"standard_error":se,"t_statistic":mean/se if np.isfinite(se) and se else np.nan,"directional_probability":(g.continuation_atr_return.dropna()>0).mean(),"p25":v.quantile(.25),"p50":v.quantile(.5),"p75":v.quantile(.75)})
    return x.groupby(groups,dropna=False).apply(s,include_groups=False).reset_index()

def breadth(by_pair,by_year):
    def count(g):
        direction=np.sign(g.mean_forward_return.mean()); return int((np.sign(g.mean_forward_return)==direction).sum())
    group=["event","horizon","dispersion_regime"] if "dispersion_regime" in by_pair else ["event","horizon"]
    p=by_pair.groupby(group).apply(count,include_groups=False).rename("pair_breadth_same_sign").reset_index()
    y=by_year.groupby(group).apply(count,include_groups=False).rename("year_breadth_same_sign").reset_index(); return p,y

def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--data",default=str(ROOT/"data_independent/derived_m15")); ap.add_argument("--out",default=str(ROOT/"results_next_strategy/round3a")); ap.add_argument("--pairs",nargs="+",default=list(PAIRS)); a=ap.parse_args(); root=Path(a.data); chunks=[]; counts=[]
    for pair in a.pairs:
        x,e=event_rows(attach_h1(read(root/pair/f"{pair}_bid_m15.csv"),h1_state(read(root/pair/f"{pair}_bid_h1.csv"))),pair); chunks.append(x); counts += [(n,pair,int(v.sum())) for n,v in e.items()]
    chunks.append(cross_rows(root)); x=pd.concat(chunks,ignore_index=True); edge=summarize(x,["event","horizon","dispersion_regime"]); bp=summarize(x,["event","horizon","dispersion_regime","pair"]); by=summarize(x,["event","horizon","dispersion_regime","year"]); pb,yb=breadth(bp,by)
    edge=edge.merge(pb,on=["event","horizon","dispersion_regime"],how="left").merge(yb,on=["event","horizon","dispersion_regime"],how="left"); out=Path(a.out); out.mkdir(parents=True,exist_ok=True)
    edge.to_csv(out/"edge_map.csv",index=False); bp.to_csv(out/"by_pair.csv",index=False); by.to_csv(out/"by_year.csv",index=False); pd.DataFrame(counts,columns=["event","pair","event_count"]).to_csv(out/"event_counts.csv",index=False)
    (ROOT/"ROUND3A_EDGE_MAP_REPORT.md").write_text("# Round 3A Edge Map Report\n\nDevelopment-only descriptive output. No P&L or strategy promotion is implied.\n",encoding="utf-8")

if __name__=="__main__": main()
