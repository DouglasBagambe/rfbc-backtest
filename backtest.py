from __future__ import annotations
import argparse, json, math, os, sys
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Optional
import numpy as np
import pandas as pd

PAIRS = ["EURUSD","GBPUSD","USDJPY","AUDUSD"]
TFS = ["d1","h4","h1","m30","m15"]
SPREAD_PIPS = {"EURUSD":0.9,"GBPUSD":1.2,"USDJPY":1.0,"AUDUSD":1.1}
PIP_RAW = 10.0

@dataclass
class Params:
    breakout_lookback:int=20
    atr_period:int=14
    atr_mult:float=1.5
    rr:float=2.5
    d1_fast:int=50
    d1_slow:int=200
    risk_pct:float=0.005
    slippage_pips_per_side:float=0.2
    use_vol_filter:bool=True
    vol_lookback:int=100
    vol_min_quantile:float=0.40
    use_h1_confirmation:bool=False
    execution_tf:str="h4"  # h4, h1, m30, m15


def load_csv(path:Path)->pd.DataFrame:
    df=pd.read_csv(path)
    dtcol="Date" if "Date" in df.columns else "datetime"
    df[dtcol]=pd.to_datetime(df[dtcol], errors="coerce")
    df=df.dropna(subset=[dtcol]).rename(columns={dtcol:"dt"}).sort_values("dt").drop_duplicates("dt")
    cols=["open","high","low","close"]
    for c in cols: df[c]=pd.to_numeric(df[c], errors="coerce")
    return df.dropna(subset=cols).reset_index(drop=True)

def ema(s,n): return s.ewm(span=n,adjust=False,min_periods=n).mean()

def atr(df,n=14):
    prev=df.close.shift(1)
    tr=pd.concat([(df.high-df.low).abs(),(df.high-prev).abs(),(df.low-prev).abs()],axis=1).max(axis=1)
    return tr.ewm(alpha=1/n,adjust=False,min_periods=n).mean()

def prepare(pair,data_dir:Path,p:Params):
    d1=load_csv(data_dir/f"{pair}d1.csv")
    h4=load_csv(data_dir/f"{pair}h4.csv")
    d1["ema_fast"]=ema(d1.close,p.d1_fast); d1["ema_slow"]=ema(d1.close,p.d1_slow)
    d1["regime"]=0
    d1.loc[(d1.close>d1.ema_fast)&(d1.ema_fast>d1.ema_slow),"regime"]=1
    d1.loc[(d1.close<d1.ema_fast)&(d1.ema_fast<d1.ema_slow),"regime"]=-1
    h4["atr"]=atr(h4,p.atr_period)
    h4["prev_high"]=h4.high.shift(1).rolling(p.breakout_lookback).max()
    h4["prev_low"]=h4.low.shift(1).rolling(p.breakout_lookback).min()
    if p.use_vol_filter:
        # Conservative reconstruction assumption because Phase-1 quantile was not recoverable:
        # require ATR to be above its rolling 40th percentile, suppressing low-volatility chop.
        h4["atr_q"]=h4.atr.shift(1).rolling(p.vol_lookback).quantile(p.vol_min_quantile)
        h4["vol_ok"]=h4.atr>=h4.atr_q
    else: h4["vol_ok"]=True
    # map most recently CLOSED daily regime to each H4 bar without look-ahead
    dmap=d1[["dt","regime"]].copy(); dmap["dt"]=dmap.dt+pd.Timedelta(days=1)
    h4=pd.merge_asof(h4.sort_values("dt"),dmap.sort_values("dt"),on="dt",direction="backward")
    h4["signal"]=0
    h4.loc[(h4.regime==1)&h4.vol_ok&(h4.close>h4.prev_high),"signal"]=1
    h4.loc[(h4.regime==-1)&h4.vol_ok&(h4.close<h4.prev_low),"signal"]=-1
    if p.use_h1_confirmation:
        h1=load_csv(data_dir/f"{pair}h1.csv"); h1["ema20"]=ema(h1.close,20)
        h1["confirm_long"]=(h1.close>h1.open)&(h1.close>h1.ema20)
        h1["confirm_short"]=(h1.close<h1.open)&(h1.close<h1.ema20)
        # confirmation must be known by H4 close
        conf=pd.merge_asof(h4[["dt"]].sort_values("dt"),h1[["dt","confirm_long","confirm_short"]].sort_values("dt"),on="dt",direction="backward")
        h4.loc[(h4.signal==1)&(~conf.confirm_long.fillna(False)),"signal"]=0
        h4.loc[(h4.signal==-1)&(~conf.confirm_short.fillna(False)),"signal"]=0
    return h4

def first_exec_bar(execdf:pd.DataFrame, after:pd.Timestamp):
    i=execdf.dt.searchsorted(after, side="right")
    return int(i) if i<len(execdf) else None

def run_pair(pair:str,data_dir:Path,p:Params):
    h4=prepare(pair,data_dir,p)
    execdf=h4 if p.execution_tf=="h4" else load_csv(data_dir/f"{pair}{p.execution_tf}.csv")
    spread=SPREAD_PIPS[pair]*PIP_RAW
    slip=p.slippage_pips_per_side*PIP_RAW
    trades=[]; next_allowed=pd.Timestamp.min
    sigidx=np.where(h4.signal.values!=0)[0]
    for si in sigidx:
        s=h4.iloc[si]
        if s.dt<=next_allowed or not np.isfinite(s.atr) or s.atr<=0: continue
        ei=first_exec_bar(execdf,s.dt)
        if ei is None: continue
        side=int(s.signal)
        base_entry=float(execdf.iloc[ei].open)
        # buy pays half-spread + slippage; sell receives worse bid equivalently
        entry=base_entry + side*(spread/2 + slip)
        risk_dist=p.atr_mult*float(s.atr)
        stop=entry-side*risk_dist
        target=entry+side*p.rr*risk_dist
        exit_px=None; exit_dt=None; reason=None
        # execute no earlier than the first bar after signal; conservative intra-bar resolution
        for j in range(ei,len(execdf)):
            b=execdf.iloc[j]
            stop_hit=(b.low<=stop) if side==1 else (b.high>=stop)
            tgt_hit=(b.high>=target) if side==1 else (b.low<=target)
            if stop_hit and tgt_hit:
                exit_px=stop-side*(spread/2+slip); reason="SL_both"; exit_dt=b.dt; break
            if stop_hit:
                exit_px=stop-side*(spread/2+slip); reason="SL"; exit_dt=b.dt; break
            if tgt_hit:
                exit_px=target-side*(spread/2+slip); reason="TP"; exit_dt=b.dt; break
            # hard time-stop after 30 calendar days to prevent indefinite stale positions
            if b.dt-s.dt>pd.Timedelta(days=30):
                exit_px=float(b.close)-side*(spread/2+slip); reason="TIME"; exit_dt=b.dt; break
        if exit_px is None: continue
        realized_r=side*(exit_px-entry)/risk_dist
        trades.append({"pair":pair,"signal_dt":s.dt,"entry_dt":execdf.iloc[ei].dt,"exit_dt":exit_dt,"side":side,"entry":entry,"stop":stop,"target":target,"exit":exit_px,"reason":reason,"r":realized_r,"atr":s.atr,"execution_tf":p.execution_tf})
        next_allowed=exit_dt
    return pd.DataFrame(trades)

def max_consecutive_losses(r):
    m=c=0
    for x in r:
        if x<0: c+=1; m=max(m,c)
        else: c=0
    return m

def metrics(trades:pd.DataFrame, risk_pct=.005, start=10000.0):
    if trades.empty: return {"trades":0}
    t=trades.sort_values("exit_dt").copy(); bal=start; peak=start; maxdd=0; eq=[]
    for r in t.r:
        bal*=1+risk_pct*r
        peak=max(peak,bal); maxdd=max(maxdd,(peak-bal)/peak); eq.append(bal)
    wins=t[t.r>0].r; losses=t[t.r<=0].r
    gp=wins.sum(); gl=-losses.sum()
    years=max((t.exit_dt.max()-t.entry_dt.min()).days/365.25,1/365.25)
    cagr=(bal/start)**(1/years)-1 if bal>0 else -1
    return {
      "trades":len(t),"wins":int((t.r>0).sum()),"losses":int((t.r<=0).sum()),"win_rate":float((t.r>0).mean()),
      "avg_r":float(t.r.mean()),"median_r":float(t.r.median()),"avg_win_r":float(wins.mean()) if len(wins) else None,
      "avg_loss_r":float(losses.mean()) if len(losses) else None,"profit_factor":float(gp/gl) if gl>0 else None,
      "max_dd_pct":float(maxdd),"longest_loss_streak":int(max_consecutive_losses(t.r.tolist())),
      "start_balance":start,"end_balance":float(bal),"net_pnl":float(bal-start),"total_return_pct":float(bal/start-1),"cagr":float(cagr)
    }

def monte_carlo(trades:pd.DataFrame,risk_pct=.005,start=10000,n=5000,seed=42):
    if trades.empty:return {}
    rng=np.random.default_rng(seed); r=trades.r.to_numpy(); finals=[]; dds=[]
    for _ in range(n):
        seq=rng.choice(r,size=len(r),replace=True); bal=start; peak=start; md=0
        for x in seq:
            bal*=1+risk_pct*x; peak=max(peak,bal); md=max(md,(peak-bal)/peak)
        finals.append(bal); dds.append(md)
    q=lambda a,x:float(np.quantile(a,x))
    return {"final_p05":q(finals,.05),"final_median":q(finals,.5),"final_p95":q(finals,.95),"dd_p50":q(dds,.5),"dd_p95":q(dds,.95),"prob_dd_gt_10pct":float(np.mean(np.array(dds)>.10)),"prob_dd_gt_20pct":float(np.mean(np.array(dds)>.20))}

def prop_sim(trades:pd.DataFrame,risk_pct=.005,start=100000,daily_dd=0.05,total_dd=0.10):
    if trades.empty:return {}
    t=trades.sort_values("exit_dt"); bal=start; peak=start; day_start=start; curday=None
    daily_breach=False; total_breach=False; breach_dt=None
    for _,x in t.iterrows():
        d=x.exit_dt.date()
        if d!=curday: curday=d; day_start=bal
        bal*=1+risk_pct*x.r; peak=max(peak,bal)
        if bal<day_start*(1-daily_dd): daily_breach=True; breach_dt=x.exit_dt; break
        if bal<start*(1-total_dd): total_breach=True; breach_dt=x.exit_dt; break
    return {"breached":daily_breach or total_breach,"daily_breach":daily_breach,"total_breach":total_breach,"breach_dt":str(breach_dt) if breach_dt else None,"end_balance":float(bal)}

def monthly_table(trades:pd.DataFrame,risk_pct=.005):
    if trades.empty:return pd.DataFrame()
    t=trades.copy(); t["month"]=t.exit_dt.dt.to_period("M").astype(str)
    out=[]
    for m,g in t.groupby("month"):
        ret=np.prod(1+risk_pct*g.r)-1
        out.append({"month":m,"trades":len(g),"return_pct":ret,"sum_r":g.r.sum()})
    return pd.DataFrame(out)

def sensitivity(data_dir:Path,outdir:Path):
    rows=[]
    for lookback in [16,20,24]:
      for atrm in [1.25,1.5,1.75]:
       for rr in [2.0,2.5,3.0]:
        p=Params(breakout_lookback=lookback,atr_mult=atrm,rr=rr,execution_tf="h4")
        alltr=pd.concat([run_pair(x,data_dir,p) for x in PAIRS],ignore_index=True)
        m=metrics(alltr,p.risk_pct); rows.append({"lookback":lookback,"atr_mult":atrm,"rr":rr,**{k:m.get(k) for k in ["trades","win_rate","avg_r","profit_factor","max_dd_pct","total_return_pct"]}})
    pd.DataFrame(rows).to_csv(outdir/"sensitivity.csv",index=False)

def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--data",default="data"); ap.add_argument("--out",default="results"); args=ap.parse_args()
    data=Path(args.data); out=Path(args.out); out.mkdir(parents=True,exist_ok=True)
    scenarios={
      "baseline_h4":Params(execution_tf="h4"),
      "h1_confirm_h4exec":Params(use_h1_confirmation=True,execution_tf="h4"),
      "baseline_h1exec":Params(execution_tf="h1"),
      "baseline_m30exec":Params(execution_tf="m30"),
      "baseline_m15exec":Params(execution_tf="m15"),
      "no_vol_filter":Params(use_vol_filter=False,execution_tf="h4"),
    }
    summary=[]
    for name,p in scenarios.items():
        chunks=[]
        for pair in PAIRS:
            try: chunks.append(run_pair(pair,data,p))
            except FileNotFoundError: pass
        tr=pd.concat(chunks,ignore_index=True) if chunks else pd.DataFrame()
        if not tr.empty:
            tr.to_csv(out/f"trades_{name}.csv",index=False)
            monthly_table(tr,p.risk_pct).to_csv(out/f"monthly_{name}.csv",index=False)
        m=metrics(tr,p.risk_pct); mc=monte_carlo(tr,p.risk_pct); ps=prop_sim(tr,p.risk_pct)
        summary.append({"scenario":name,**m,**{f"mc_{k}":v for k,v in mc.items()},**{f"prop_{k}":v for k,v in ps.items()}})
    pd.DataFrame(summary).to_csv(out/"summary.csv",index=False)
    sensitivity(data,out)
    # pair-level baseline
    p=scenarios["baseline_h4"]; prow=[]
    for pair in PAIRS:
        tr=run_pair(pair,data,p); prow.append({"pair":pair,**metrics(tr,p.risk_pct)})
    pd.DataFrame(prow).to_csv(out/"pair_metrics.csv",index=False)
    # machine-readable strategy assumptions
    (out/"strategy_reconstruction.json").write_text(json.dumps(asdict(p),indent=2))
    print(pd.DataFrame(summary).to_string(index=False))

if __name__=="__main__": main()
