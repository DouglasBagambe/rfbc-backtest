#!/usr/bin/env python3
"""External Dukascopy BID/ASK replication of frozen RFBC v1.0 on non-USDJPY pairs.

This intentionally tests only the frozen v1.0 rule set (20-H4 breakout, 1.50 ATR stop,
2.50R target) on EURUSD, GBPUSD and AUDUSD. It does not optimize or retune anything.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import backtest

PERIODS = {
    "overlap_2013_to_2022_03_03": ("2013-01-01", "2022-03-03"),
    "unseen_2022_03_04_to_2026_09_01": ("2022-03-04", "2026-09-01"),
    "full_independent": ("2013-01-01", "2026-09-01"),
}


def read_pair(pair: str, side: str, tf: str, root: Path) -> pd.DataFrame:
    p = root / pair / f"{pair}_{side}_{tf}.csv"
    return pd.read_csv(p, parse_dates=["dt"])


def prepare(pair: str, root: Path):
    d1 = read_pair(pair, "bid", "d1", root)
    h4_bid = read_pair(pair, "bid", "h4", root)
    h4_ask = read_pair(pair, "ask", "h4", root)
    h1_bid = read_pair(pair, "bid", "h1", root)
    h1_ask = read_pair(pair, "ask", "h1", root)

    d1["ema_fast"] = backtest.ema(d1.close, 50)
    d1["ema_slow"] = backtest.ema(d1.close, 200)
    d1["ema_fast_prev"] = d1.ema_fast.shift(5)
    d1["regime"] = 0
    d1.loc[(d1.close > d1.ema_fast) & (d1.ema_fast > d1.ema_slow) & (d1.ema_fast > d1.ema_fast_prev), "regime"] = 1
    d1.loc[(d1.close < d1.ema_fast) & (d1.ema_fast < d1.ema_slow) & (d1.ema_fast < d1.ema_fast_prev), "regime"] = -1

    h4_bid["atr"] = backtest.atr(h4_bid, 14)
    prev = h4_bid.close.shift(1)
    h4_bid["tr"] = pd.concat([
        (h4_bid.high - h4_bid.low).abs(),
        (h4_bid.high - prev).abs(),
        (h4_bid.low - prev).abs(),
    ], axis=1).max(axis=1)
    h4_bid["prev_high"] = h4_bid.high.shift(1).rolling(20).max()
    h4_bid["prev_low"] = h4_bid.low.shift(1).rolling(20).min()
    h4_bid["close_dt"] = h4_bid.dt + pd.Timedelta(hours=4)

    dm = d1[["dt", "regime"]].copy()
    dm["available_dt"] = dm.dt + pd.Timedelta(days=1)
    h4_bid = pd.merge_asof(
        h4_bid.sort_values("close_dt"),
        dm[["available_dt", "regime"]].sort_values("available_dt"),
        left_on="close_dt", right_on="available_dt", direction="backward",
    )

    actionable = h4_bid.close_dt.map(
        lambda ts: (ts.weekday() <= 3 and ts.hour in (8, 12, 16)) or (ts.weekday() == 4 and ts.hour in (8, 12))
    )
    h4_bid["signal"] = 0
    common = actionable & np.isfinite(h4_bid.atr) & (h4_bid.atr > 0) & (h4_bid.tr <= 2.0 * h4_bid.atr)
    h4_bid.loc[common & h4_bid.regime.eq(1) & (h4_bid.close > h4_bid.prev_high), "signal"] = 1
    h4_bid.loc[common & h4_bid.regime.eq(-1) & (h4_bid.close < h4_bid.prev_low), "signal"] = -1

    h1 = h1_bid.merge(h1_ask, on="dt", suffixes=("_bid", "_ask"), validate="one_to_one").set_index("dt")
    return h4_bid.reset_index(drop=True), h4_ask.reset_index(drop=True), h1


def run_pair(pair: str, root: Path):
    h4, ask4, h1 = prepare(pair, root)
    trades = []
    next_allowed = pd.Timestamp.min.tz_localize("UTC")
    ambiguous = 0
    unclosed = 0
    h4_closes = dict(zip(h4.close_dt, h4.close))

    for i in np.flatnonzero(h4.signal.to_numpy()):
        signal = h4.iloc[i]
        signal_dt = signal.close_dt
        if i + 1 >= len(h4) or signal_dt <= next_allowed:
            continue
        side = int(signal.signal)
        entry = float(ask4.open.iat[i + 1] if side == 1 else h4.open.iat[i + 1])
        adverse = side * (entry - float(signal.close))
        if adverse > 0.20 * float(signal.atr):
            continue

        risk = 1.50 * float(signal.atr)
        stop = entry - side * risk
        target = entry + side * 2.50 * risk
        be_stop = entry
        armed = False
        exit_px = exit_dt = reason = None
        entry_dt = h4.dt.iat[i + 1]

        for dt, b in h1.loc[entry_dt:].iterrows():
            if dt.weekday() == 4 and dt.hour >= 16:
                exit_px = float(b.open_bid if side == 1 else b.open_ask)
                exit_dt = dt
                reason = "FRIDAY"
                break

            low = float(b.low_bid if side == 1 else b.low_ask)
            high = float(b.high_bid if side == 1 else b.high_ask)
            active = be_stop if armed else stop
            stop_hit = low <= active if side == 1 else high >= active
            target_hit = high >= target if side == 1 else low <= target
            if stop_hit and target_hit:
                ambiguous += 1
            if stop_hit or target_hit:
                exit_px = active if stop_hit else target
                exit_dt = dt
                reason = "BE" if (stop_hit and armed) else "SL" if stop_hit else "TP"
                break

            boundary = dt + pd.Timedelta(hours=1)
            if boundary in h4_closes and side * (h4_closes[boundary] - entry) / risk >= 1.50:
                armed = True

        if exit_px is None:
            unclosed += 1
            continue

        r = side * (float(exit_px) - entry) / risk
        trades.append({
            "pair": pair, "signal_dt": signal_dt, "entry_dt": entry_dt, "exit_dt": exit_dt,
            "side": side, "entry": entry, "stop": stop, "target": target, "exit": exit_px,
            "reason": reason, "r": r,
        })
        next_allowed = exit_dt

    return pd.DataFrame(trades), ambiguous, unclosed


def metrics(t: pd.DataFrame, risk_pct: float = 0.005):
    if t.empty:
        return {"trades": 0}
    t = t.sort_values("exit_dt")
    r = t.r.to_numpy(float)
    equity = np.cumprod(1 + risk_pct * r)
    peak = np.maximum.accumulate(equity)
    dd = 1 - equity / peak
    wins, losses = r[r > 0], r[r <= 0]
    first_m = t.entry_dt.min().tz_localize(None).to_period("M")
    last_m = t.exit_dt.max().tz_localize(None).to_period("M")
    months = max((last_m - first_m).n + 1, 1)
    years = max((t.exit_dt.max() - t.entry_dt.min()).days / 365.25, 1 / 365.25)
    streak = max(map(len, "".join("L" if x < 0 else "W" for x in r).split("W")))
    return {
        "trades": len(t),
        "trades_per_month": len(t) / months,
        "wins": len(wins),
        "losses": len(losses),
        "win_rate": float((r > 0).mean()),
        "expectancy_r": float(r.mean()),
        "profit_factor": float(wins.sum() / -losses.sum()) if len(losses) else np.nan,
        "avg_win_r": float(wins.mean()) if len(wins) else np.nan,
        "avg_loss_r": float(losses.mean()) if len(losses) else np.nan,
        "max_dd_pct": float(dd.max()),
        "total_return_pct": float(equity[-1] - 1),
        "cagr": float(equity[-1] ** (1 / years) - 1),
        "longest_loss_streak": streak,
    }


def monte_carlo(t: pd.DataFrame, n: int = 5000, risk_pct: float = 0.005, seed: int = 42):
    if t.empty:
        return {}
    x = t.sort_values("exit_dt").copy()
    x["week"] = x.exit_dt.dt.tz_localize(None).dt.to_period("W-SUN")
    blocks = [g.r.to_numpy(float) for _, g in x.groupby("week")]
    padded = np.zeros((len(blocks), max(map(len, blocks))), dtype=float)
    for i, b in enumerate(blocks):
        padded[i, :len(b)] = b
    rng = np.random.default_rng(seed)
    picks = rng.integers(0, len(blocks), size=(n, len(blocks)))
    r = padded[picks].reshape(n, -1)
    eq = np.cumprod(1 + risk_pct * r, axis=1)
    dd = 1 - eq / np.maximum.accumulate(eq, axis=1)
    finals = eq[:, -1]
    maxdd = dd.max(axis=1)
    return {
        "final_p05": float(np.quantile(finals, .05)),
        "final_p50": float(np.quantile(finals, .50)),
        "final_p95": float(np.quantile(finals, .95)),
        "dd_p50": float(np.quantile(maxdd, .50)),
        "dd_p95": float(np.quantile(maxdd, .95)),
        "prob_dd_gt_5pct": float((maxdd > .05).mean()),
        "prob_dd_gt_10pct": float((maxdd > .10).mean()),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pairs", nargs="+", default=["EURUSD", "GBPUSD", "AUDUSD"])
    ap.add_argument("--data", default="data_independent/derived")
    ap.add_argument("--out", default="results_external_other_pairs")
    args = ap.parse_args()
    root = Path(args.data)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    rows = []
    mc_rows = []
    decisions = {}
    for pair in args.pairs:
        trades, ambiguous, unclosed = run_pair(pair, root)
        trades.to_csv(out / f"trades_{pair}.csv", index=False)
        pair_rows = []
        for period, (start, end) in PERIODS.items():
            s = trades[trades.entry_dt.dt.normalize().between(pd.Timestamp(start, tz="UTC"), pd.Timestamp(end, tz="UTC"))]
            row = {"pair": pair, "period": period, "ambiguous_h1_stop_first_events": ambiguous,
                   "unclosed_at_data_end": unclosed, **metrics(s)}
            rows.append(row)
            pair_rows.append(row)
        mc_rows.append({"pair": pair, **monte_carlo(trades)})
        full = next(r for r in pair_rows if r["period"] == "full_independent")
        unseen = next(r for r in pair_rows if r["period"] == "unseen_2022_03_04_to_2026_09_01")
        survives = (
            full.get("expectancy_r", -99) >= 0.15 and
            full.get("profit_factor", 0) >= 1.30 and
            unseen.get("expectancy_r", -99) > 0
        )
        decisions[pair] = "SURVIVED" if survives else "REJECTED"

        yearly = pd.DataFrame([{"year": y, **metrics(g)} for y, g in trades.assign(year=trades.entry_dt.dt.year).groupby("year")])
        yearly.to_csv(out / f"yearly_{pair}.csv", index=False)

    metrics_df = pd.DataFrame(rows)
    mc_df = pd.DataFrame(mc_rows)
    metrics_df.to_csv(out / "pair_period_metrics.csv", index=False)
    mc_df.to_csv(out / "monte_carlo.csv", index=False)
    (out / "decisions.json").write_text(json.dumps(decisions, indent=2))

    report = [
        "# External Dukascopy Validation — Remaining RFBC Pairs",
        "",
        "Frozen v1.0 only. No retuning. BID signals, BID/ASK execution, H1 stop/target path, 0.5% risk metrics.",
        "",
        "## Decisions",
        "",
    ]
    report.extend([f"- {p}: **{d}**" for p, d in decisions.items()])
    report += ["", "## Period metrics", "", "```csv", metrics_df.to_csv(index=False).strip(), "```",
               "", "## Monte Carlo", "", "```csv", mc_df.to_csv(index=False).strip(), "```", ""]
    (out / "DUKASCOPY_OTHER_PAIRS_REPORT.md").write_text("\n".join(report))

    print(json.dumps({"decisions": decisions, "metrics": rows, "monte_carlo": mc_rows}, default=str))


if __name__ == "__main__":
    main()
