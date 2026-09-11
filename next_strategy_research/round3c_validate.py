#!/usr/bin/env python3
"""One-pass Round 3C validation of the frozen Round 3B register.

Only 2018--2020 events may create trades.  The input reader excludes 2021+
before any features are constructed; December 2017 is warm-up only.
"""
from __future__ import annotations

import argparse
import gc
from pathlib import Path

import numpy as np
import pandas as pd

import round3a_edge_map as r3a

ROOT = Path(__file__).resolve().parents[1]
START = pd.Timestamp("2018-01-01", tz="UTC")
END = pd.Timestamp("2021-01-01", tz="UTC")
WARMUP = pd.Timestamp("2017-12-01", tz="UTC")
PAIRS = r3a.PAIRS
HYPOTHESES = ("H1_MSS_REVERSAL", "H2_OB_REVERSAL", "H3_SHOCK_REVERSAL", "H4_LONDON_SWEEP_REVERSAL", "H5_PEER_CONVERGENCE")
SINGLE_COST_R = 0.10
PEER_COST_R = 0.20
MAX_BARS = 16


def atr(f: pd.DataFrame) -> pd.Series:
    return r3a.atr(f)


def read_window(path: Path) -> pd.DataFrame:
    """Retain only warm-up through validation; closed padding never enters state."""
    parts = []
    for x in pd.read_csv(path, usecols=["dt", "open", "high", "low", "close", "volume"],
                         chunksize=40_000, dtype={k: "float32" for k in ("open", "high", "low", "close", "volume")}):
        x["dt"] = pd.to_datetime(x["dt"], utc=True)
        valid = (x.volume > 0) & np.isfinite(x[["open", "high", "low", "close", "volume"]]).all(axis=1) & x.high.ge(x.low)
        keep = valid & x.dt.ge(WARMUP) & x.dt.lt(END)
        if keep.any():
            parts.append(x.loc[keep])
    if not parts:
        raise RuntimeError(f"no usable warm-up/validation rows: {path}")
    return pd.concat(parts, ignore_index=True).set_index("dt").sort_index()


def load_pair(root: Path, pair: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    d = root / pair
    m15 = read_window(d / f"{pair}_bid_m15.csv")
    h1 = read_window(d / f"{pair}_bid_h1.csv")
    return m15, h1


def selected_events(m15: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, pd.Series]]:
    """Call the unchanged Round 3A event constructors, then select frozen labels."""
    f, _ = r3a.add_context(m15.copy())
    events = r3a.primitives(f)
    events["london_open_sweep_low"] = (f.low < f.london_open_low) & (f.close >= f.london_open_low)
    events["london_open_sweep_high"] = (f.high > f.london_open_high) & (f.close <= f.london_open_high)
    shock = (f.close - f.close.shift()) / f.atr15
    events["m15_shock_down_0_5_1_0"] = (shock <= -0.5) & (shock > -1.0)
    events["m15_shock_down_1_0_1_5"] = (shock <= -1.0) & (shock > -1.5)
    events["m15_shock_up_1_0_1_5"] = (shock >= 1.0) & (shock < 1.5)
    branches = {
        "H1_MSS_REVERSAL:mss_up": events["mss_up"].fillna(False),
        "H1_MSS_REVERSAL:mss_down": events["mss_down"].fillna(False),
        "H2_OB_REVERSAL:ob_candidate_up": events["ob_candidate_up"].fillna(False),
        "H2_OB_REVERSAL:ob_candidate_down": events["ob_candidate_down"].fillna(False),
        "H3_SHOCK_REVERSAL:m15_shock_down_0_5_1_0": events["m15_shock_down_0_5_1_0"].fillna(False),
        "H3_SHOCK_REVERSAL:m15_shock_down_1_0_1_5": events["m15_shock_down_1_0_1_5"].fillna(False),
        "H3_SHOCK_REVERSAL:m15_shock_up_1_0_1_5": events["m15_shock_up_1_0_1_5"].fillna(False),
        "H4_LONDON_SWEEP_REVERSAL:london_open_sweep_high": events["london_open_sweep_high"].fillna(False),
        "H4_LONDON_SWEEP_REVERSAL:london_open_sweep_low": events["london_open_sweep_low"].fillna(False),
    }
    return f, branches


def side_for(branch: str) -> int:
    return -1 if branch.endswith(("mss_up", "ob_candidate_up", "m15_shock_up_1_0_1_5", "london_open_sweep_low")) else 1


def is_friday_cutoff(ts: pd.Timestamp) -> bool:
    return ts.weekday() == 4 and (ts.hour > 16 or (ts.hour == 16 and ts.minute >= 0))


def is_forced_friday_close(ts: pd.Timestamp) -> bool:
    return ts.weekday() == 4 and (ts.hour > 20 or (ts.hour == 20 and ts.minute >= 45))


def next_valid_index(index: pd.DatetimeIndex, i: int) -> int | None:
    if i + 1 >= len(index) or index[i + 1] != index[i] + pd.Timedelta(minutes=15):
        return None
    return i + 1


def execute_single(f: pd.DataFrame, pair: str, hypothesis: str, branch: str, signal: pd.Series) -> list[dict]:
    index = f.index; vals = {k: f[k].to_numpy(float) for k in ("open", "high", "low", "close", "atr15", "volume")}
    rows: list[dict] = []; free_at = -1; armed = True
    for i, fired in enumerate(signal.to_numpy(bool)):
        if not fired:
            armed = True
            continue
        if not armed or i < free_at or index[i] < START or is_friday_cutoff(index[i]):
            continue
        entry_i = next_valid_index(index, i)
        risk = vals["atr15"][i]
        if entry_i is None or not np.isfinite(risk) or risk <= 0 or vals["volume"][entry_i] <= 0:
            continue
        side = side_for(branch); entry = vals["open"][entry_i]; stop = entry - side * risk; target = entry + side * risk
        exit_i = min(entry_i + MAX_BARS - 1, len(index) - 1); exit_px = vals["close"][exit_i]; reason = "TIME"; ambiguous = False
        for j in range(entry_i, min(entry_i + MAX_BARS, len(index))):
            if is_forced_friday_close(index[j]):
                exit_i, exit_px, reason = j, vals["close"][j], "FRIDAY"
                break
            stop_hit = vals["low"][j] <= stop if side == 1 else vals["high"][j] >= stop
            target_hit = vals["high"][j] >= target if side == 1 else vals["low"][j] <= target
            if stop_hit or target_hit:
                exit_i, ambiguous = j, bool(stop_hit and target_hit)
                exit_px, reason = (stop, "SL") if stop_hit else (target, "TP")
                break
        gross_r = side * (exit_px - entry) / risk
        rows.append(dict(hypothesis=hypothesis, branch=branch.split(":", 1)[1], unit=pair, signal_dt=index[i], entry_dt=index[entry_i], exit_dt=index[exit_i], side=side, gross_r=gross_r, cost_r=SINGLE_COST_R, r=gross_r-SINGLE_COST_R, reason=reason, ambiguous_stop_first=ambiguous))
        free_at = exit_i + 1; armed = False
    return rows


def peer_events(h1: dict[str, pd.DataFrame]) -> list[tuple[str, pd.Timestamp, str, str]]:
    out = []
    for a, b in (("EURUSD", "GBPUSD"), ("AUDUSD", "NZDUSD"), ("EURJPY", "GBPJPY")):
        if a not in h1 or b not in h1:
            continue
        x = pd.concat({a: h1[a]["norm"], b: h1[b]["norm"]}, axis=1, join="inner").dropna()
        for t, row in x.iterrows():
            lead, lag = (a, b) if row[a] >= row[b] else (b, a)
            # An H1 source bar becomes usable only after it has completed.
            out.append((f"{a}_{b}", t + pd.Timedelta(hours=1), lead, lag))
    return out


def execute_peer(m15: dict[str, pd.DataFrame], h1: dict[str, pd.DataFrame]) -> list[dict]:
    rows = []; lookup = {p: {t: i for i, t in enumerate(f.index)} for p, f in m15.items()}; free: dict[str, pd.Timestamp] = {}
    for group, signal_dt, lead, lag in peer_events(h1):
        if signal_dt < START or is_friday_cutoff(signal_dt) or (group in free and signal_dt <= free[group]):
            continue
        # The two fixed legs must both have the exact event bar and next M15 open; no substitution.
        if signal_dt not in lookup[lead] or signal_dt not in lookup[lag]:
            continue
        il, ig = lookup[lead][signal_dt], lookup[lag][signal_dt]
        el, eg = next_valid_index(m15[lead].index, il), next_valid_index(m15[lag].index, ig)
        if el is None or eg is None or m15[lead].index[el] != m15[lag].index[eg]:
            continue
        al, ag = float(m15[lead].atr15.iloc[il]), float(m15[lag].atr15.iloc[ig])
        if not (np.isfinite(al) and np.isfinite(ag) and al > 0 and ag > 0):
            continue
        entry_dt = m15[lead].index[el]; ep_l, ep_g = float(m15[lead].open.iloc[el]), float(m15[lag].open.iloc[eg])
        end = min(el + MAX_BARS - 1, len(m15[lead]) - 1, eg + MAX_BARS - 1, len(m15[lag]) - 1); exit_i = end; reason = "TIME"; ambiguous = False; gross_r = None
        for offset in range(MAX_BARS):
            jl, jg = el + offset, eg + offset
            if jl >= len(m15[lead]) or jg >= len(m15[lag]) or m15[lead].index[jl] != m15[lag].index[jg]: break
            t = m15[lead].index[jl]
            if is_forced_friday_close(t):
                exit_i, reason = jl, "FRIDAY"; end = jg; break
            # Equal ATR-risk legs: short leader, long laggard.  Pair threshold is average R.
            worst = ((ep_l - float(m15[lead].high.iloc[jl])) / al + (float(m15[lag].low.iloc[jg]) - ep_g) / ag) / 2
            best = ((ep_l - float(m15[lead].low.iloc[jl])) / al + (float(m15[lag].high.iloc[jg]) - ep_g) / ag) / 2
            if worst <= -1 or best >= 1:
                gross_r, reason, ambiguous, exit_i, end = (-1.0, "SL", worst <= -1 and best >= 1, jl, jg) if worst <= -1 else (1.0, "TP", False, jl, jg)
                break
        if gross_r is None:
            gross_r = ((ep_l - float(m15[lead].close.iloc[exit_i])) / al + (float(m15[lag].close.iloc[end]) - ep_g) / ag) / 2
        exit_dt = m15[lead].index[exit_i]
        rows.append(dict(hypothesis="H5_PEER_CONVERGENCE", branch="convergence", unit=group, signal_dt=signal_dt, entry_dt=entry_dt, exit_dt=exit_dt, side=0, gross_r=gross_r, cost_r=PEER_COST_R, r=gross_r-PEER_COST_R, reason=reason, ambiguous_stop_first=ambiguous))
        free[group] = exit_dt
    return rows


def metrics(t: pd.DataFrame) -> dict:
    if t.empty: return dict(trade_count=0, expectancy_r=np.nan, profit_factor=np.nan, win_rate=np.nan, average_win_r=np.nan, average_loss_r=np.nan, max_drawdown_r=np.nan, total_r=0.0, annual_trade_frequency=0.0, monthly_trade_frequency=0.0)
    r = t.sort_values("exit_dt").r.to_numpy(float); wins, losses = r[r > 0], r[r < 0]; equity = np.cumsum(r); dd = np.maximum.accumulate(equity) - equity
    return dict(trade_count=len(r), expectancy_r=float(r.mean()), profit_factor=float(wins.sum() / -losses.sum()) if len(losses) else np.inf, win_rate=float(len(wins)/len(r)), average_win_r=float(wins.mean()) if len(wins) else np.nan, average_loss_r=float(losses.mean()) if len(losses) else np.nan, max_drawdown_r=float(dd.max()), total_r=float(r.sum()), annual_trade_frequency=float(len(r)/3), monthly_trade_frequency=float(len(r)/36))


def gate(t: pd.DataFrame, hypothesis: str) -> tuple[str, str]:
    m = metrics(t); years = t.assign(year=pd.to_datetime(t.entry_dt, utc=True).dt.year).groupby("year").r.agg(["sum", "mean"]) if len(t) else pd.DataFrame()
    positive_years = int((years["mean"] > 0).sum()) if len(years) else 0; positive_total = years.loc[years["sum"] > 0, "sum"].sum() if len(years) else 0
    no_year_dependence = positive_years >= 2 and (positive_total <= 0 or years["sum"].max() <= .70 * positive_total)
    units = t.groupby("unit").r.mean() if len(t) else pd.Series(dtype=float)
    breadth = int((units > 0).sum()) >= (2 if hypothesis == "H5_PEER_CONVERGENCE" else 8)
    ok = m["trade_count"] >= 120 and m["expectancy_r"] > 0 and m["profit_factor"] > 1 and no_year_dependence and breadth and m["max_drawdown_r"] <= 20 and np.isfinite(m["average_win_r"]) and np.isfinite(m["average_loss_r"])
    return ("SURVIVED" if ok else "REJECTED", "all frozen criteria passed" if ok else "one or more frozen gate criteria failed")


def write_outputs(trades: pd.DataFrame, out: Path) -> pd.DataFrame:
    out.mkdir(parents=True, exist_ok=True)
    summary = []
    for h in HYPOTHESES:
        x = trades[trades.hypothesis.eq(h)].copy(); status, detail = gate(x, h); summary.append(dict(hypothesis=h, classification=status, gate_detail=detail, **metrics(x)))
    s = pd.DataFrame(summary); s.to_csv(out / "summary.csv", index=False)
    def grouped(cols: list[str]) -> pd.DataFrame:
        rows=[]
        for key, x in trades.groupby(cols, dropna=False):
            key = key if isinstance(key, tuple) else (key,); rows.append(dict(zip(cols,key), **metrics(x)))
        return pd.DataFrame(rows)
    grouped(["hypothesis", "entry_year"] if "entry_year" in trades else ["hypothesis"]).to_csv(out / "by_year.csv", index=False)
    grouped(["hypothesis", "unit", "branch"]).to_csv(out / "by_pair.csv", index=False)
    return s


def main() -> None:
    ap=argparse.ArgumentParser(); ap.add_argument("--data",default=str(ROOT/"data_independent/derived_m15")); ap.add_argument("--out",default=str(ROOT/"results_next_strategy/round3c")); args=ap.parse_args()
    root, all_rows = Path(args.data), []
    peer_pairs = {"EURUSD", "GBPUSD", "AUDUSD", "NZDUSD", "EURJPY", "GBPJPY"}
    m15: dict[str,pd.DataFrame] = {}; h1: dict[str,pd.DataFrame] = {}
    for pair in PAIRS:
        raw, hour = load_pair(root, pair); f, branches = selected_events(raw); m15[pair] = f; h = r3a.h1_state(hour.copy()); h["norm"] = h.h1_norm_return; h1[pair] = h
        for branch, signal in branches.items():
            hyp = branch.split(":",1)[0]; all_rows.extend(execute_single(f,pair,hyp,branch,signal))
        if pair not in peer_pairs:
            del m15[pair], h1[pair]
        else:
            m15[pair] = f[["open","high","low","close","volume","atr15"]].copy()
            h1[pair] = h[["norm"]].copy()
        gc.collect()
    all_rows.extend(execute_peer(m15,h1)); trades=pd.DataFrame(all_rows)
    if trades.empty: trades=pd.DataFrame(columns=["hypothesis","branch","unit","signal_dt","entry_dt","exit_dt","side","gross_r","cost_r","r","reason","ambiguous_stop_first"])
    for c in ("signal_dt","entry_dt","exit_dt"): trades[c]=pd.to_datetime(trades[c],utc=True)
    trades["entry_year"] = trades.entry_dt.dt.year
    out=Path(args.out); out.mkdir(parents=True,exist_ok=True); trades.to_csv(out/"trades.csv",index=False)
    summary=write_outputs(trades,out); print(summary[["hypothesis","classification","trade_count","expectancy_r","profit_factor","max_drawdown_r","total_r"]].to_string(index=False))

if __name__ == "__main__": main()
