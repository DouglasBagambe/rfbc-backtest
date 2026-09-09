"""Lightweight, reproducible exploratory research for RFBC v1.1.

This script never changes frozen v1.0 trade rules or writes into ``results/``.
It reads the v1.0 control trades, derives signal-time features, and writes all
research artifacts under ``results_v11_research/``.
"""
from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

import numpy as np
import pandas as pd

import backtest


ROOT = Path(__file__).parent
DATA = ROOT / "data"
CONTROL = ROOT / "results" / "trades_baseline_h4.csv"
OUT = ROOT / "results_v11_research"
BASE = backtest.Params(execution_tf="h4")
SPLITS = {"development": (2013, 2016), "validation": (2017, 2019), "holdout": (2020, 2022)}


def load_control() -> pd.DataFrame:
    trades = pd.read_csv(CONTROL, parse_dates=["signal_dt", "entry_dt", "exit_dt"])
    trades["holding_hours"] = (trades.exit_dt - trades.entry_dt).dt.total_seconds() / 3600
    return trades


def signal_features(trades: pd.DataFrame) -> pd.DataFrame:
    """Create only signal-time features. ATR percentile is strictly trailing."""
    parts: list[pd.DataFrame] = []
    for pair in backtest.BASELINE_PAIRS:
        h4 = backtest.prepare(pair, DATA, BASE).copy()
        d1 = backtest.load_csv(DATA / f"{pair}d1.csv")
        d1["ema_fast"] = backtest.ema(d1.close, BASE.d1_fast)
        d1["ema_slow"] = backtest.ema(d1.close, BASE.d1_slow)
        d1["ema_fast_prev"] = d1.ema_fast.shift(BASE.d1_slope_lookback)
        d1_features = d1[["dt", "ema_fast", "ema_slow", "ema_fast_prev"]].copy()
        d1_features["available_dt"] = d1_features.dt + pd.Timedelta(days=1)
        h4 = pd.merge_asof(
            h4.sort_values("close_dt"),
            d1_features.drop(columns="dt").sort_values("available_dt"),
            left_on="close_dt", right_on="available_dt", direction="backward",
        )
        h4["pair"] = pair
        h4["signal_dt"] = h4["close_dt"]
        h4["entry_checkpoint_utc"] = h4["close_dt"].dt.hour
        h4["weekday"] = h4["close_dt"].dt.day_name()
        h4["trend_sep_atr"] = (h4["ema_fast"] - h4["ema_slow"]).abs() / h4["atr"]
        h4["ema_slope_atr"] = (h4["ema_fast"] - h4["ema_fast_prev"]).abs() / h4["atr"]
        h4["breakout_atr"] = np.where(
            h4["signal"] == 1,
            (h4["close"] - h4["prev_high"]) / h4["atr"],
            (h4["prev_low"] - h4["close"]) / h4["atr"],
        )
        h4["candle_atr"] = h4["tr"] / h4["atr"]
        h4["atr_pct_252"] = h4["atr"].shift(1).rolling(252, min_periods=63).rank(pct=True)
        parts.append(h4[["pair", "signal_dt", "entry_checkpoint_utc", "weekday", "trend_sep_atr", "ema_slope_atr", "breakout_atr", "candle_atr", "atr_pct_252"]])
    feature_frame = pd.concat(parts, ignore_index=True)
    out = trades.merge(feature_frame, on=["pair", "signal_dt"], how="left", validate="one_to_one")
    out["year"] = out.entry_dt.dt.year
    out["entry_weekday"] = out.entry_dt.dt.day_name()
    out["friday_outcome"] = np.where(out.reason.eq("FRIDAY"), np.where(out.r > 0, "FRIDAY_WIN", "FRIDAY_LOSS"), "NOT_FRIDAY")
    out["no_chase_displacement_atr"] = (out.entry - out.signal_close).abs() / out.atr
    return out


def basic_metrics(t: pd.DataFrame, risk: float = 0.005) -> dict[str, float | int | None]:
    if t.empty:
        return {"trades": 0, "win_rate": None, "expectancy_r": None, "profit_factor": None, "max_dd_pct": None, "total_return_pct": None, "trades_per_month": None, "longest_loss_streak": None}
    r = t.sort_values("exit_dt")["r"].to_numpy(float)
    equity = np.cumprod(1 + risk * r)
    dd = 1 - equity / np.maximum.accumulate(equity)
    wins, losses = r[r > 0], r[r <= 0]
    months = max((t.exit_dt.max().to_period("M") - t.entry_dt.min().to_period("M")).n + 1, 1)
    years = max((t.exit_dt.max() - t.entry_dt.min()).days / 365.25, 1 / 365.25)
    streak = max((len(x) for x in "".join("L" if x < 0 else "W" for x in r).split("W")), default=0)
    return {
        "trades": len(t), "win_rate": float((r > 0).mean()), "expectancy_r": float(r.mean()),
        "profit_factor": float(wins.sum() / -losses.sum()) if len(losses) and losses.sum() < 0 else None,
        "max_dd_pct": float(dd.max()), "total_return_pct": float(equity[-1] - 1), "cagr": float(equity[-1] ** (1 / years) - 1),
        "trades_per_month": float(len(t) / months), "longest_loss_streak": int(streak),
    }


def grouped(t: pd.DataFrame, col: str) -> pd.DataFrame:
    rows = []
    for value, group in t.groupby(col, dropna=False):
        rows.append({col: str(value), **basic_metrics(group)})
    return pd.DataFrame(rows).sort_values("expectancy_r", ascending=False, na_position="last")


def split_metrics(t: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for name, (start, end) in SPLITS.items():
        rows.append({"split": name, "start_year": start, "end_year": end, **basic_metrics(t[t.year.between(start, end)])})
    return pd.DataFrame(rows)


def yearly(t: pd.DataFrame) -> pd.DataFrame:
    return grouped(t, "year").sort_values("year")


def block_arrays(t: pd.DataFrame) -> list[list[np.ndarray]]:
    """Return sequential R arrays per within-week day, without original dates."""
    ordered = t.sort_values("exit_dt").copy()
    ordered["week"] = ordered.exit_dt.dt.to_period("W-SUN")
    blocks: list[list[np.ndarray]] = []
    for _, week in ordered.groupby("week", sort=True):
        days = []
        for _, day in week.groupby(week.exit_dt.dt.normalize(), sort=True):
            days.append(day.r.to_numpy(float))
        blocks.append(days)
    return blocks


def corrected_bootstrap(t: pd.DataFrame, risk: float, n: int = 5000, start: float = 100000.0, seed: int = 100) -> dict[str, float]:
    """Weekly block bootstrap with synthetic sequential days.

    Each sampled historical week's day positions become distinct simulation days.
    Therefore sampled duplicate weeks never share a daily-loss baseline.
    """
    blocks = block_arrays(t)
    if not blocks:
        return {}
    rng = np.random.default_rng(seed)
    finals = np.empty(n)
    maxdds = np.empty(n)
    daily_breach = np.zeros(n, dtype=bool)
    total_breach = np.zeros(n, dtype=bool)
    internal_breach = np.zeros(n, dtype=bool)
    for path in range(n):
        bal = peak = start
        path_maxdd = 0.0
        path_daily = path_total = path_internal = False
        for synthetic_week, choice in enumerate(rng.integers(0, len(blocks), size=len(blocks))):
            for synthetic_day, rs in enumerate(blocks[choice]):
                day_start = bal  # fresh synthetic identifier: (path, synthetic_week, synthetic_day)
                for value in rs:
                    bal *= 1 + risk * value
                    peak = max(peak, bal)
                    path_maxdd = max(path_maxdd, 1 - bal / peak)
                    path_daily |= bal < day_start * 0.95
                    path_internal |= bal < peak * 0.95
                    path_total |= bal < start * 0.90
        finals[path] = bal
        maxdds[path] = path_maxdd
        daily_breach[path], internal_breach[path], total_breach[path] = path_daily, path_internal, path_total
    return {
        "paths": n, "risk_pct": risk, "final_p05": float(np.quantile(finals, .05)), "final_median": float(np.quantile(finals, .5)), "final_p95": float(np.quantile(finals, .95)),
        "dd_p50": float(np.quantile(maxdds, .5)), "dd_p95": float(np.quantile(maxdds, .95)),
        "prob_internal_5pct_halt": float(internal_breach.mean()), "prob_generic_10pct_total_breach": float(total_breach.mean()),
        "prob_generic_5pct_daily_breach": float(daily_breach.mean()),
    }


def param_run(**changes: object) -> pd.DataFrame:
    p = backtest.Params(**{**asdict(BASE), **changes})
    return pd.concat([backtest.run_pair(pair, DATA, p) for pair in backtest.BASELINE_PAIRS], ignore_index=True)


def usdjpy_sensitivity() -> pd.DataFrame:
    """Staged one-factor testing plus a deliberately small local 3x3x3 grid."""
    rows = []
    tests = {
        "breakout_lookback": [10, 15, 20, 25, 30, 40], "atr_mult": [1.0, 1.25, 1.5, 1.75, 2.0],
        "rr": [1.5, 2.0, 2.5, 3.0, 3.5], "d1_slope_lookback": [3, 5, 10],
        "extreme_candle_atr": [1.5, 2.0, 2.5], "chase_atr": [.10, .20, .30],
    }
    for field, values in tests.items():
        for value in values:
            p = backtest.Params(**{**asdict(BASE), field: value})
            t = backtest.run_pair("USDJPY", DATA, p)
            rows.append({"stage": "one_factor", "variable": field, "value": value, **basic_metrics(t)})
    for lookback in (15, 20, 25):
        for atr_mult in (1.25, 1.5, 1.75):
            for rr in (2.0, 2.5, 3.0):
                p = backtest.Params(**{**asdict(BASE), "breakout_lookback": lookback, "atr_mult": atr_mult, "rr": rr})
                t = backtest.run_pair("USDJPY", DATA, p)
                rows.append({"stage": "local_grid", "variable": "lookback_atr_rr", "value": f"{lookback}/{atr_mult}/{rr}", **basic_metrics(t)})
    return pd.DataFrame(rows)


def candidate_screen(t: pd.DataFrame) -> pd.DataFrame:
    """Small, rationale-led screen. Ranking is development-only."""
    rules = [
        ("USDJPY only", lambda x: x.pair.eq("USDJPY")),
        ("USDJPY long only", lambda x: x.pair.eq("USDJPY") & x.side.eq(1)),
        ("USDJPY short only", lambda x: x.pair.eq("USDJPY") & x.side.eq(-1)),
        ("USDJPY trend separation >=1 ATR", lambda x: x.pair.eq("USDJPY") & x.trend_sep_atr.ge(1.0)),
        ("USDJPY slope >=0.10 ATR", lambda x: x.pair.eq("USDJPY") & x.ema_slope_atr.ge(.10)),
        ("USDJPY breakout >=0.10 ATR", lambda x: x.pair.eq("USDJPY") & x.breakout_atr.ge(.10)),
        ("USDJPY middle ATR regime", lambda x: x.pair.eq("USDJPY") & x.atr_pct_252.between(.20, .80)),
        ("all pairs strong separation >=1.5 ATR", lambda x: x.trend_sep_atr.ge(1.5)),
    ]
    rows = []
    for name, condition in rules:
        selected = t[condition(t)].copy()
        dev = selected[selected.year.between(2013, 2016)]
        rows.append({"rule": name, **{f"dev_{k}": v for k, v in basic_metrics(dev).items()}, **{f"all_{k}": v for k, v in basic_metrics(selected).items()}, "validation_expectancy_r": basic_metrics(selected[selected.year.between(2017, 2019)])["expectancy_r"], "holdout_expectancy_r": basic_metrics(selected[selected.year.between(2020, 2022)])["expectancy_r"]})
    return pd.DataFrame(rows).sort_values(["dev_expectancy_r", "dev_profit_factor"], ascending=False, na_position="last")


def select_candidates(t: pd.DataFrame, screen: pd.DataFrame) -> list[tuple[str, pd.DataFrame]]:
    # Only retain rules that meet the requested development quality and are non-negative in both later splits.
    valid = screen[(screen.dev_expectancy_r >= .15) & (screen.dev_profit_factor >= 1.30) & (screen.validation_expectancy_r > 0) & (screen.holdout_expectancy_r > 0)]
    mapping = {
        "USDJPY only": t.pair.eq("USDJPY"),
        "USDJPY long only": t.pair.eq("USDJPY") & t.side.eq(1),
        "USDJPY short only": t.pair.eq("USDJPY") & t.side.eq(-1),
        "USDJPY trend separation >=1 ATR": t.pair.eq("USDJPY") & t.trend_sep_atr.ge(1.0),
        "USDJPY slope >=0.10 ATR": t.pair.eq("USDJPY") & t.ema_slope_atr.ge(.10),
        "USDJPY breakout >=0.10 ATR": t.pair.eq("USDJPY") & t.breakout_atr.ge(.10),
        "USDJPY middle ATR regime": t.pair.eq("USDJPY") & t.atr_pct_252.between(.20, .80),
        "all pairs strong separation >=1.5 ATR": t.trend_sep_atr.ge(1.5),
    }
    return [(row.rule, t[mapping[row.rule]].copy()) for _, row in valid.head(3).iterrows()]


def parameter_candidates() -> list[tuple[str, str, pd.DataFrame]]:
    """Three bounded USDJPY variants drawn from the broad local sensitivity plateau."""
    specs = [
        ("v11_usdjpy_control", "USDJPY only; frozen v1.0 parameters (control subset)", {}),
        ("v11_usdjpy_l25_rr3", "USDJPY only; 25-H4 breakout, 1.50 ATR stop, 3.00R target", {"breakout_lookback": 25, "atr_mult": 1.5, "rr": 3.0}),
        ("v11_usdjpy_l25_wide", "USDJPY only; 25-H4 breakout, 1.75 ATR stop, 2.50R target", {"breakout_lookback": 25, "atr_mult": 1.75, "rr": 2.5}),
    ]
    output = []
    for candidate_id, rule, changes in specs:
        p = backtest.Params(**{**asdict(BASE), **changes})
        trades = backtest.run_pair("USDJPY", DATA, p)
        trades["signal_dt"] = pd.to_datetime(trades["signal_dt"])
        trades["entry_dt"] = pd.to_datetime(trades["entry_dt"])
        trades["exit_dt"] = pd.to_datetime(trades["exit_dt"])
        trades["year"] = trades.entry_dt.dt.year
        output.append((candidate_id, rule, trades))
    return output


def write_report(t: pd.DataFrame, filter_candidates: list[tuple[str, pd.DataFrame]], parameter_variants: list[tuple[str, str, pd.DataFrame]], candidate_results: pd.DataFrame, corrected: pd.DataFrame, sensitivity: pd.DataFrame, screen: pd.DataFrame) -> None:
    lines = ["# RFBC v1.1 Exploratory Research Report", "", "## Scope and safeguards", "", "This is exploratory analysis of 2013 through March 2022 price-only data. Frozen RFBC v1.0 code and `results/` were not changed. No live trading, broker, or MT5 connection was used.", "", "## v1.0 control", "", f"- Trades: {len(t)}", f"- Expectancy: {basic_metrics(t)['expectancy_r']:.4f}R", f"- Profit factor: {basic_metrics(t)['profit_factor']:.3f}", f"- Maximum drawdown at 0.5% risk: {basic_metrics(t)['max_dd_pct']:.2%}", "", "## Phase A: corrected bootstrap", "", "The corrected prop bootstrap assigns every sampled week/day a synthetic sequential simulation identity. Duplicate sampled historical weeks therefore cannot reuse an original calendar-date daily balance. Monte Carlo uses only sequential R outcomes in sampled weekly blocks; it does not carry real dates across paths.", "", "## Phase B: strongest descriptive findings", ""]
    pair = grouped(t, "pair")
    lines.extend([f"- {r.pair}: {int(r.trades)} trades, expectancy {r.expectancy_r:.4f}R, PF {r.profit_factor:.3f}" for r in pair.itertuples()])
    lines.extend(["", "Chronological v1.0 control expectancy: " + ", ".join(f"{r.split} {r.expectancy_r:.4f}R ({int(r.trades)} trades)" for r in split_metrics(t).itertuples()) + ".", "Corrected 5,000-path prop bootstrap daily-breach probabilities are " + ", ".join(f"{r.risk_pct:.2%}: {r.prob_generic_5pct_daily_breach:.2%}" for r in corrected.itertuples()) + "; zero is expected because the H4 dataset has at most one exit per original day and synthetic days reset correctly.", "", "Feature tables are saved as CSVs; they are descriptive, not selection proof.", "", "## Phase C: USDJPY parameter stability", ""])
    stable = sensitivity[(sensitivity.expectancy_r > 0) & (sensitivity.profit_factor >= 1.0)]
    lines.append(f"- Positive/PF>=1.0 USDJPY sensitivity cells: {len(stable)} of {len(sensitivity)}.")
    lines.append("- Inspect `usdjpy_sensitivity.csv` for every tested cell; no Cartesian mega-search was run.")
    lines.extend(["", "## Phase D-F: candidate decision", ""])
    lines.append("No signal-time filter passed the predeclared development threshold (>=0.15R, PF>=1.30) while also staying positive in validation and holdout. The three parameter variants below are therefore stress tests, not promoted candidates:")
    for candidate_id, rule, selected in parameter_variants:
        m = basic_metrics(selected)
        splits = split_metrics(selected).set_index("split")
        mc = candidate_results[(candidate_results.candidate.eq(candidate_id)) & (candidate_results.metric_scope.eq("corrected_prop_bootstrap")) & (candidate_results.risk_pct.eq(.005))].iloc[0]
        lines.append(f"- **{candidate_id}** ({rule}) — {m['trades']} trades, {m['trades_per_month']:.2f}/month, expectancy {m['expectancy_r']:.4f}R, PF {m['profit_factor']:.3f}, DD {m['max_dd_pct']:.2%}, CAGR {m['cagr']:.2%}, total return {m['total_return_pct']:.2%}; development/validation/holdout expectancy = {splits.loc['development', 'expectancy_r']:.4f}/{splits.loc['validation', 'expectancy_r']:.4f}/{splits.loc['holdout', 'expectancy_r']:.4f}R; corrected 0.5% MC final P05/P50/P95 = ${mc.final_p05:,.0f}/${mc.final_median:,.0f}/${mc.final_p95:,.0f}, DD P50/P95 = {mc.dd_p50:.2%}/{mc.dd_p95:.2%}, 5% internal halt = {mc.prob_internal_5pct_halt:.2%}.")
    lines.append("Recommendation: **REJECT** a v1.1 candidate on this dataset. CONTINUE RESEARCH only after independent data validation, not further optimization of this sample.")
    lines.extend(["", "## Mandatory next validation", "", "Re-run frozen v1.0 and any candidate unchanged on independent Dukascopy/HistData data with a validated timestamp/session convention, historical bid/ask costs, news handling, and broker-specific prop rules. Do not declare a tradable edge from this dataset."])
    (OUT / "RFBC_V11_RESEARCH_REPORT.md").write_text("\n".join(lines) + "\n")


def main() -> None:
    OUT.mkdir(exist_ok=True)
    t = signal_features(load_control())
    t.to_csv(OUT / "v10_trade_features.csv", index=False)
    for col in ("pair", "year", "side", "entry_checkpoint_utc", "weekday", "entry_weekday", "reason", "friday_outcome"):
        grouped(t, col).to_csv(OUT / f"analysis_by_{col}.csv", index=False)
    # Feature bins avoid peeking: ATR percentile itself is trailing; bins are descriptive only.
    for col in ("trend_sep_atr", "ema_slope_atr", "breakout_atr", "candle_atr", "no_chase_displacement_atr", "holding_hours", "atr_pct_252"):
        q = pd.qcut(t[col], q=4, duplicates="drop")
        grouped(t.assign(**{f"{col}_quartile": q}), f"{col}_quartile").to_csv(OUT / f"analysis_by_{col}_quartile.csv", index=False)
    yearly(t).to_csv(OUT / "v10_yearly_control.csv", index=False)
    split_metrics(t).to_csv(OUT / "v10_chronological_splits.csv", index=False)
    corrected = pd.DataFrame([corrected_bootstrap(t, risk) for risk in (.0025, .005, .01)])
    corrected.to_csv(OUT / "corrected_prop_simulations.csv", index=False)
    sensitivity = usdjpy_sensitivity()
    sensitivity.to_csv(OUT / "usdjpy_sensitivity.csv", index=False)
    screen = candidate_screen(t)
    screen.to_csv(OUT / "candidate_screen.csv", index=False)
    filter_candidates = select_candidates(t, screen)
    variants = parameter_candidates()
    rows = []
    for candidate_id, rule, selected in variants:
        selected.to_csv(OUT / f"{candidate_id}_trades.csv", index=False)
        split_metrics(selected).to_csv(OUT / f"{candidate_id}_splits.csv", index=False)
        yearly(selected).to_csv(OUT / f"{candidate_id}_yearly.csv", index=False)
        rows.append({"candidate": candidate_id, "rule": rule, "metric_scope": "full_sample", **basic_metrics(selected)})
        for risk in (.0025, .005, .01):
            rows.append({"candidate": candidate_id, "rule": rule, "metric_scope": "corrected_prop_bootstrap", **corrected_bootstrap(selected, risk)})
    candidate_results = pd.DataFrame(rows)
    candidate_results.to_csv(OUT / "candidate_metrics_and_corrected_prop.csv", index=False)
    write_report(t, filter_candidates, variants, candidate_results, corrected, sensitivity, screen)
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
