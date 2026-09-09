#!/usr/bin/env python3
"""Stage A/B M15/H1 BID/ASK falsification screen for the frozen S2 register.

This is intentionally separate from RFBC. Signals use completed BID M15/H1
bars; the next M15 open is executed on ASK for longs and BID for shorts.
Stops/targets are evaluated on executable prices and ambiguous same-bar events
are stop-first. The script never reads the post-2020 holdout period.
"""
from __future__ import annotations

import argparse
import gc
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PAIRS = ("EURUSD", "GBPUSD", "USDJPY")
DEV_END = pd.Timestamp("2018-01-01", tz="UTC")
VALIDATION_END = pd.Timestamp("2021-01-01", tz="UTC")
SLIPPAGE_PIPS = 0.10
SCREEN_GATE = {
    "development_expectancy_r": 0.10,
    "development_profit_factor": 1.15,
    "validation_expectancy_r": 0.05,
    "validation_profit_factor": 1.10,
    "minimum_combined_trades": 120,
}


@dataclass(frozen=True)
class Spec:
    hypothesis: str
    family: str
    stop_atr: float = 1.0
    reward_risk: float = 1.25
    max_bars: int = 16


SPECS = (
    Spec("S2-01", "trend_pullback"), Spec("S2-02", "first_pullback"),
    Spec("S2-03", "london_bias_pullback"), Spec("S2-04", "london_or_break"),
    Spec("S2-05", "ny_or_break"), Spec("S2-06", "london_failed_break", reward_risk=1.1),
    Spec("S2-07", "rolling_mean_reversion", reward_risk=1.0), Spec("S2-08", "asia_reclaim", reward_risk=1.0),
    Spec("S2-09", "shock_reversion", reward_risk=1.0), Spec("S2-10", "compression_break"),
    Spec("S2-11", "trend_compression_break"), Spec("S2-12", "session_sweep_reclaim", reward_risk=1.1),
    Spec("S2-13", "equal_level_sweep", reward_risk=1.1), Spec("S2-14", "impulse_retrace"),
    Spec("S2-15", "three_bar_momentum"), Spec("S2-16", "london_fix_momentum"),
    Spec("S2-17", "ny_open_london_position"), Spec("S2-18", "asia_compression_london_break"),
    Spec("S2-19", "ema_reclaim_microbreak"), Spec("S2-20", "weekly_failed_break", reward_risk=1.1),
)


def atr(frame: pd.DataFrame, n: int) -> pd.Series:
    prev = frame.close.shift()
    return pd.concat((frame.high - frame.low, (frame.high - prev).abs(), (frame.low - prev).abs()), axis=1).max(axis=1).rolling(n).mean()


def pip_size(pair: str) -> float:
    return 0.01 if pair.endswith("JPY") else 0.0001


def load_pair(data_root: Path, pair: str) -> pd.DataFrame:
    pair_dir = data_root / pair
    def load(side: str, tf: str) -> pd.DataFrame:
        f = pair_dir / f"{pair}_{side}_{tf}.csv"
        # Do not retain volume or float64 columns: neither participates in this
        # screen and this keeps a full 13-year M15 pair within a low-RAM budget.
        chunks = []
        for chunk in pd.read_csv(
            f, usecols=["dt", "open", "high", "low", "close"], parse_dates=["dt"],
            dtype={"open": "float32", "high": "float32", "low": "float32", "close": "float32"}, chunksize=40_000,
        ):
            # The untouched holdout is excluded before it can enter memory.
            chunks.append(chunk.loc[chunk.dt < VALIDATION_END])
        frame = pd.concat(chunks, ignore_index=True)
        frame["dt"] = pd.to_datetime(frame.dt, utc=True)
        return frame.set_index("dt").sort_index()
    bid, ask, h1 = load("bid", "m15"), load("ask", "m15"), load("bid", "h1")
    if not bid.index.equals(ask.index):
        raise RuntimeError(f"{pair}: BID/ASK M15 indexes are not aligned")
    out = bid.add_prefix("bid_").join(ask.add_prefix("ask_"), how="inner")
    out = out.rename(columns={"bid_open": "open", "bid_high": "high", "bid_low": "low", "bid_close": "close"})
    out["atr15"] = atr(out, 14)
    out["ema20"] = out.close.ewm(span=20, adjust=False).mean()
    out["ema50"] = out.close.ewm(span=50, adjust=False).mean()
    out["mean20"] = out.close.rolling(20).mean()
    out["std20"] = out.close.rolling(20).std()
    out["range20_hi"] = out.high.shift().rolling(20).max()
    out["range20_lo"] = out.low.shift().rolling(20).min()
    out["tr"] = pd.concat(((out.high-out.low), (out.high-out.close.shift()).abs(), (out.low-out.close.shift()).abs()), axis=1).max(axis=1)
    h1["h1_ema20"] = h1.close.ewm(span=20, adjust=False).mean()
    h1["h1_ema50"] = h1.close.ewm(span=50, adjust=False).mean()
    h1["h1_atr"] = atr(h1, 14)
    h1["h1_trend"] = np.where((h1.close > h1.h1_ema20) & (h1.h1_ema20 > h1.h1_ema50), 1, np.where((h1.close < h1.h1_ema20) & (h1.h1_ema20 < h1.h1_ema50), -1, 0))
    h1["h1_impulse"] = (h1.close-h1.close.shift(3))/h1.h1_atr
    available = h1.index + pd.Timedelta(hours=1)
    mapped = pd.merge_asof(out.reset_index().sort_values("dt"), h1[["h1_trend", "h1_impulse", "h1_atr"]].assign(available=available).reset_index(drop=True).sort_values("available"), left_on="dt", right_on="available", direction="backward")
    # A previous-week extreme only becomes available at the next UTC Monday;
    # do not use a group transform, which would leak the current week's high.
    weekly = out.groupby(out.index.to_period("W-SUN"))[["high", "low"]].agg({"high": "max", "low": "min"}).shift(1)
    weekly.index = weekly.index.to_timestamp().tz_localize("UTC")
    weekly = weekly.rename(columns={"high": "prior_week_hi", "low": "prior_week_lo"}).assign(week_available=weekly.index)
    mapped = pd.merge_asof(mapped.sort_values("dt"), weekly.reset_index(drop=True).sort_values("week_available"), left_on="dt", right_on="week_available", direction="backward")
    mapped = mapped.set_index("dt")
    mapped["hour"] = mapped.index.hour
    mapped["weekday"] = mapped.index.weekday
    mapped["date"] = mapped.index.normalize()
    mapped["week"] = mapped.index.to_period("W-MON").start_time.tz_localize("UTC")
    # Values built from only prior completed M15 bars.
    mapped["asia_hi"] = mapped.groupby("date").high.transform(lambda s: s.where(s.index.hour < 7).expanding().max()).shift()
    mapped["asia_lo"] = mapped.groupby("date").low.transform(lambda s: s.where(s.index.hour < 7).expanding().min()).shift()
    mapped["london_hi"] = mapped.groupby("date").high.transform(lambda s: s.where((s.index.hour >= 7) & (s.index.hour < 12)).expanding().max()).shift()
    mapped["london_lo"] = mapped.groupby("date").low.transform(lambda s: s.where((s.index.hour >= 7) & (s.index.hour < 12)).expanding().min()).shift()
    return mapped


def sided(long: pd.Series, short: pd.Series) -> np.ndarray:
    return np.where(long.fillna(False), 1, np.where(short.fillna(False), -1, 0))


def signals(f: pd.DataFrame, family: str) -> np.ndarray:
    up, down = f.h1_trend.eq(1), f.h1_trend.eq(-1)
    bull, bear = f.close.gt(f.open), f.close.lt(f.open)
    london = f.hour.between(7, 11); ny = f.hour.between(12, 16); overlap = f.hour.between(12, 15)
    compression = f.atr15.le(f.atr15.shift().rolling(64).quantile(.25))
    if family == "trend_pullback": return sided(london & up & f.low.le(f.ema20) & f.close.gt(f.ema20) & bull, london & down & f.high.ge(f.ema20) & f.close.lt(f.ema20) & bear)
    if family == "first_pullback": return sided(london & up & f.h1_impulse.gt(1.0) & f.low.le(f.ema20) & bull, london & down & f.h1_impulse.lt(-1.0) & f.high.ge(f.ema20) & bear)
    if family == "london_bias_pullback": return sided(ny & up & f.close.gt(f.london_hi) & f.low.le(f.ema20) & bull, ny & down & f.close.lt(f.london_lo) & f.high.ge(f.ema20) & bear)
    if family == "london_or_break": return sided(london & compression & up & f.close.gt(f.asia_hi), london & compression & down & f.close.lt(f.asia_lo))
    if family == "ny_or_break": return sided(ny & up & f.close.gt(f.london_hi), ny & down & f.close.lt(f.london_lo))
    if family == "london_failed_break": return sided(london & f.low.lt(f.asia_lo) & f.close.gt(f.asia_lo) & bull, london & f.high.gt(f.asia_hi) & f.close.lt(f.asia_hi) & bear)
    if family == "rolling_mean_reversion":
        z=(f.close-f.mean20)/f.std20
        return sided(f.hour.between(1, 6) & f.h1_trend.eq(0) & z.lt(-2) & bull, f.hour.between(1, 6) & f.h1_trend.eq(0) & z.gt(2) & bear)
    if family == "asia_reclaim": return sided(f.hour.between(1, 6) & f.low.lt(f.asia_lo) & f.close.gt(f.asia_lo), f.hour.between(1, 6) & f.high.gt(f.asia_hi) & f.close.lt(f.asia_hi))
    if family == "shock_reversion": return sided(f.tr.gt(2.5*f.atr15) & f.close.lt(f.open) & f.close.lt(f.mean20), f.tr.gt(2.5*f.atr15) & f.close.gt(f.open) & f.close.gt(f.mean20))
    if family == "compression_break": return sided(london & compression & f.close.gt(f.range20_hi), london & compression & f.close.lt(f.range20_lo))
    if family == "trend_compression_break": return sided(london & compression & up & f.close.gt(f.range20_hi), london & compression & down & f.close.lt(f.range20_lo))
    if family == "session_sweep_reclaim": return sided(london & f.low.lt(f.asia_lo) & f.close.gt(f.asia_lo), london & f.high.gt(f.asia_hi) & f.close.lt(f.asia_hi))
    if family == "equal_level_sweep": return sided(london & f.low.lt(f.range20_lo) & f.close.gt(f.range20_lo) & bull, london & f.high.gt(f.range20_hi) & f.close.lt(f.range20_hi) & bear)
    if family == "impulse_retrace": return sided(overlap & up & f.h1_impulse.gt(1) & f.low.le(f.ema20) & bull, overlap & down & f.h1_impulse.lt(-1) & f.high.ge(f.ema20) & bear)
    if family == "three_bar_momentum": return sided(overlap & up & f.close.gt(f.close.shift(3)) & f.close.shift(1).gt(f.open.shift(1)) & f.close.shift(2).gt(f.open.shift(2)), overlap & down & f.close.lt(f.close.shift(3)) & f.close.shift(1).lt(f.open.shift(1)) & f.close.shift(2).lt(f.open.shift(2)))
    if family == "london_fix_momentum": return sided(f.hour.eq(15) & up & bull, f.hour.eq(15) & down & bear)
    if family == "ny_open_london_position": return sided(f.hour.between(12, 13) & up & f.close.gt(f.london_hi), f.hour.between(12, 13) & down & f.close.lt(f.london_lo))
    if family == "asia_compression_london_break": return sided(london & compression & f.close.gt(f.asia_hi), london & compression & f.close.lt(f.asia_lo))
    if family == "ema_reclaim_microbreak": return sided(london & up & f.close.shift(1).lt(f.ema20.shift(1)) & f.close.gt(f.ema20) & f.close.gt(f.high.shift(1)), london & down & f.close.shift(1).gt(f.ema20.shift(1)) & f.close.lt(f.ema20) & f.close.lt(f.low.shift(1)))
    if family == "weekly_failed_break": return sided(f.low.lt(f.prior_week_lo) & f.close.gt(f.prior_week_lo) & f.h1_trend.eq(0), f.high.gt(f.prior_week_hi) & f.close.lt(f.prior_week_hi) & f.h1_trend.eq(0))
    raise ValueError(family)


def run_pair(f: pd.DataFrame, pair: str, spec: Spec) -> pd.DataFrame:
    sig = signals(f, spec.family); slip = SLIPPAGE_PIPS * pip_size(pair); trades=[]; next_ok=pd.Timestamp.min.tz_localize("UTC")
    for i in np.flatnonzero(sig):
        if i + 1 >= len(f) or f.index[i] >= VALIDATION_END or f.index[i] < pd.Timestamp("2013-01-01", tz="UTC") or f.index[i] < next_ok or not np.isfinite(f.atr15.iat[i]): continue
        side=int(sig[i]); entry=float(f.ask_open.iat[i+1] + slip) if side == 1 else float(f.open.iat[i+1] - slip)
        risk=spec.stop_atr * float(f.atr15.iat[i]); stop=entry-side*risk; target=entry+side*spec.reward_risk*risk
        reason="TIME"; exit_idx=min(i+spec.max_bars, len(f)-1); exit_px=None; ambiguous=False
        for j in range(i+1, min(i+spec.max_bars+1, len(f))):
            if f.index[j].weekday() == 4 and f.index[j].hour >= 16:
                exit_idx=j; reason="FRIDAY"; break
            hi=float(f.bid_high.iat[j] if side == 1 else f.ask_high.iat[j]); lo=float(f.bid_low.iat[j] if side == 1 else f.ask_low.iat[j])
            stop_hit=lo <= stop if side == 1 else hi >= stop; target_hit=hi >= target if side == 1 else lo <= target
            if stop_hit or target_hit:
                exit_idx=j; ambiguous=bool(stop_hit and target_hit); reason="SL" if stop_hit else "TP"; exit_px=stop if stop_hit else target; break
        if exit_px is None: exit_px=float(f.bid_close.iat[exit_idx] - slip) if side == 1 else float(f.ask_close.iat[exit_idx] + slip)
        trades.append({"hypothesis":spec.hypothesis,"family":spec.family,"pair":pair,"signal_dt":f.index[i],"entry_dt":f.index[i+1],"exit_dt":f.index[exit_idx],"side":side,"r":side*(exit_px-entry)/risk,"reason":reason,"ambiguous_stop_first":ambiguous})
        next_ok=f.index[exit_idx]
    return pd.DataFrame(trades)


def metrics(t: pd.DataFrame, risk: float=.005) -> dict:
    if t.empty: return {"trades":0,"expectancy_r":np.nan,"profit_factor":np.nan,"win_rate":np.nan,"max_dd_pct":np.nan,"return_pct":np.nan,"trades_per_day":0.0,"trades_per_month":0.0,"longest_loss_streak":0,"ambiguous_stop_first":0}
    r=t.sort_values("exit_dt").r.to_numpy(float); equity=np.cumprod(1+risk*r); dd=1-equity/np.maximum.accumulate(equity); wins=r[r>0]; losses=r[r<=0]
    days=max((t.exit_dt.max()-t.entry_dt.min()).days,1); months=max((t.exit_dt.max().to_period("M")-t.entry_dt.min().to_period("M")).n+1,1); streak=max(map(len,"".join("L" if value<=0 else "W" for value in r).split("W")))
    return {"trades":len(t),"expectancy_r":float(r.mean()),"profit_factor":float(wins.sum()/-losses.sum()) if len(losses) else np.nan,"win_rate":float((r>0).mean()),"max_dd_pct":float(dd.max()),"return_pct":float(equity[-1]-1),"trades_per_day":len(t)/days,"trades_per_month":len(t)/months,"longest_loss_streak":streak,"ambiguous_stop_first":int(t.ambiguous_stop_first.sum())}


def main() -> None:
    ap=argparse.ArgumentParser(); ap.add_argument("--data",default=str(ROOT/"data_independent/derived_m15")); ap.add_argument("--out",default=str(ROOT/"results_next_strategy/m15_preliminary")); ap.add_argument("--pairs",nargs="+",default=DEFAULT_PAIRS); args=ap.parse_args()
    out=Path(args.out); out.mkdir(parents=True,exist_ok=True); rows=[]
    # Keep this laptop-safe: retain at most one pair's M15/H1 frames in RAM.
    # Trade records are tiny compared with three complete source frames.
    for pair in args.pairs:
        frame = load_pair(Path(args.data), pair)
        for spec in SPECS:
            checkpoint = out / f"checkpoint_{pair}_{spec.hypothesis}.csv"
            run_pair(frame, pair, spec).to_csv(checkpoint, index=False)
        del frame
        gc.collect()
    for spec in SPECS:
        trades=pd.concat([pd.read_csv(out/f"checkpoint_{pair}_{spec.hypothesis}.csv", parse_dates=["signal_dt", "entry_dt", "exit_dt"]) for pair in args.pairs],ignore_index=True)
        trades.to_csv(out/f"trades_{spec.hypothesis}.csv",index=False)
        dev=metrics(trades[trades.entry_dt<DEV_END]); val=metrics(trades[(trades.entry_dt>=DEV_END)&(trades.entry_dt<VALIDATION_END)])
        promoted=all((dev["expectancy_r"]>=SCREEN_GATE["development_expectancy_r"],dev["profit_factor"]>=SCREEN_GATE["development_profit_factor"],val["expectancy_r"]>=SCREEN_GATE["validation_expectancy_r"],val["profit_factor"]>=SCREEN_GATE["validation_profit_factor"],dev["trades"]+val["trades"]>=SCREEN_GATE["minimum_combined_trades"]))
        rows.append({"hypothesis":spec.hypothesis,"family":spec.family,"pairs":"|".join(args.pairs),"preliminary_promoted":promoted,**{f"development_{k}":v for k,v in dev.items()},**{f"validation_{k}":v for k,v in val.items()}})
    screen=pd.DataFrame(rows).sort_values(["preliminary_promoted","validation_expectancy_r"],ascending=False); screen.to_csv(out/"screen.csv",index=False); pd.DataFrame([SCREEN_GATE]).to_json(out/"screen_gate.json",orient="records",indent=2)
    print(screen[["hypothesis","family","preliminary_promoted","development_trades","development_expectancy_r","development_profit_factor","validation_trades","validation_expectancy_r","validation_profit_factor"]].to_string(index=False))


if __name__ == "__main__": main()
