"""Bounded exploratory screen for non-RFBC forex strategy families.

All signals are known at the completed H4 close; entries use the next H4 open.
This is a research screen, not a claim of validation or a live-trading system.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import json
import sys

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import backtest

DATA, OUT = ROOT / "data", ROOT / "results_next_strategy"
PAIRS = ["EURUSD", "GBPUSD", "USDJPY", "AUDUSD"]
SPREAD = {"EURUSD": .9, "GBPUSD": 1.2, "USDJPY": 1.0, "AUDUSD": 1.1}
SPLITS = {"development": (2013, 2016), "validation": (2017, 2019), "holdout": (2020, 2022)}


@dataclass(frozen=True)
class Spec:
    family: str
    rationale: str
    lookback: int = 20
    stop_atr: float = 1.5
    rr: float = 2.0
    max_bars: int = 20


SPECS = [
    Spec("trend_pullback", "D1 trend; controlled H4 pullback to EMA20 with a same-bar continuation close."),
    Spec("contraction_expansion", "D1 trend; a low-volatility H4 regime followed by a range expansion and breakout."),
    Spec("range_mean_reversion", "Low D1 trend separation; H4 extension from its mean followed by a reversal candle." , rr=1.2, max_bars=12),
    Spec("session_momentum", "D1 trend; 08:00 UTC H4 expansion candle aligned with the higher-timeframe regime.", rr=1.8),
    Spec("breakout_retest", "D1 trend; a preceding H4 range breakout followed by a successful retest, not a raw breakout."),
    Spec("mtf_momentum", "D1 regime plus aligned H4 EMA20/EMA50 momentum and a three-bar expansion."),
]


def prep(pair: str) -> pd.DataFrame:
    d1 = backtest.load_csv(DATA / f"{pair}d1.csv")
    h = backtest.load_csv(DATA / f"{pair}h4.csv")
    d1["fast"] = backtest.ema(d1.close, 50); d1["slow"] = backtest.ema(d1.close, 200)
    d1["atr_d1"] = backtest.atr(d1, 14)
    d1["regime"] = np.where((d1.close > d1.fast) & (d1.fast > d1.slow), 1, np.where((d1.close < d1.fast) & (d1.fast < d1.slow), -1, 0))
    d1["sep_d1_atr"] = (d1.fast - d1.slow).abs() / d1.atr_d1
    dm = d1[["dt", "regime", "sep_d1_atr"]].copy(); dm["available"] = dm.dt + pd.Timedelta(days=1)
    h["atr"] = backtest.atr(h, 14); h["ema20"] = backtest.ema(h.close, 20); h["ema50"] = backtest.ema(h.close, 50)
    h["sma20"] = h.close.rolling(20).mean(); h["tr"] = pd.concat([(h.high-h.low).abs(), (h.high-h.close.shift()).abs(), (h.low-h.close.shift()).abs()], axis=1).max(axis=1)
    h["prev_hi"] = h.high.shift(1).rolling(20).max(); h["prev_lo"] = h.low.shift(1).rolling(20).min()
    h["atr_low"] = h.atr.shift(1).rolling(100, min_periods=50).quantile(.25)
    h["close_dt"] = h.dt + pd.Timedelta(hours=4)
    h = pd.merge_asof(h.sort_values("close_dt"), dm[["available", "regime", "sep_d1_atr"]].sort_values("available"), left_on="close_dt", right_on="available", direction="backward")
    return h.reset_index(drop=True)


def signals(h: pd.DataFrame, spec: Spec) -> np.ndarray:
    up, down = h.regime.eq(1), h.regime.eq(-1)
    bull, bear = h.close.gt(h.open), h.close.lt(h.open)
    if spec.family == "trend_pullback":
        return np.where(up & h.low.le(h.ema20) & h.close.gt(h.ema20) & bull, 1, np.where(down & h.high.ge(h.ema20) & h.close.lt(h.ema20) & bear, -1, 0))
    if spec.family == "contraction_expansion":
        common = h.atr.le(h.atr_low) & h.tr.ge(1.2*h.atr)
        return np.where(common & up & h.close.gt(h.prev_hi), 1, np.where(common & down & h.close.lt(h.prev_lo), -1, 0))
    if spec.family == "range_mean_reversion":
        rng = h.sep_d1_atr.le(.6); deviation = (h.close-h.sma20)/h.atr
        return np.where(rng & deviation.le(-1.5) & bull, 1, np.where(rng & deviation.ge(1.5) & bear, -1, 0))
    if spec.family == "session_momentum":
        common = h.close_dt.dt.hour.eq(8) & h.tr.ge(h.atr) & ((h.close-h.low)/(h.high-h.low).replace(0, np.nan)).ge(.7)
        return np.where(common & up & bull, 1, np.where(common & down & bear, -1, 0))
    if spec.family == "breakout_retest":
        prior_up = h.close.shift(1).gt(h.prev_hi.shift(1)); prior_down = h.close.shift(1).lt(h.prev_lo.shift(1))
        return np.where(up & prior_up & h.low.le(h.prev_hi.shift(1)) & h.close.gt(h.prev_hi.shift(1)), 1, np.where(down & prior_down & h.high.ge(h.prev_lo.shift(1)) & h.close.lt(h.prev_lo.shift(1)), -1, 0))
    if spec.family == "mtf_momentum":
        move = (h.close-h.close.shift(3))/h.atr
        return np.where(up & h.ema20.gt(h.ema50) & move.ge(1.0), 1, np.where(down & h.ema20.lt(h.ema50) & move.le(-1.0), -1, 0))
    raise ValueError(spec.family)


def run_pair(pair: str, spec: Spec) -> pd.DataFrame:
    h = prep(pair); sig = signals(h, spec); pip = 10.0; cost = (SPREAD[pair] + .4) * pip
    trades, next_allowed = [], pd.Timestamp.min
    for i in np.flatnonzero(sig):
        if i + 1 >= len(h) or h.close_dt.iat[i] <= next_allowed or not np.isfinite(h.atr.iat[i]):
            continue
        side, entry = int(sig[i]), float(h.open.iat[i+1] + sig[i]*cost/2)
        risk = spec.stop_atr * float(h.atr.iat[i]); stop, target = entry-side*risk, entry+side*spec.rr*risk
        exit_px = exit_dt = reason = None
        for j in range(i+1, min(len(h), i+1+spec.max_bars)):
            b = h.iloc[j]; dt = b.close_dt
            if dt.weekday() == 4 and dt.hour >= 16:
                exit_px, exit_dt, reason = float(b.open)-side*cost/2, dt, "FRIDAY"; break
            stop_hit = b.low <= stop if side == 1 else b.high >= stop
            target_hit = b.high >= target if side == 1 else b.low <= target
            if stop_hit or target_hit:
                # Conservative intrabar ordering when both levels are hit.
                exit_px, exit_dt, reason = (stop if stop_hit else target)-side*cost/2, dt, "SL" if stop_hit else "TP"; break
        if exit_px is None:
            b = h.iloc[min(len(h)-1, i+spec.max_bars)]
            exit_px, exit_dt, reason = float(b.close)-side*cost/2, b.close_dt, "TIME"
        trades.append({"family": spec.family, "pair": pair, "signal_dt": h.close_dt.iat[i], "entry_dt": h.dt.iat[i+1], "exit_dt": exit_dt, "side": side, "r": side*(exit_px-entry)/risk, "reason": reason})
        next_allowed = exit_dt
    return pd.DataFrame(trades)


def metrics(t: pd.DataFrame, risk: float=.005) -> dict:
    if t.empty: return {"trades": 0, "expectancy_r": np.nan, "profit_factor": np.nan, "win_rate": np.nan, "max_dd_pct": np.nan, "return_pct": np.nan, "cagr": np.nan, "trades_per_month": 0, "longest_loss_streak": 0}
    r = t.sort_values("exit_dt").r.to_numpy(float); equity = np.cumprod(1+risk*r); dd = 1-equity/np.maximum.accumulate(equity)
    wins, losses = r[r>0], r[r<=0]; years=max((t.exit_dt.max()-t.entry_dt.min()).days/365.25, 1/365.25); months=max((t.exit_dt.max().to_period("M")-t.entry_dt.min().to_period("M")).n+1, 1)
    return {"trades":len(t), "expectancy_r":float(r.mean()), "profit_factor":float(wins.sum()/-losses.sum()) if len(losses) else np.nan, "win_rate":float((r>0).mean()), "max_dd_pct":float(dd.max()), "return_pct":float(equity[-1]-1), "cagr":float(equity[-1]**(1/years)-1), "trades_per_month":float(len(t)/months), "longest_loss_streak":max(map(len, "".join("L" if x<0 else "W" for x in r).split("W")))}


def splits(t: pd.DataFrame) -> pd.DataFrame:
    t=t.copy(); t["year"]=t.entry_dt.dt.year
    return pd.DataFrame([{"split":name, **metrics(t[t.year.between(a,b)])} for name,(a,b) in SPLITS.items()])


def bootstrap(t: pd.DataFrame, risk: float, n: int=2000, seed: int=91) -> dict:
    """Fast sequential weekly block bootstrap; paths use synthetic weeks/days."""
    t=t.sort_values("exit_dt").copy(); t["week"]=t.exit_dt.dt.to_period("W-SUN")
    blocks=[g.r.to_numpy(float) for _,g in t.groupby("week")]
    if not blocks: return {}
    rng=np.random.default_rng(seed); finals=[]; dds=[]
    for choices in rng.integers(0,len(blocks),size=(n,len(blocks))):
        r=np.concatenate([blocks[i] for i in choices]); e=np.cumprod(1+risk*r); finals.append(e[-1]); dds.append((1-e/np.maximum.accumulate(e)).max())
    return {"paths":n,"risk_pct":risk,"final_p05":float(np.quantile(finals,.05)),"final_p50":float(np.quantile(finals,.5)),"final_p95":float(np.quantile(finals,.95)),"dd_p50":float(np.quantile(dds,.5)),"dd_p95":float(np.quantile(dds,.95))}


def main() -> None:
    OUT.mkdir(exist_ok=True); log=[]; all_trades=[]
    for spec in SPECS:
        trades=pd.concat([run_pair(pair,spec) for pair in PAIRS], ignore_index=True); all_trades.append(trades)
        split=splits(trades); full=metrics(trades); dev, val, hold=[split.iloc[i] for i in range(3)]
        promoted=bool(dev.expectancy_r>=.15 and dev.profit_factor>=1.3 and val.expectancy_r>0 and val.profit_factor>=1.0)
        log.append({"family":spec.family,"rationale":spec.rationale,"promoted_after_validation":promoted,**full,"development_expectancy_r":dev.expectancy_r,"validation_expectancy_r":val.expectancy_r,"holdout_expectancy_r":hold.expectancy_r})
        trades.to_csv(OUT/f"trades_{spec.family}.csv",index=False); split.to_csv(OUT/f"splits_{spec.family}.csv",index=False)
        pd.DataFrame([{"year":y,**metrics(g)} for y,g in trades.assign(year=trades.entry_dt.dt.year).groupby("year")]).to_csv(OUT/f"yearly_{spec.family}.csv",index=False)
    screen=pd.DataFrame(log).sort_values(["promoted_after_validation","validation_expectancy_r","development_expectancy_r"],ascending=False)
    screen.to_csv(OUT/"prototype_screen.csv",index=False)
    survivors=screen[screen.promoted_after_validation]
    robust=[]
    for name in survivors.family.head(3):
        base=next(s for s in SPECS if s.family==name)
        for stop in (base.stop_atr*.8,base.stop_atr,base.stop_atr*1.2):
            for rr in (base.rr*.8,base.rr,base.rr*1.2):
                spec=Spec(**{**base.__dict__,"stop_atr":round(stop,2),"rr":round(rr,2)})
                t=pd.concat([run_pair(p,spec) for p in PAIRS],ignore_index=True); sp=splits(t)
                robust.append({"family":name,"stop_atr":spec.stop_atr,"rr":spec.rr,**metrics(t),"development_expectancy_r":sp.expectancy_r.iat[0],"validation_expectancy_r":sp.expectancy_r.iat[1],"holdout_expectancy_r":sp.expectancy_r.iat[2]})
    pd.DataFrame(robust).to_csv(OUT/"survivor_parameter_neighborhoods.csv",index=False)
    mc=[]
    for name in survivors.family.head(3):
        t=next(x for x in all_trades if not x.empty and x.family.iat[0]==name)
        for risk in (.0025,.005,.01): mc.append({"family":name,**bootstrap(t,risk)})
    pd.DataFrame(mc).to_csv(OUT/"survivor_monte_carlo.csv",index=False)
    rejected=screen[~screen.promoted_after_validation][["family","rationale","development_expectancy_r","validation_expectancy_r","holdout_expectancy_r","profit_factor","max_dd_pct"]]
    rejected.to_csv(OUT/"rejected_families.csv",index=False)
    report=["# Next Strategy Research Report","","## Scope","","RFBC was not modified. Track 1 independent RFBC replication is **not completed**: HistData exposes independent M1 bid-price archives, but a reliable multi-year download/resampling path was not technically practical in this constrained run. RFBC survival is therefore **UNKNOWN**, not YES.","","## Stage A/B prototype screen","","```csv",screen.to_csv(index=False).rstrip(),"```","","## Decision",""
    ]
    if survivors.empty:
        report.append("**NO ROBUST STRATEGY FOUND.** All six non-RFBC prototype families were rejected before holdout promotion because they failed the predeclared development/validation gate. No parameters were tuned on holdout.")
    else:
        report.append("Survivors are exploratory only. See the parameter-neighborhood and Monte Carlo CSVs; no candidate is frozen without independent data.")
    report.extend(["","## Required next step","","Acquire a versioned, independently sourced bid/ask dataset, validate UTC/session and candle construction, rerun unchanged prototypes, then evaluate any survivor on untouched external data. Do not connect to MT5/Exness or trade."])
    (OUT/"NEXT_STRATEGY_RESEARCH_REPORT.md").write_text("\n".join(report)+"\n")
    (OUT/"candidate_definitions.json").write_text(json.dumps([s.__dict__ for s in SPECS],indent=2))


if __name__=="__main__": main()
