from __future__ import annotations
import argparse, json
from dataclasses import dataclass, asdict
from pathlib import Path
import numpy as np
import pandas as pd

BASELINE_PAIRS = ["EURUSD","GBPUSD","USDJPY"]
DATA_PAIRS = ["EURUSD","GBPUSD","USDJPY","AUDUSD"]  # AUDUSD is exploratory/missing-pair coverage only.
SPREAD_PIPS = {"EURUSD":0.9,"GBPUSD":1.2,"USDJPY":1.0,"AUDUSD":1.1}
PIP_RAW = 10.0  # ejtraderLabs files are scaled by 1e5, so one pip = 10 raw units.

@dataclass
class Params:
    breakout_lookback:int=20
    atr_period:int=14
    atr_mult:float=1.50
    rr:float=2.50
    d1_fast:int=50
    d1_slow:int=200
    d1_slope_lookback:int=5
    extreme_candle_atr:float=2.0
    chase_atr:float=0.20
    risk_pct:float=0.005
    slippage_pips_per_side:float=0.2
    execution_tf:str="h4"

def load_csv(path:Path)->pd.DataFrame:
    df=pd.read_csv(path)
    dtcol="Date" if "Date" in df.columns else "datetime"
    df[dtcol]=pd.to_datetime(df[dtcol], errors="coerce", utc=True).dt.tz_convert(None)
    df=df.dropna(subset=[dtcol]).rename(columns={dtcol:"dt"}).sort_values("dt").drop_duplicates("dt")
    for c in ["open","high","low","close"]:
        df[c]=pd.to_numeric(df[c], errors="coerce")
    return df.dropna(subset=["open","high","low","close"]).reset_index(drop=True)

def ema(s,n): return s.ewm(span=n,adjust=False,min_periods=n).mean()

def atr(df,n=14):
    prev=df.close.shift(1)
    tr=pd.concat([(df.high-df.low).abs(),(df.high-prev).abs(),(df.low-prev).abs()],axis=1).max(axis=1)
    return tr.ewm(alpha=1/n,adjust=False,min_periods=n).mean()

def is_actionable_close(ts:pd.Timestamp)->bool:
    wd=ts.weekday(); h=ts.hour
    if wd <= 3: return h in (8,12,16)
    if wd == 4: return h in (8,12)
    return False

def prepare(pair,data_dir:Path,p:Params):
    d1=load_csv(data_dir/f"{pair}d1.csv")
    h4=load_csv(data_dir/f"{pair}h4.csv")
    d1["ema_fast"]=ema(d1.close,p.d1_fast)
    d1["ema_slow"]=ema(d1.close,p.d1_slow)
    d1["ema_fast_prev"]=d1.ema_fast.shift(p.d1_slope_lookback)
    d1["regime"]=0
    d1.loc[(d1.close>d1.ema_fast)&(d1.ema_fast>d1.ema_slow)&(d1.ema_fast>d1.ema_fast_prev),"regime"]=1
    d1.loc[(d1.close<d1.ema_fast)&(d1.ema_fast<d1.ema_slow)&(d1.ema_fast<d1.ema_fast_prev),"regime"]=-1

    h4["atr"]=atr(h4,p.atr_period)
    prev=h4.close.shift(1)
    h4["tr"]=pd.concat([(h4.high-h4.low).abs(),(h4.high-prev).abs(),(h4.low-prev).abs()],axis=1).max(axis=1)
    h4["prev_high"]=h4.high.shift(1).rolling(p.breakout_lookback).max()
    h4["prev_low"]=h4.low.shift(1).rolling(p.breakout_lookback).min()
    h4["close_dt"]=h4.dt+pd.Timedelta(hours=4)

    dmap=d1[["dt","regime"]].copy(); dmap["available_dt"]=dmap.dt+pd.Timedelta(days=1)
    h4=pd.merge_asof(h4.sort_values("close_dt"),dmap[["available_dt","regime"]].sort_values("available_dt"),
                     left_on="close_dt",right_on="available_dt",direction="backward")
    h4["actionable"]=h4.close_dt.map(is_actionable_close)
    h4["signal"]=0
    common=h4.actionable & np.isfinite(h4.atr) & (h4.atr>0) & (h4.tr<=p.extreme_candle_atr*h4.atr)
    h4.loc[common & (h4.regime==1) & (h4.close>h4.prev_high),"signal"]=1
    h4.loc[common & (h4.regime==-1) & (h4.close<h4.prev_low),"signal"]=-1
    return h4

def first_exec_bar(execdf:pd.DataFrame, at_or_after:pd.Timestamp):
    i=execdf.dt.searchsorted(at_or_after,side="left")
    return int(i) if i<len(execdf) else None

def run_pair(pair:str,data_dir:Path,p:Params):
    h4=prepare(pair,data_dir,p)
    execdf=h4[["dt","open","high","low","close"]].copy() if p.execution_tf=="h4" else load_csv(data_dir/f"{pair}{p.execution_tf}.csv")
    spread=SPREAD_PIPS[pair]*PIP_RAW; slip=p.slippage_pips_per_side*PIP_RAW; round_trip_cost=spread+2*slip
    trades=[]; next_allowed=pd.Timestamp.min
    for si in np.where(h4.signal.values!=0)[0]:
        s=h4.iloc[si]; signal_dt=s.close_dt
        if signal_dt<=next_allowed or not np.isfinite(s.atr) or s.atr<=0: continue
        ei=first_exec_bar(execdf,signal_dt)
        if ei is None: continue
        side=int(s.signal); base_entry=float(execdf.iloc[ei].open)
        adverse=side*(base_entry-float(s.close))
        if adverse > p.chase_atr*float(s.atr): continue
        entry=base_entry+side*(spread/2+slip)
        risk_dist=p.atr_mult*float(s.atr)
        stop=entry-side*risk_dist; target=entry+side*p.rr*risk_dist; be_stop=entry+side*round_trip_cost
        be_armed=False; exit_px=exit_dt=reason=None

        for j in range(ei,len(execdf)):
            b=execdf.iloc[j]
            bar_dt=b["dt"]
            if bar_dt.weekday()==4 and bar_dt>=bar_dt.normalize()+pd.Timedelta(hours=16):
                exit_px=float(b.open)-side*(spread/2+slip); exit_dt=bar_dt; reason="FRIDAY"; break
            active_stop=be_stop if be_armed else stop
            stop_hit=(b.low<=active_stop) if side==1 else (b.high>=active_stop)
            tgt_hit=(b.high>=target) if side==1 else (b.low<=target)
            if stop_hit and tgt_hit:
                exit_px=active_stop-side*(spread/2+slip); exit_dt=bar_dt; reason="BE_both" if be_armed else "SL_both"; break
            if stop_hit:
                exit_px=active_stop-side*(spread/2+slip); exit_dt=bar_dt; reason="BE" if be_armed else "SL"; break
            if tgt_hit:
                exit_px=target-side*(spread/2+slip); exit_dt=bar_dt; reason="TP"; break

            if p.execution_tf=="h4":
                if side*(float(b.close)-entry)/risk_dist >= 1.50: be_armed=True
            else:
                close_dt=bar_dt + (pd.Timedelta(minutes=30) if p.execution_tf=="m30" else pd.Timedelta(minutes=15))
                if close_dt.hour in (0,4,8,12,16,20) and close_dt.minute==0 and side*(float(b.close)-entry)/risk_dist >= 1.50:
                    be_armed=True

        if exit_px is None: continue
        realized_r=side*(float(exit_px)-entry)/risk_dist
        trades.append({"pair":pair,"signal_dt":signal_dt,"entry_dt":execdf.iloc[ei]["dt"],"exit_dt":exit_dt,
                       "side":side,"entry":entry,"signal_close":float(s.close),"stop":stop,"target":target,
                       "exit":float(exit_px),"reason":reason,"r":realized_r,"atr":float(s.atr),"execution_tf":p.execution_tf})
        next_allowed=exit_dt
    return pd.DataFrame(trades)

def max_consecutive_losses(r):
    m=c=0
    for x in r:
        if x<0: c+=1; m=max(m,c)
        else: c=0
    return m

def equity_path(trades:pd.DataFrame,risk_pct=.005,start=10000.0):
    t=trades.sort_values("exit_dt").copy(); bal=peak=start; dd=0; rows=[]
    for _,x in t.iterrows():
        before=bal; bal*=1+risk_pct*x.r; peak=max(peak,bal); dd=max(dd,(peak-bal)/peak)
        rows.append((x.exit_dt,before,bal,(peak-bal)/peak))
    return bal,dd,rows

def metrics(trades:pd.DataFrame,risk_pct=.005,start=10000.0):
    if trades.empty:return {"trades":0}
    t=trades.sort_values("exit_dt").copy(); bal,maxdd,_=equity_path(t,risk_pct,start)
    wins=t[t.r>0].r; losses=t[t.r<=0].r; gp=wins.sum(); gl=-losses.sum()
    years=max((t.exit_dt.max()-t.entry_dt.min()).days/365.25,1/365.25)
    months=max((t.exit_dt.max().to_period("M")-t.entry_dt.min().to_period("M")).n+1,1)
    return {"trades":len(t),"wins":int((t.r>0).sum()),"losses":int((t.r<=0).sum()),
      "win_rate":float((t.r>0).mean()),"avg_r":float(t.r.mean()),"median_r":float(t.r.median()),
      "avg_win_r":float(wins.mean()) if len(wins) else None,"avg_loss_r":float(losses.mean()) if len(losses) else None,
      "profit_factor":float(gp/gl) if gl>0 else None,"max_dd_pct":float(maxdd),
      "longest_loss_streak":int(max_consecutive_losses(t.r.tolist())),"start_balance":start,"end_balance":float(bal),
      "net_pnl":float(bal-start),"total_return_pct":float(bal/start-1),
      "cagr":float((bal/start)**(1/years)-1) if bal>0 else -1,"avg_trades_per_month":float(len(t)/months)}

def period_table(trades:pd.DataFrame,risk_pct=.005,freq="M"):
    if trades.empty:return pd.DataFrame()
    t=trades.copy(); key="month" if freq=="M" else "year"; t[key]=t.exit_dt.dt.to_period(freq).astype(str); rows=[]
    for k,g in t.groupby(key):
        rows.append({key:k,"trades":len(g),"return_pct":float(np.prod(1+risk_pct*g.r)-1),"sum_r":float(g.r.sum()),
                     "win_rate":float((g.r>0).mean()),"avg_r":float(g.r.mean())})
    return pd.DataFrame(rows)

def weekly_blocks(trades:pd.DataFrame):
    t=trades.sort_values("exit_dt").copy(); t["week"]=t.exit_dt.dt.to_period("W-SUN").astype(str)
    return [g.r.to_numpy() for _,g in t.groupby("week")]

def simulate_blocks(trades:pd.DataFrame,risk_pct=.005,start=100000,n=5000,seed=42):
    if trades.empty:return pd.DataFrame()
    blocks=weekly_blocks(trades)
    if not blocks:return pd.DataFrame()
    rng=np.random.default_rng(seed); rows=[]
    for _ in range(n):
        seq=[]
        for _j in range(len(blocks)): seq.extend(blocks[rng.integers(0,len(blocks))])
        bal=peak=start; maxdd=0
        for r in seq:
            bal*=1+risk_pct*r; peak=max(peak,bal); maxdd=max(maxdd,(peak-bal)/peak)
        rows.append({"final":bal,"max_dd":maxdd})
    return pd.DataFrame(rows)

def monte_carlo(trades:pd.DataFrame,risk_pct=.005,start=10000,n=5000,seed=42):
    sim=simulate_blocks(trades,risk_pct,start,n,seed)
    if sim.empty:return {}
    return {"final_p05":float(sim.final.quantile(.05)),"final_median":float(sim.final.quantile(.50)),
      "final_p95":float(sim.final.quantile(.95)),"dd_p50":float(sim.max_dd.quantile(.50)),"dd_p95":float(sim.max_dd.quantile(.95)),
      "prob_dd_gt_5pct":float((sim.max_dd>.05).mean()),"prob_dd_gt_10pct":float((sim.max_dd>.10).mean()),
      "prob_dd_gt_20pct":float((sim.max_dd>.20).mean())}

def prop_mc(trades:pd.DataFrame,risk_pct,n=5000,start=100000,seed=100):
    if trades.empty:return {}
    t=trades.sort_values("exit_dt").copy(); t["week"]=t.exit_dt.dt.to_period("W-SUN").astype(str)
    blocks=[g.copy() for _,g in t.groupby("week")]; rng=np.random.default_rng(seed)
    dd5=dd10=daily5=0; finals=[]
    for _ in range(n):
        bal=peak=start; breached5=breached10=breacheddaily=False
        for _j in range(len(blocks)):
            g=blocks[rng.integers(0,len(blocks))].copy(); day_start={}
            for _,x in g.iterrows():
                d=x.exit_dt.date()
                if d not in day_start: day_start[d]=bal
                bal*=1+risk_pct*x.r; peak=max(peak,bal)
                if bal < day_start[d]*.95: breacheddaily=True
                if bal < peak*.95: breached5=True
                if bal < start*.90: breached10=True
        dd5+=breached5; dd10+=breached10; daily5+=breacheddaily; finals.append(bal)
    return {"risk_pct":risk_pct,"prob_internal_5pct_halt":dd5/n,"prob_generic_10pct_total_breach":dd10/n,
            "prob_generic_5pct_daily_breach":daily5/n,"final_median":float(np.median(finals))}

def sensitivity(data_dir:Path,outdir:Path):
    rows=[]
    for lookback in [15,20,25]:
      for atrm in [1.25,1.50,1.75]:
       for rr in [2.0,2.5,3.0]:
        p=Params(breakout_lookback=lookback,atr_mult=atrm,rr=rr,execution_tf="h4")
        alltr=pd.concat([run_pair(x,data_dir,p) for x in BASELINE_PAIRS],ignore_index=True)
        m=metrics(alltr,p.risk_pct)
        rows.append({"lookback":lookback,"atr_mult":atrm,"rr":rr,**{k:m.get(k) for k in ["trades","win_rate","avg_r","profit_factor","max_dd_pct","total_return_pct"]}})
    pd.DataFrame(rows).to_csv(outdir/"sensitivity.csv",index=False)

def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--data",default="data"); ap.add_argument("--out",default="results")
    args=ap.parse_args(); data=Path(args.data); out=Path(args.out); out.mkdir(parents=True,exist_ok=True)
    scenarios={"baseline_h4":Params(execution_tf="h4"),"baseline_m30exec":Params(execution_tf="m30"),"baseline_m15exec":Params(execution_tf="m15")}
    summary=[]; baseline_tr=None
    for name,p in scenarios.items():
        chunks=[run_pair(pair,data,p) for pair in BASELINE_PAIRS]; tr=pd.concat(chunks,ignore_index=True) if chunks else pd.DataFrame()
        if name=="baseline_h4": baseline_tr=tr.copy()
        if not tr.empty:
            tr.to_csv(out/f"trades_{name}.csv",index=False); period_table(tr,p.risk_pct,"M").to_csv(out/f"monthly_{name}.csv",index=False)
            period_table(tr,p.risk_pct,"Y").to_csv(out/f"yearly_{name}.csv",index=False)
        m=metrics(tr,p.risk_pct); mc=monte_carlo(tr,p.risk_pct)
        summary.append({"scenario":name,**m,**{f"mc_{k}":v for k,v in mc.items()}})
    pd.DataFrame(summary).to_csv(out/"summary.csv",index=False)

    p=scenarios["baseline_h4"]; prow=[]
    for pair in BASELINE_PAIRS:
        tr=run_pair(pair,data,p); prow.append({"pair":pair,**metrics(tr,p.risk_pct)})
    pd.DataFrame(prow).to_csv(out/"pair_metrics.csv",index=False)
    sensitivity(data,out)
    pd.DataFrame([prop_mc(baseline_tr,r) for r in (0.0025,0.005,0.01)]).to_csv(out/"prop_simulations.csv",index=False)

    (out/"strategy_reconstruction.json").write_text(json.dumps({
      "frozen_baseline_pairs":BASELINE_PAIRS,"exploratory_data_pairs":DATA_PAIRS,"params":asdict(p),
      "rules":{"d1_regime":"EMA50/EMA200 plus EMA50 5-day slope, latest completed D1 only",
        "signal":"strict 20-H4 breakout; true range <=2x ATR14; eligible UTC close only",
        "entry":"next H4 open; cancel if adverse displacement >0.20x signal ATR","sl":"1.50x signal ATR","tp":"2.50R",
        "breakeven":"after completed H4 close >= +1.50R, cost-adjusted BE","friday_cutoff":"16:00 UTC",
        "h1_confirmation":False,"d1_trend_invalidation_exit":False,"unfrozen_volatility_quantile_filter":False,"unfrozen_30_day_time_stop":False},
      "limitations":["price-only first-pass dataset; not final validation","news exits/blocks not modeled in this dataset",
        "spread is fixed approximation, not historical bid/ask","slippage fixed approximation","exact prop firm reset/trailing/news rules not modeled",
        "AUDUSD excluded from frozen baseline; may be tested later as an exploratory missing-pair candidate"]},indent=2))
    print(pd.DataFrame(summary).to_string(index=False))

if __name__=="__main__": main()
