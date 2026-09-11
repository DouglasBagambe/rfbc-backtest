#!/usr/bin/env python3
"""Frozen, development-only S3B feature screen (2013-2017)."""
from __future__ import annotations

import argparse
import csv
import math
from pathlib import Path

import numpy as np
import pandas as pd

PAIRS = ("EURUSD", "GBPUSD", "USDJPY", "AUDUSD", "NZDUSD", "USDCAD", "USDCHF", "EURJPY", "GBPJPY", "AUDJPY", "CADJPY", "CHFJPY", "EURGBP", "EURAUD", "GBPAUD")
CURRENCIES = ("USD", "EUR", "GBP", "JPY", "AUD", "NZD", "CAD", "CHF")
START = pd.Timestamp("2013-01-01T00:00:00Z")
END = pd.Timestamp("2018-01-01T00:00:00Z")


def pair_orientation(pair: str, currency: str) -> int:
    if pair[:3] == currency: return 1
    if pair[3:] == currency: return -1
    raise ValueError(f"{currency} is not in {pair}")


def currency_strength(z_by_pair: dict[str, float]) -> dict[str, float]:
    out = {}
    for c in CURRENCIES:
        vals = [pair_orientation(p, c) * z for p, z in z_by_pair.items() if c in p]
        out[c] = float(np.mean(vals)) if vals else math.nan
    return out


def candidate_pair(strength: dict[str, float]) -> tuple[str, int]:
    scored = []
    for p in PAIRS:
        d = strength[p[:3]] - strength[p[3:]]
        scored.append((-abs(d), p, 1 if d > 0 else -1))
    _, p, direction = min(scored)
    return p, direction


def read_h1_until(path: Path) -> pd.DataFrame:
    """Read only development bars; terminate before parsing boundary OHLC."""
    rows = []
    with path.open(newline="") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            ts = pd.Timestamp(row["dt"])
            if ts.tzinfo is None: ts = ts.tz_localize("UTC")
            else: ts = ts.tz_convert("UTC")
            if ts >= END: break
            if ts < START: continue
            rows.append((ts, float(row["open"]), float(row["high"]), float(row["low"]), float(row["close"]), float(row["volume"])))
    return pd.DataFrame(rows, columns=["time", "open", "high", "low", "close", "volume"]).set_index("time")


def load_midpoints(data_root: Path) -> dict[str, pd.DataFrame]:
    result = {}
    for p in PAIRS:
        bid = read_h1_until(data_root / p / f"{p}_bid_h1.csv")
        ask = read_h1_until(data_root / p / f"{p}_ask_h1.csv")
        joined = bid.join(ask, lsuffix="_bid", rsuffix="_ask", how="inner")
        # Exclude market-closed / zero-volume bars without using later data.
        joined = joined[(joined.volume_bid > 0) & (joined.volume_ask > 0)]
        out = pd.DataFrame(index=joined.index)
        for col in ("open", "high", "low", "close"):
            out[col] = (joined[f"{col}_bid"] + joined[f"{col}_ask"]) / 2.0
        result[p] = out
    return result


def rate_panel(path: Path) -> pd.DataFrame:
    rates = pd.read_csv(path, parse_dates=["date"])
    rates["date"] = rates.date.dt.tz_localize("UTC")
    return rates.pivot(index="date", columns="currency", values="rate").reindex(columns=CURRENCIES).sort_index()


def build_events(bars: dict[str, pd.DataFrame], rates: pd.DataFrame) -> pd.DataFrame:
    common = sorted(set.intersection(*(set(x.index) for x in bars.values())))
    closes = pd.DataFrame({p: bars[p].reindex(common).close for p in PAIRS})
    highs = pd.DataFrame({p: bars[p].reindex(common).high for p in PAIRS})
    lows = pd.DataFrame({p: bars[p].reindex(common).low for p in PAIRS})
    r4 = np.log(closes / closes.shift(4)); sigma4 = r4.rolling(60).std()
    r1 = np.log(closes / closes.shift(1)); sigma1 = r1.rolling(60).std()
    tr = pd.DataFrame({p: pd.concat([highs[p]-lows[p], (highs[p]-closes[p].shift()).abs(), (lows[p]-closes[p].shift()).abs()], axis=1).max(axis=1) for p in PAIRS})
    atr = tr.rolling(14).mean()
    z = r4 / sigma4
    rate_hourly = rates.reindex(pd.DatetimeIndex(common).normalize(), method="ffill")
    rate_hourly.index = common
    records = []
    previous = []
    dispersion_history = []
    vol_history = []
    for i, ts in enumerate(common):
        # A candidate requires every frozen forward horizon inside development.
        if i + 8 >= len(common): break
        if i < 60 + 24 + 120 + 8: continue
        zrow = z.loc[ts]
        if zrow.isna().any(): continue
        strength = currency_strength(zrow.to_dict())
        pair, direction = candidate_pair(strength)
        base, quote = pair[:3], pair[3:]
        breadth = {}
        for c in CURRENCIES:
            vals = [pair_orientation(p, c) * np.sign(r4.at[ts, p]) for p in PAIRS if c in p]
            breadth[c] = float(np.mean(vals))
        disp = float(np.std(list(strength.values()), ddof=1)); dispersion_history.append(disp)
        pv = float(np.median(sigma4.loc[ts])); vol_history.append(pv)
        if len(dispersion_history) < 25 or len(vol_history) < 121: continue
        rate_base, rate_quote = rate_hourly.at[ts, base], rate_hourly.at[ts, quote]
        carry_ok = pd.notna(rate_base) and pd.notna(rate_quote) and np.sign(rate_base-rate_quote) == direction
        signed_r1 = direction * r1.at[ts, pair]
        stable = len(previous) >= 2 and all(x == (pair, direction) for x in previous[-2:])
        p80 = float(np.quantile(vol_history[-121:-1], .80))
        conditions = {
            "S3-01": True,
            "S3-02": carry_ok,
            "S3-03": disp > dispersion_history[-25] and breadth[base] >= .60 and breadth[quote] <= -.60,
            "S3-04": carry_ok and stable and signed_r1 < 0 and signed_r1 >= -.75 * sigma1.at[ts, pair],
            "S3-05": pv <= p80,
            "S3-06": carry_ok and signed_r1 > 0 and signed_r1 <= sigma1.at[ts, pair],
        }
        previous.append((pair, direction))
        for mech, active in conditions.items():
            if not active: continue
            for h in (4, 8):
                future = closes[pair].iloc[i+h]
                outcome = direction * (future - closes.at[ts, pair]) / atr.at[ts, pair]
                if pd.notna(outcome): records.append((mech, ts, pair, base, quote, direction, h, outcome))
    return pd.DataFrame(records, columns=["mechanism", "time", "pair", "base", "quote", "direction", "horizon_h1", "forward_atr"])


def aggregate(events: pd.DataFrame, group: list[str]) -> pd.DataFrame:
    def one(x: pd.DataFrame) -> pd.Series:
        n = len(x); mean = x.forward_atr.mean(); sd = x.forward_atr.std(ddof=1)
        return pd.Series({"sample_count": n, "mean_forward_atr": mean, "t_stat": mean / (sd / math.sqrt(n)) if n > 1 and sd else math.nan})
    return events.groupby(group, dropna=False).apply(one, include_groups=False).reset_index()


def write_outputs(events: pd.DataFrame, out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    summary = aggregate(events, ["mechanism", "horizon_h1"])
    years = events.assign(year=events.time.dt.year); by_year = aggregate(years, ["mechanism", "horizon_h1", "year"])
    by_pair = aggregate(events, ["mechanism", "horizon_h1", "pair"])
    by_currency = pd.concat([aggregate(events.rename(columns={"base":"currency"}), ["mechanism", "horizon_h1", "currency"]).assign(role="base"), aggregate(events.rename(columns={"quote":"currency"}), ["mechanism", "horizon_h1", "currency"]).assign(role="quote")])
    raw = events.groupby("mechanism").time.nunique().rename("raw_signal_hours").reset_index()
    raw["approx_per_week"] = raw.raw_signal_hours / ((END-START).days / 7)
    summary.to_csv(out / "summary.csv", index=False); by_year.to_csv(out / "by_year.csv", index=False); by_pair.to_csv(out / "by_pair.csv", index=False); by_currency.to_csv(out / "by_currency.csv", index=False); raw.to_csv(out / "frequency.csv", index=False)


def main() -> None:
    ap = argparse.ArgumentParser(); ap.add_argument("--data-root", type=Path, default=Path("data_independent/derived_m15")); ap.add_argument("--rates", type=Path, default=Path("strategy3_data/bis_cbpol_2013_2017.csv")); ap.add_argument("--out", type=Path, default=Path("results_next_strategy/strategy3_s3b")); args = ap.parse_args()
    events = build_events(load_midpoints(args.data_root), rate_panel(args.rates)); write_outputs(events, args.out)

if __name__ == "__main__": main()
