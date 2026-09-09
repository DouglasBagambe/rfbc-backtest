#!/usr/bin/env python3
"""Read-only summary of a local MT5 USDJPYc spread log."""
from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd


def summary(frame: pd.DataFrame) -> pd.DataFrame:
    return frame["spread_pips"].agg(["count", "median", lambda s: s.quantile(.90), lambda s: s.quantile(.95), "max"]).to_frame().T.rename(columns={"<lambda_0>": "p90", "<lambda_1>": "p95"})


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--log", type=Path, default=Path("broker_validation/local_data/usdjpyc_spread_log.csv"))
    parser.add_argument("--output", type=Path, default=Path("broker_validation/output/usdjpyc_spread_summary.md"))
    parser.add_argument("--rollover-start-hour", type=int, default=21, help="UTC; verify this broker-specific window before relying on it")
    parser.add_argument("--rollover-end-hour", type=int, default=23, help="UTC; inclusive")
    args = parser.parse_args()
    if not args.log.exists():
        raise SystemExit(f"Spread log not found: {args.log}. Copy the MT5 Common/Files log there first.")
    frame = pd.read_csv(args.log, parse_dates=["timestamp_utc"])
    frame["timestamp_utc"] = pd.to_datetime(frame["timestamp_utc"], utc=True)
    frame["spread_pips"] = pd.to_numeric(frame["spread_pips"], errors="coerce")
    frame = frame.dropna(subset=["spread_pips"])
    if frame.empty:
        raise SystemExit("No usable spread observations.")
    by_hour = frame.groupby(frame.timestamp_utc.dt.hour).apply(summary, include_groups=False).reset_index().drop(columns="level_1")
    checkpoints = frame[frame.timestamp_utc.dt.hour.isin([0, 4, 8, 12, 16, 20])]
    friday_16 = frame[(frame.timestamp_utc.dt.weekday == 4) & (frame.timestamp_utc.dt.hour == 16)]
    rollover = frame[frame.timestamp_utc.dt.hour.between(args.rollover_start_hour, args.rollover_end_hour)]
    dukascopy = Path("results_external_dukascopy/spread_by_year.csv")
    comparison = "Dukascopy comparison file unavailable."
    if dukascopy.exists():
        external = pd.read_csv(dukascopy)
        comparison = "Dukascopy H1 opening-spread reference (pips):\n\n```csv\n" + external.to_csv(index=False).strip() + "\n```"
    report = ["# USDJPYc MT5 Spread Validation", "", "All timestamps are parsed as UTC. Rollover hours are an explicit analysis assumption and must be confirmed for this account/server.", "", "## Overall", "", "```csv", summary(frame).to_csv(index=False).strip(), "```", "", "## By UTC hour", "", "```csv", by_hour.to_csv(index=False).strip(), "```", "", "## RFBC checkpoint-hour observations", "", "```csv", summary(checkpoints).to_csv(index=False).strip() if not checkpoints.empty else "no observations", "```", "", "## Friday 16:00 UTC observations", "", "```csv", summary(friday_16).to_csv(index=False).strip() if not friday_16.empty else "no observations", "```", "", f"## Rollover-window observations ({args.rollover_start_hour:02d}:00-{args.rollover_end_hour:02d}:59 UTC)", "", "```csv", summary(rollover).to_csv(index=False).strip() if not rollover.empty else "no observations", "```", "", "## Dukascopy external-backtest cost reference", "", comparison, ""]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text("\n".join(report))
    print(args.output)


if __name__ == "__main__":
    main()
