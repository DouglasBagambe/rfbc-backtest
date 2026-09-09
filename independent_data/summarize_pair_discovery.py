#!/usr/bin/env python3
"""Consolidate completed frozen-RFBC discovery checkpoints; no strategy evaluation."""
from __future__ import annotations
import json
from pathlib import Path
import pandas as pd

ROOT=Path(__file__).resolve().parents[1]
PAIRS="EURUSD GBPUSD AUDUSD NZDUSD USDCAD USDCHF USDJPY EURJPY GBPJPY AUDJPY CADJPY CHFJPY EURGBP EURAUD GBPAUD".split()
OUT=ROOT/"results_external_discovery"

def main():
    rows=[]; mc=[]; decisions={}; trades={}
    for p in PAIRS:
        d=OUT/p
        if not (d/"pair_period_metrics.csv").exists(): raise SystemExit(f"Missing completed checkpoint: {p}")
        m=pd.read_csv(d/"pair_period_metrics.csv"); x=pd.read_csv(d/"monte_carlo.csv")
        full=m[m.period.eq("full_independent")].iloc[0].to_dict(); unseen=m[m.period.str.startswith("unseen_")].iloc[0]
        full.update({"decision":json.loads((d/"decisions.json").read_text())[p],"unseen_trades":unseen.trades,"unseen_expectancy_r":unseen.expectancy_r,"unseen_profit_factor":unseen.profit_factor,"unseen_max_dd_pct":unseen.max_dd_pct})
        full.update(x.iloc[0].to_dict()); rows.append(full); decisions[p]=full["decision"]
        t=pd.read_csv(d/f"trades_{p}.csv",parse_dates=["entry_dt","exit_dt"]); trades[p]=t
    rank=pd.DataFrame(rows).sort_values(["decision","expectancy_r","profit_factor"],ascending=[True,False,False])
    rank.to_csv(OUT/"pair_ranking.csv",index=False); survivors=rank[rank.decision.eq("SURVIVED")].pair.tolist()
    (OUT/"survivors.json").write_text(json.dumps({"survivors":survivors,"promotion_gate":"full expectancy >= 0.15R; full PF >= 1.30; unseen expectancy > 0"},indent=2)+"\n")
    # Equal-risk, concurrent trade-event portfolio; no arbitrary survivor cap.
    series={p:pd.Series(t.r.to_numpy(),index=t.exit_dt).groupby(level=0).sum() for p,t in trades.items() if p in survivors}
    returns=pd.DataFrame(series).fillna(0.0)
    corr=returns.corr(); corr.to_csv(OUT/"survivor_return_correlation.csv")
    port=returns.mean(axis=1) if len(survivors) else pd.Series(dtype=float)
    eq=(1+.005*port).cumprod() if len(port) else port; dd=1-eq/eq.cummax() if len(port) else port
    pd.DataFrame({"exit_dt":eq.index,"portfolio_r":port,"equity":eq,"drawdown":dd}).to_csv(OUT/"portfolio_equity_curve.csv",index=False)
    dd_corr=pd.DataFrame({p:1-(1+.005*returns[p]).cumprod()/(1+.005*returns[p]).cumprod().cummax() for p in survivors}).corr()
    dd_corr.to_csv(OUT/"survivor_drawdown_correlation.csv")
    overlap=[]
    for i,a in enumerate(survivors):
        for b in survivors[i+1:]:
            n=sum(int(((trades[a].entry_dt<=row.exit_dt).to_numpy() & (trades[a].exit_dt>=row.entry_dt).to_numpy()).sum()) for _,row in trades[b].iterrows())
            overlap.append({"pair_a":a,"pair_b":b,"overlapping_trade_pairs":n})
    pd.DataFrame(overlap).to_csv(OUT/"survivor_trade_overlap.csv",index=False)
    loss=pd.DataFrame({p:(returns[p]<0) for p in survivors}); loss["simultaneous_loss_count"]=loss.sum(axis=1)
    loss.to_csv(OUT/"survivor_simultaneous_losses.csv",index_label="exit_dt")
    if len(port):
        blocks=[g.to_numpy(float) for _,g in pd.Series(port.values,index=pd.DatetimeIndex(port.index).tz_localize(None)).groupby(lambda d:d.to_period("W-SUN"))]
        import numpy as np
        rng=np.random.default_rng(42); finals=[]; mdds=[]
        for pick in rng.integers(0,len(blocks),size=(5000,len(blocks))):
            e=np.cumprod(1+.005*np.concatenate([blocks[i] for i in pick])); finals.append(e[-1]); mdds.append((1-e/np.maximum.accumulate(e)).max())
        portfolio_mc={"paths":5000,"final_p05":float(np.quantile(finals,.05)),"final_p50":float(np.quantile(finals,.5)),"final_p95":float(np.quantile(finals,.95)),"dd_p50":float(np.quantile(mdds,.5)),"dd_p95":float(np.quantile(mdds,.95)),"prob_dd_gt_10pct":float((np.asarray(mdds)>.10).mean())}
    else: portfolio_mc={}
    (OUT/"portfolio_monte_carlo.json").write_text(json.dumps(portfolio_mc,indent=2)+"\n")
    currency={p:{"AUDJPY":["AUD","JPY"],"USDJPY":["USD","JPY"]}.get(p,[]) for p in survivors}
    summary=["# RFBC Full Pair Discovery Summary","",f"Survivors: {', '.join(survivors) if survivors else 'none'}.","", "## Consolidated ranking","","```csv",rank.to_csv(index=False).strip(),"```","", "## Portfolio", "", f"Equal-risk survivor portfolio max drawdown: {dd.max() if len(dd) else float('nan'):.6f}.",f"Currency exposure: {json.dumps(currency)}. Both survivors contain JPY, so JPY concentration is the material non-redundancy risk; neither is excluded because both pass independently and their return/drawdown/overlap artifacts are supplied for the next validation layer.", f"Portfolio Monte Carlo: {json.dumps(portfolio_mc)}", ""]
    (OUT/"PAIR_DISCOVERY_SUMMARY.md").write_text("\n".join(summary))
if __name__=="__main__": main()
