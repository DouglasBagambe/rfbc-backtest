#!/usr/bin/env python3
from __future__ import annotations

import os
from datetime import datetime, timedelta

import numpy as np
import pandas as pd
import dukascopy_python
from dukascopy_python import instruments

PAIR = "USDJPY"
SYMBOL = "USDJPYc"
INSTRUMENT = instruments.INSTRUMENT_FX_MAJORS_USD_JPY
LOOKBACK_DAYS = 430
ATR_PERIOD = 14
BREAKOUT_LOOKBACK = 20
ATR_MULT = 1.50
RR = 2.50
EMA_FAST = 50
EMA_SLOW = 200
EMA_SLOPE_LOOKBACK = 5
MAX_SIGNAL_TR_ATR = 2.0
CHASE_ATR = 0.20
VOLUME = 0.01
CONTRACT_SIZE = 1000.0
RISK_CAP_PCT = 1.0


def norm(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame(columns=["dt", "open", "high", "low", "close", "volume"])
    out = df.reset_index().rename(columns={df.reset_index().columns[0]: "dt"})
    out["dt"] = pd.to_datetime(out["dt"], utc=True, errors="coerce")
    out = out.dropna(subset=["dt", "open", "high", "low", "close"])
    keep = [c for c in ["dt", "open", "high", "low", "close", "volume"] if c in out.columns]
    return out[keep].sort_values("dt").drop_duplicates("dt")


def fetch(interval, side, start: datetime, end: datetime) -> pd.DataFrame:
    return norm(dukascopy_python.fetch(
        instrument=INSTRUMENT,
        interval=interval,
        offer_side=side,
        start=start.replace(tzinfo=None),
        end=end.replace(tzinfo=None),
        max_retries=4,
        debug=False,
    ))


def resample_h4(df: pd.DataFrame) -> pd.DataFrame:
    x = df.set_index("dt")
    grouped = x.resample("4h", label="left", closed="left")
    out = grouped.agg(open=("open", "first"), high=("high", "max"), low=("low", "min"), close=("close", "last"))
    out = out[grouped["open"].count().eq(4)]
    return out.dropna().reset_index()


def resample_d1(df: pd.DataFrame) -> pd.DataFrame:
    x = df.set_index("dt")
    out = x.resample("1D", label="left", closed="left").agg(
        open=("open", "first"), high=("high", "max"), low=("low", "min"), close=("close", "last")
    ).dropna()
    out = out[out.index.weekday < 5]
    return out.reset_index()


def true_range(df: pd.DataFrame) -> pd.Series:
    prev = df.close.shift(1)
    return pd.concat([
        (df.high - df.low).abs(),
        (df.high - prev).abs(),
        (df.low - prev).abs(),
    ], axis=1).max(axis=1)


def atr_wilder(df: pd.DataFrame, n: int = 14) -> pd.Series:
    return true_range(df).ewm(alpha=1 / n, adjust=False, min_periods=n).mean()


def eligible_close(ts: pd.Timestamp) -> bool:
    wd = ts.weekday()
    if wd <= 3:
        return ts.hour in (8, 12, 16) and ts.minute == 0
    return wd == 4 and ts.hour in (8, 12) and ts.minute == 0


def build_signal_frame(now: datetime):
    start = now - timedelta(days=LOOKBACK_DAYS)
    end = now + timedelta(hours=1)
    bid_h1 = fetch(dukascopy_python.INTERVAL_HOUR_1, dukascopy_python.OFFER_SIDE_BID, start, end)
    ask_h1 = fetch(dukascopy_python.INTERVAL_HOUR_1, dukascopy_python.OFFER_SIDE_ASK, start, end)
    if bid_h1.empty or ask_h1.empty:
        raise RuntimeError("Dukascopy returned empty H1 data")

    h4 = resample_h4(bid_h1)
    ask4 = resample_h4(ask_h1)
    d1 = resample_d1(bid_h1)
    now_ts = pd.Timestamp(now)
    h4 = h4[h4.dt + pd.Timedelta(hours=4) <= now_ts].copy()
    ask4 = ask4[ask4.dt + pd.Timedelta(hours=4) <= now_ts].copy()
    d1 = d1[d1.dt + pd.Timedelta(days=1) <= now_ts].copy()
    if len(h4) < 250 or len(d1) < EMA_SLOW + EMA_SLOPE_LOOKBACK:
        raise RuntimeError("Insufficient completed history for RFBC")

    d1["ema50"] = d1.close.ewm(span=EMA_FAST, adjust=False, min_periods=EMA_FAST).mean()
    d1["ema200"] = d1.close.ewm(span=EMA_SLOW, adjust=False, min_periods=EMA_SLOW).mean()
    d1["ema50_prev"] = d1.ema50.shift(EMA_SLOPE_LOOKBACK)
    d1["available_dt"] = d1.dt + pd.Timedelta(days=1)
    d1["regime"] = 0
    d1.loc[(d1.close > d1.ema50) & (d1.ema50 > d1.ema200) & (d1.ema50 > d1.ema50_prev), "regime"] = 1
    d1.loc[(d1.close < d1.ema50) & (d1.ema50 < d1.ema200) & (d1.ema50 < d1.ema50_prev), "regime"] = -1

    h4["close_dt"] = h4.dt + pd.Timedelta(hours=4)
    h4["atr"] = atr_wilder(h4, ATR_PERIOD)
    h4["tr"] = true_range(h4)
    h4["prev_high"] = h4.high.shift(1).rolling(BREAKOUT_LOOKBACK).max()
    h4["prev_low"] = h4.low.shift(1).rolling(BREAKOUT_LOOKBACK).min()
    h4 = pd.merge_asof(
        h4.sort_values("close_dt"),
        d1[["available_dt", "regime"]].sort_values("available_dt"),
        left_on="close_dt", right_on="available_dt", direction="backward",
    )
    h4["signal"] = 0
    common = h4.close_dt.map(eligible_close) & h4.atr.notna() & (h4.atr > 0) & (h4.tr <= MAX_SIGNAL_TR_ATR * h4.atr)
    h4.loc[common & h4.regime.eq(1) & (h4.close > h4.prev_high), "signal"] = 1
    h4.loc[common & h4.regime.eq(-1) & (h4.close < h4.prev_low), "signal"] = -1

    merged_h1 = bid_h1.merge(ask_h1, on="dt", suffixes=("_bid", "_ask"), validate="one_to_one").set_index("dt")
    return h4.reset_index(drop=True), ask4.reset_index(drop=True), merged_h1


def latest_quote(now: datetime):
    start = now - timedelta(minutes=20)
    end = now + timedelta(minutes=1)
    bid = fetch(dukascopy_python.INTERVAL_MIN_1, dukascopy_python.OFFER_SIDE_BID, start, end)
    ask = fetch(dukascopy_python.INTERVAL_MIN_1, dukascopy_python.OFFER_SIDE_ASK, start, end)
    if bid.empty or ask.empty:
        raise RuntimeError("No recent Dukascopy M1 quote")
    b, a = bid.iloc[-1], ask.iloc[-1]
    return float(b.close), float(a.close), max(pd.Timestamp(b.dt), pd.Timestamp(a.dt))


def risk_pct(entry: float, stop: float, equity_usd: float):
    units_usd = VOLUME * CONTRACT_SIZE
    risk_jpy = units_usd * abs(entry - stop)
    risk_usd = risk_jpy / entry
    pct = (risk_usd / equity_usd * 100.0) if equity_usd > 0 else float("inf")
    return risk_usd, pct


def candidate_trade(h4: pd.DataFrame, now: datetime):
    last = h4.iloc[-1]
    close_dt = pd.Timestamp(last.close_dt)
    if not eligible_close(close_dt) or int(last.signal) == 0:
        return None
    age = pd.Timestamp(now) - close_dt
    if age < pd.Timedelta(0) or age > pd.Timedelta(minutes=12):
        return {"kind": "stale", "close_dt": close_dt}

    side = int(last.signal)
    bid, ask, quote_dt = latest_quote(now)
    entry = ask if side == 1 else bid
    chase = side * (entry - float(last.close))
    max_chase = CHASE_ATR * float(last.atr)
    if chase > max_chase:
        return {"kind": "skip_chase", "side": side, "entry": entry, "signal_close": float(last.close),
                "atr": float(last.atr), "chase": chase, "max_chase": max_chase,
                "quote_dt": quote_dt, "close_dt": close_dt}

    risk_dist = ATR_MULT * float(last.atr)
    stop = entry - side * risk_dist
    target = entry + side * RR * risk_dist
    equity = float(os.environ.get("RFBC_EQUITY_USD", "10.01"))
    risk_usd, pct = risk_pct(entry, stop, equity)
    return {"kind": "trade" if pct <= RISK_CAP_PCT else "skip_risk", "side": side, "entry": entry,
            "stop": stop, "target": target, "atr": float(last.atr), "risk_usd": risk_usd,
            "risk_pct": pct, "equity": equity, "quote_dt": quote_dt, "close_dt": close_dt}


def infer_open_trade_and_event(h4: pd.DataFrame, ask4: pd.DataFrame, h1: pd.DataFrame, now: datetime):
    """Reconstruct the latest frozen trade using the validated next-H4 BID/ASK entry convention."""
    current_close = pd.Timestamp(h4.iloc[-1].close_dt)
    candidates = np.flatnonzero((h4.signal.to_numpy() != 0) & h4.close_dt.map(eligible_close).to_numpy())
    for i in reversed(candidates.tolist()):
        if i + 1 >= len(h4):
            continue
        s = h4.iloc[i]
        if pd.Timestamp(s.close_dt) >= current_close:
            continue
        side = int(s.signal)
        entry = float(ask4.open.iat[i + 1] if side == 1 else h4.open.iat[i + 1])
        if side * (entry - float(s.close)) > CHASE_ATR * float(s.atr):
            continue
        risk = ATR_MULT * float(s.atr)
        stop = entry - side * risk
        target = entry + side * RR * risk
        entry_dt = pd.Timestamp(h4.dt.iat[i + 1])
        armed = False
        active = True
        newly_armed_at = None

        path = h1[(h1.index >= entry_dt) & (h1.index < current_close)]
        h4_close_map = dict(zip(h4.close_dt, h4.close))
        for dt, b in path.iterrows():
            if dt.weekday() == 4 and dt.hour >= 16:
                active = False
                break
            active_stop = entry if armed else stop
            low = float(b.low_bid if side == 1 else b.low_ask)
            high = float(b.high_bid if side == 1 else b.high_ask)
            stop_hit = low <= active_stop if side == 1 else high >= active_stop
            target_hit = high >= target if side == 1 else low <= target
            if stop_hit or target_hit:
                active = False
                break
            boundary = dt + pd.Timedelta(hours=1)
            if boundary in h4_close_map and not armed and side * (float(h4_close_map[boundary]) - entry) / risk >= 1.50:
                armed = True
                newly_armed_at = boundary
        if not active:
            continue
        if current_close.weekday() == 4 and current_close.hour == 16:
            return {"kind": "friday_close", "side": side, "signal_dt": pd.Timestamp(s.close_dt), "entry_reference": entry}
        if side * (float(h4.iloc[-1].close) - entry) / risk >= 1.50 and newly_armed_at is None:
            return {"kind": "move_be", "side": side, "signal_dt": pd.Timestamp(s.close_dt), "entry_reference": entry}
        return None
    return None
