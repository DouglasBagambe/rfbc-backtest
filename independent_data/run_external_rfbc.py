"""Frozen USDJPY RFBC replication on independently sourced Dukascopy BID/ASK bars."""
from __future__ import annotations

import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import backtest

DATA = ROOT / "data_independent" / "derived" / "USDJPY"
OUT = ROOT / "results_external_dukascopy"
PIP = .01


@dataclass(frozen=True)
class Candidate:
    code: str
    breakout_lookback: int
    atr_mult: float
    rr: float


CANDIDATES = [
    Candidate("A_frozen_usdjpy_v10", 20, 1.50, 2.50),
    Candidate("B_l25_atr150_rr300", 25, 1.50, 3.00),
    Candidate("C_l25_atr175_rr250", 25, 1.75, 2.50),
]
PERIODS = {
    "overlap_2013_to_2022_03_03": ("2013-01-01", "2022-03-03"),
    "unseen_2022_03_04_to_2026_09_01": ("2022-03-04", "2026-09-01"),
    "full_independent": ("2013-01-01", "2026-09-01"),
}


def read(name: str) -> pd.DataFrame:
    return pd.read_csv(DATA / name, parse_dates=["dt"])


def prepare(candidate: Candidate) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    d1 = read("USDJPY_bid_d1.csv")
    h4_bid, h4_ask = read("USDJPY_bid_h4.csv"), read("USDJPY_ask_h4.csv")
    h1_bid, h1_ask = read("USDJPY_bid_h1.csv"), read("USDJPY_ask_h1.csv")
    d1["ema_fast"] = backtest.ema(d1.close, 50); d1["ema_slow"] = backtest.ema(d1.close, 200)
    d1["ema_fast_prev"] = d1.ema_fast.shift(5); d1["regime"] = 0
    d1.loc[(d1.close>d1.ema_fast)&(d1.ema_fast>d1.ema_slow)&(d1.ema_fast>d1.ema_fast_prev),"regime"] = 1
    d1.loc[(d1.close<d1.ema_fast)&(d1.ema_fast<d1.ema_slow)&(d1.ema_fast<d1.ema_fast_prev),"regime"] = -1
    h4_bid["atr"] = backtest.atr(h4_bid, 14); prev = h4_bid.close.shift(1)
    h4_bid["tr"] = pd.concat([(h4_bid.high-h4_bid.low).abs(), (h4_bid.high-prev).abs(), (h4_bid.low-prev).abs()],axis=1).max(axis=1)
    h4_bid["prev_high"] = h4_bid.high.shift(1).rolling(candidate.breakout_lookback).max()
    h4_bid["prev_low"] = h4_bid.low.shift(1).rolling(candidate.breakout_lookback).min()
    h4_bid["close_dt"] = h4_bid.dt + pd.Timedelta(hours=4)
    dm=d1[["dt","regime"]].copy(); dm["available_dt"] = dm.dt + pd.Timedelta(days=1)
    h4_bid=pd.merge_asof(h4_bid.sort_values("close_dt"),dm[["available_dt","regime"]].sort_values("available_dt"),left_on="close_dt",right_on="available_dt",direction="backward")
    actionable=h4_bid.close_dt.map(lambda ts: ts.weekday()<=3 and ts.hour in (8,12,16) or ts.weekday()==4 and ts.hour in (8,12))
    h4_bid["signal"] = 0
    common=actionable & np.isfinite(h4_bid.atr) & (h4_bid.atr>0) & (h4_bid.tr<=2*h4_bid.atr)
    h4_bid.loc[common&(h4_bid.regime.eq(1))&(h4_bid.close>h4_bid.prev_high),"signal"] = 1
    h4_bid.loc[common&(h4_bid.regime.eq(-1))&(h4_bid.close<h4_bid.prev_low),"signal"] = -1
    h1=h1_bid.merge(h1_ask,on="dt",suffixes=("_bid","_ask"),validate="one_to_one").set_index("dt")
    return h4_bid.reset_index(drop=True), h4_ask.reset_index(drop=True), h1


def run(candidate: Candidate) -> tuple[pd.DataFrame, int, int]:
    h4, ask4, h1 = prepare(candidate); trades=[]; next_allowed=pd.Timestamp.min.tz_localize("UTC"); ambiguous=unclosed=0
    h4_closes=dict(zip(h4.close_dt, h4.close))
    for i in np.flatnonzero(h4.signal.to_numpy()):
        signal=h4.iloc[i]; signal_dt=signal.close_dt
        if i+1>=len(h4) or signal_dt<=next_allowed: continue
        side=int(signal.signal); entry=float(ask4.open.iat[i+1] if side==1 else h4.open.iat[i+1])
        adverse=side*(entry-float(signal.close))
        if adverse>.20*float(signal.atr): continue
        risk=candidate.atr_mult*float(signal.atr); stop=entry-side*risk; target=entry+side*candidate.rr*risk; be_stop=entry
        armed=False; exit_px=exit_dt=reason=None
        entry_dt=h4.dt.iat[i+1]
        for dt,b in h1.loc[entry_dt:].iterrows():
            if dt.weekday()==4 and dt.hour>=16:
                exit_px=float(b.open_bid if side==1 else b.open_ask); exit_dt=dt; reason="FRIDAY"; break
            low=float(b.low_bid if side==1 else b.low_ask); high=float(b.high_bid if side==1 else b.high_ask)
            active=be_stop if armed else stop
            stop_hit=low<=active if side==1 else high>=active
            target_hit=high>=target if side==1 else low<=target
            if stop_hit and target_hit: ambiguous+=1
            if stop_hit or target_hit:
                exit_px=active if stop_hit else target; exit_dt=dt; reason="BE" if stop_hit and armed else "SL" if stop_hit else "TP"; break
            boundary=dt+pd.Timedelta(hours=1)
            if boundary in h4_closes and side*(h4_closes[boundary]-entry)/risk>=1.50: armed=True
        if exit_px is None:
            unclosed+=1; continue
        r=side*(float(exit_px)-entry)/risk
        trades.append({"candidate":candidate.code,"signal_dt":signal_dt,"entry_dt":entry_dt,"exit_dt":exit_dt,"side":side,"entry":entry,"exit":exit_px,"stop":stop,"target":target,"reason":reason,"r":r})
        next_allowed=exit_dt
    return pd.DataFrame(trades), ambiguous, unclosed


def metrics(t: pd.DataFrame, risk: float=.005) -> dict:
    if t.empty: return {"trades":0}
    t=t.sort_values("exit_dt"); r=t.r.to_numpy(float); equity=np.cumprod(1+risk*r); dd=1-equity/np.maximum.accumulate(equity)
    wins,losses=r[r>0],r[r<=0]
    first_month=t.entry_dt.min().tz_localize(None).to_period("M")
    last_month=t.exit_dt.max().tz_localize(None).to_period("M")
    months=max((last_month-first_month).n+1,1); years=max((t.exit_dt.max()-t.entry_dt.min()).days/365.25,1/365.25)
    return {"trades":len(t),"trades_per_month":len(t)/months,"wins":len(wins),"losses":len(losses),"win_rate":float((r>0).mean()),"expectancy_r":float(r.mean()),"profit_factor":float(wins.sum()/-losses.sum()) if len(losses) else np.nan,"avg_win_r":float(wins.mean()) if len(wins) else np.nan,"avg_loss_r":float(losses.mean()) if len(losses) else np.nan,"max_dd_pct":float(dd.max()),"total_return_pct":float(equity[-1]-1),"cagr":float(equity[-1]**(1/years)-1),"longest_loss_streak":max(map(len,"".join("L" if x<0 else "W" for x in r).split("W")))}


def mc(t: pd.DataFrame, n: int=5000, risk: float=.005, seed: int=42) -> dict:
    x=t.sort_values("exit_dt").copy(); x["week"]=x.exit_dt.dt.tz_localize(None).dt.to_period("W-SUN")
    blocks=[g.r.to_numpy(float) for _,g in x.groupby("week")]
    padded=np.zeros((len(blocks),max(map(len,blocks))),dtype=float)
    for i,block in enumerate(blocks): padded[i,:len(block)]=block
    rng=np.random.default_rng(seed); picks=rng.integers(0,len(blocks),size=(n,len(blocks)))
    r=padded[picks].reshape(n,-1); equity=np.cumprod(1+risk*r,axis=1)
    dd=1-equity/np.maximum.accumulate(equity,axis=1); finals=equity[:,-1]; max_dd=dd.max(axis=1)
    return {"paths":n,"final_p05":float(np.quantile(finals,.05)),"final_p50":float(np.quantile(finals,.5)),"final_p95":float(np.quantile(finals,.95)),"dd_p50":float(np.quantile(max_dd,.5)),"dd_p95":float(np.quantile(max_dd,.95)),"prob_dd_gt_5pct":float((max_dd>.05).mean()),"prob_dd_gt_10pct":float((max_dd>.10).mean())}


def audit() -> tuple[pd.DataFrame,pd.DataFrame,pd.DataFrame]:
    b,a=read("USDJPY_bid_h1.csv"),read("USDJPY_ask_h1.csv"); merged=b.merge(a,on="dt",suffixes=("_bid","_ask"),validate="one_to_one"); spread=(merged.open_ask-merged.open_bid)*100
    actual=pd.DatetimeIndex(merged.dt); grid=pd.date_range(actual.min(),actual.max(),freq="h",tz="UTC")
    expected=grid[((grid.weekday<4)|((grid.weekday==4)&(grid.hour<21))|((grid.weekday==6)&(grid.hour>=21)))]
    missing=expected.difference(actual); md=pd.DataFrame({"dt":missing}); md["month"]=md.dt.dt.tz_localize(None).dt.to_period("M").astype(str); missing_months=md.groupby("month").size().rename("missing_h1_bars").reset_index()
    spread_year=pd.DataFrame({"year":merged.dt.dt.year,"spread_pips":spread}).groupby("year").spread_pips.agg(["count","median",lambda x:x.quantile(.95)]).reset_index().rename(columns={"<lambda_0>":"p95"})
    h4=read("USDJPY_bid_h4.csv"); d1=read("USDJPY_bid_d1.csv")
    manifest=pd.DataFrame([{"h1_first":str(actual.min()),"h1_last":str(actual.max()),"h1_bid_ask_exact_alignment":bool(b.dt.equals(a.dt)),"h1_duplicate_timestamps":int(actual.duplicated().sum()),"crossed_open_spreads":int((spread<0).sum()),"h4_allowed_utc_opens":bool(set(h4.dt.dt.hour).issubset({0,4,8,12,16,20})),"d1_midnight_utc":bool((d1.dt.dt.hour==0).all()),"missing_expected_h1_bars":len(missing)}])
    return manifest,missing_months,spread_year


def main() -> None:
    OUT.mkdir(exist_ok=True); manifest,missing,spread=audit(); manifest.to_csv(OUT/"dataset_audit.csv",index=False); missing.to_csv(OUT/"missing_h1_by_month.csv",index=False); spread.to_csv(OUT/"spread_by_year.csv",index=False)
    all_metrics=[]; mc_rows=[]; yearly_frames={}
    survivors=[]
    for c in CANDIDATES:
        t,ambiguous,unclosed=run(c); t.to_csv(OUT/f"trades_{c.code}.csv",index=False)
        for period,(start,end) in PERIODS.items():
            s=t[t.entry_dt.dt.normalize().between(pd.Timestamp(start,tz="UTC"),pd.Timestamp(end,tz="UTC"))]
            all_metrics.append({"candidate":c.code,"period":period,"ambiguous_h1_stop_first_events":ambiguous,"unclosed_at_data_end":unclosed,**metrics(s)})
        yearly=pd.DataFrame([{"year":y,**metrics(g)} for y,g in t.assign(year=t.entry_dt.dt.year).groupby("year")]); yearly.to_csv(OUT/f"yearly_{c.code}.csv",index=False); yearly_frames[c.code]=yearly
        full=metrics(t); mc_rows.append({"candidate":c.code,**mc(t)}); survivors.append((c,full))
    metrics_frame=pd.DataFrame(all_metrics); metrics_frame.to_csv(OUT/"candidate_period_metrics.csv",index=False)
    mc_frame=pd.DataFrame(mc_rows); mc_frame.to_csv(OUT/"monte_carlo_full_independent.csv",index=False)
    unseen=metrics_frame[metrics_frame.period.eq("unseen_2022_03_04_to_2026_09_01")].set_index("candidate")
    passed=[(c,m) for c,m in survivors if m.get("expectancy_r",-99)>=.15 and m.get("profit_factor",0)>=1.30 and unseen.loc[c.code,"expectancy_r"]>0]
    decision="RFBC USDJPY CANDIDATE SURVIVED EXTERNAL REPLICATION" if passed else "RFBC EXTERNALLY REJECTED"
    report=[
        "# Dukascopy USDJPY External RFBC Replication",
        "",
        "## Scope and execution",
        "",
        "This is the first independent external USDJPY replication. Data is Dukascopy H1 BID/ASK from 2013-01-01 through 2026-09-01 UTC. Signals are constructed from BID bars. Long entries use ASK and long exits/SL/TP use BID; short entries use BID and short exits/SL/TP use ASK.",
        "",
        "The frozen rules tested are D1 EMA50/EMA200 regime with five-day EMA50 slope using completed D1 only; H4 ATR14 and true-range gate; the exact eligible UTC checkpoints; next-H4 entry; 0.20 ATR no-chase; completed-H4 +1.50R breakeven; Friday 16:00 UTC cutoff; and no H1 confirmation, D1-invalidation exit, extra volatility filter, or time stop. Any H1 candle touching both stop and target is resolved stop-first.",
        "",
        "## Data validation",
        "",
        "```csv",
        manifest.to_csv(index=False).strip(),
        "```",
        "",
        f"The downloader completed all 165 requested calendar months for each side with no persistent month failure. The {int(manifest.missing_expected_h1_bars.iat[0])} missing expected-session H1 timestamps are explicitly listed by month in `missing_h1_by_month.csv`; they are retained as data/market-closure gaps, not filled or silently skipped. The final raw H1 timestamp is 2026-09-01 21:00 UTC; incomplete final H4/D1 buckets are excluded from the derived H4/D1 series.",
        "",
        "### Opening spread by year (pips)",
        "",
        "```csv",
        spread.to_csv(index=False).strip(),
        "```",
        "",
        "## Candidate definitions",
        "",
        "- A — 20 H4 breakout, 1.50 ATR stop, 2.50R target (USDJPY frozen RFBC v1.0 subset).",
        "- B — 25 H4 breakout, 1.50 ATR stop, 3.00R target.",
        "- C — 25 H4 breakout, 1.75 ATR stop, 2.50R target.",
        "",
        "## Period metrics",
        "",
        "Returns, CAGR and drawdown use fixed 0.5% risk per trade. All R metrics use actual BID/ASK execution prices.",
        "",
        "```csv",
        metrics_frame.to_csv(index=False).strip(),
        "```",
        "",
        "## Yearly performance",
        "",
    ]
    for c in CANDIDATES:
        report.extend([f"### {c.code}", "", "```csv", yearly_frames[c.code].to_csv(index=False).strip(), "```", ""])
    report.extend(["## Weekly block-bootstrap Monte Carlo — full independent sample", "", "5,000 paths, resampling weekly trade blocks with a fixed random seed (42); final values are equity multipliers from normalized starting equity of 1.0.", "", "```csv", mc_frame.to_csv(index=False).strip(), "```"])
    report.extend(["", f"## Decision: {decision}", ""])
    if passed:
        names=", ".join(c.code for c,_ in passed)
        report.extend([f"{names} meets the stated independent-sample survival benchmark: full-sample expectancy at least +0.15R, profit factor at least 1.30, and positive truly unseen 2022-03-04 onward expectancy. The remaining candidates do not meet the full-sample benchmark.", "", "This is not authorization to trade. The surviving candidate is flagged only for the next validation layer; no parameters were tuned from this external result."])
    else:
        report.append("None of the candidates meets the stated independent-sample survival benchmark. RFBC should be archived rather than retuned from this result.")
    (OUT/"DUKASCOPY_USDJPY_EXTERNAL_REPORT.md").write_text("\n".join(report)+"\n")
    (OUT/"candidate_definitions.json").write_text(json.dumps([asdict(c) for c in CANDIDATES],indent=2))


if __name__=="__main__": main()
