#!/usr/bin/env python3
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd
import requests
import dukascopy_python
from dukascopy_python import instruments

PAIR = "USDJPY"
SYMBOL = "USDJPYc"
INSTRUMENT = instruments.INSTRUMENT_FX_MAJORS_USD_JPY
LOOKBACK_DAYS = 420
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
    out = df.reset_index()
    out = out.rename(columns={out.columns[0]: "dt"})
    out["dt"] = pd.to_datetime(out["dt"], utc=True, errors="coerce")
    out = out.dropna(subset=["dt", "open", "high", "low", "close"])
    keep = [c for c in ["dt", "open", "high", "low", "close", "volume"] if c in out.columns]
    return out[keep].sort_values("dt").drop_duplicates("dt")


def fetch(interval, side, start: datetime, end: datetime) -> pd.DataFrame:
    return norm(
        dukascopy_python.fetch(
            instrument=INSTRUMENT,
            interval=interval,
            offer_side=side,
            start=start.replace(tzinfo=None),
            end=end.replace(tzinfo=None),
            max_retries=4,
            debug=False,
        )
    )


def resample_ohlc(df: pd.DataFrame, rule: str) -> pd.DataFrame:
    x = df.set_index("dt")
    agg = x.resample(rule, origin="start_day", label="left", closed="left").agg(
        open=("open", "first"), high=("high", "max"), low=("low", "min"), close=("close", "last")
    )
    return agg.dropna().reset_index()


def true_range(df: pd.DataFrame) -> pd.Series:
    prev = df["close"].shift(1)
    return pd.concat(
        [(df["high"] - df["low"]).abs(), (df["high"] - prev).abs(), (df["low"] - prev).abs()], axis=1
    ).max(axis=1)


def eligible_close(ts: pd.Timestamp) -> bool:
    wd = ts.weekday()
    hm = (ts.hour, ts.minute)
    if wd <= 3:
        return hm in {(8, 0), (12, 0), (16, 0)}
    if wd == 4:
        return hm in {(8, 0), (12, 0)}
    return False


def notify(title: str, body: str, priority: str = "high") -> None:
    topic = os.environ.get("NTFY_TOPIC", "").strip()
    if not topic:
        print(title)
        print(body)
        return
    server = os.environ.get("NTFY_SERVER", "https://ntfy.sh").rstrip("/")
    r = requests.post(
        f"{server}/{topic}",
        data=body.encode("utf-8"),
        headers={"Title": title, "Priority": priority, "Tags": "chart_with_upwards_trend"},
        timeout=20,
    )
    r.raise_for_status()


def build_signal_frame(now: datetime):
    start = now - timedelta(days=LOOKBACK_DAYS)
    bid_h1 = fetch(dukascopy_python.INTERVAL_HOUR_1, dukascopy_python.OFFER_SIDE_BID, start, now + timedelta(hours=1))
    ask_h1 = fetch(dukascopy_python.INTERVAL_HOUR_1, dukascopy_python.OFFER_SIDE_ASK, start, now + timedelta(hours=1))
    if bid_h1.empty or ask_h1.empty:
        raise RuntimeError("Dukascopy returned empty H1 data")

    h4 = resample_ohlc(bid_h1, "4h")
    d1 = resample_ohlc(bid_h1, "1d")
    now_ts = pd.Timestamp(now)
    h4 = h4[h4.dt + pd.Timedelta(hours=4) <= now_ts].copy()
    d1 = d1[d1.dt + pd.Timedelta(days=1) <= now_ts].copy()
    if len(h4) < 250 or len(d1) < EMA_SLOW + EMA_SLOPE_LOOKBACK + 5:
        raise RuntimeError("Insufficient completed history for RFBC")

    d1["ema50"] = d1.close.ewm(span=EMA_FAST, adjust=False).mean()
    d1["ema200"] = d1.close.ewm(span=EMA_SLOW, adjust=False).mean()
    d1["ema50_prev"] = d1.ema50.shift(EMA_SLOPE_LOOKBACK)
    d1["d1_close_dt"] = d1.dt + pd.Timedelta(days=1)
    d1["regime"] = 0
    d1.loc[(d1.ema50 > d1.ema200) & (d1.ema50 > d1.ema50_prev), "regime"] = 1
    d1.loc[(d1.ema50 < d1.ema200) & (d1.ema50 < d1.ema50_prev), "regime"] = -1

    h4["close_dt"] = h4.dt + pd.Timedelta(hours=4)
    h4["tr"] = true_range(h4)
    h4["atr"] = h4.tr.rolling(ATR_PERIOD).mean()
    h4["prev_high"] = h4.high.shift(1).rolling(BREAKOUT_LOOKBACK).max()
    h4["prev_low"] = h4.low.shift(1).rolling(BREAKOUT_LOOKBACK).min()

    regimes = d1[["d1_close_dt", "regime"]].sort_values("d1_close_dt")
    h4 = pd.merge_asof(
        h4.sort_values("close_dt"), regimes, left_on="close_dt", right_on="d1_close_dt", direction="backward", allow_exact_matches=True
    )
    h4["signal"] = 0
    common = h4.atr.notna() & (h4.atr > 0) & (h4.tr <= MAX_SIGNAL_TR_ATR * h4.atr)
    h4.loc[common & (h4.regime == 1) & (h4.close > h4.prev_high), "signal"] = 1
    h4.loc[common & (h4.regime == -1) & (h4.close < h4.prev_low), "signal"] = -1
    return h4, bid_h1, ask_h1


def latest_quote(now: datetime):
    start = now - timedelta(minutes=20)
    bid = fetch(dukascopy_python.INTERVAL_MIN_1, dukascopy_python.OFFER_SIDE_BID, start, now + timedelta(minutes=1))
    ask = fetch(dukascopy_python.INTERVAL_MIN_1, dukascopy_python.OFFER_SIDE_ASK, start, now + timedelta(minutes=1))
    if bid.empty or ask.empty:
        raise RuntimeError("No recent Dukascopy M1 quote")
    b = bid.iloc[-1]
    a = ask.iloc[-1]
    return float(b.close), float(a.close), max(pd.Timestamp(b.dt), pd.Timestamp(a.dt))


def risk_pct(entry: float, stop: float, equity_usd: float) -> tuple[float, float]:
    units_usd = VOLUME * CONTRACT_SIZE
    risk_jpy = units_usd * abs(entry - stop)
    risk_usd = risk_jpy / entry
    pct = risk_usd / equity_usd * 100.0 if equity_usd > 0 else float("inf")
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
        return {
            "kind": "skip_chase", "side": side, "entry": entry, "signal_close": float(last.close), "atr": float(last.atr),
            "chase": chase, "max_chase": max_chase, "quote_dt": quote_dt, "close_dt": close_dt,
        }

    risk_dist = ATR_MULT * float(last.atr)
    stop = entry - side * risk_dist
    target = entry + side * RR * risk_dist
    equity = float(os.environ.get("RFBC_EQUITY_USD", "10.01"))
    risk_usd, pct = risk_pct(entry, stop, equity)
    return {
        "kind": "trade" if pct <= RISK_CAP_PCT else "skip_risk",
        "side": side, "entry": entry, "stop": stop, "target": target, "atr": float(last.atr), "risk_usd": risk_usd,
        "risk_pct": pct, "equity": equity, "quote_dt": quote_dt, "close_dt": close_dt,
    }


def infer_open_trade_and_event(h4: pd.DataFrame, now: datetime):
    """Reconstruct the most recent qualifying frozen signal and whether this H4 close creates a BE/Friday action.

    This is intentionally conservative and stateless. SL/TP are assumed to have been placed server-side by the user,
    so this function only emits manual management events that must happen at completed H4/Friday checkpoints.
    """
    current_close = pd.Timestamp(h4.iloc[-1].close_dt)
    signals = h4[(h4.signal != 0) & h4.close_dt.map(eligible_close)]
    if signals.empty:
        return None
    s = signals.iloc[-1]
    s_close_dt = pd.Timestamp(s.close_dt)
    if s_close_dt >= current_close:
        return None

    side = int(s.signal)
    entry = float(s.close)  # conservative proxy for stateless management reconstruction
    risk_dist = ATR_MULT * float(s.atr)
    target = entry + side * RR * risk_dist
    stop = entry - side * risk_dist
    be_level = entry + side * 1.50 * risk_dist

    path = h4[(h4.dt >= s_close_dt) & (h4.close_dt <= current_close)].copy()
    be_first = None
    for _, b in path.iterrows():
        if side == 1:
            if float(b.low) <= stop or float(b.high) >= target:
                return None
        else:
            if float(b.high) >= stop or float(b.low) <= target:
                return None
        if be_first is None and side * (float(b.close) - entry) >= 1.50 * risk_dist:
            be_first = pd.Timestamp(b.close_dt)

    if current_close.weekday() == 4 and current_close.hour == 16:
        return {"kind": "friday_close", "side": side, "signal_dt": s_close_dt}
    if be_first is not None and be_first == current_close:
        return {"kind": "move_be", "side": side, "signal_dt": s_close_dt, "entry_proxy": entry}
    return None


def main():
    now = datetime.now(timezone.utc)
    try:
        h4, _, _ = build_signal_frame(now)
        last_close = pd.Timestamp(h4.iloc[-1].close_dt)
        if pd.Timestamp(now) - last_close > pd.Timedelta(minutes=15):
            print(f"No fresh completed H4 close yet. Last={last_close}")
            return

        trade = candidate_trade(h4, now)
        if trade:
            if trade["kind"] == "trade":
                d = "BUY" if trade["side"] == 1 else "SELL"
                body = (
                    f"TRADE {SYMBOL} {d}\n"
                    f"Volume: {VOLUME:.2f}\n"
                    f"Entry now: {trade['entry']:.3f}\n"
                    f"SL: {trade['stop']:.3f}\n"
                    f"TP: {trade['target']:.3f}\n"
                    f"ATR14(H4): {trade['atr']:.3f}\n"
                    f"Est risk: ${trade['risk_usd']:.3f} ({trade['risk_pct']:.2f}% of ${trade['equity']:.2f})\n"
                    f"Quote time UTC: {trade['quote_dt']}\n"
                    "Set SL and TP immediately."
                )
                notify("RFBC TRADE", body, "urgent")
            elif trade["kind"] == "skip_risk":
                d = "BUY" if trade["side"] == 1 else "SELL"
                notify(
                    "RFBC SKIP",
                    f"SKIP {SYMBOL} {d}: minimum 0.01 volume estimates {trade['risk_pct']:.2f}% risk, above 1.00% cap.",
                )
            elif trade["kind"] == "skip_chase":
                d = "BUY" if trade["side"] == 1 else "SELL"
                notify(
                    "RFBC SKIP",
                    f"SKIP {SYMBOL} {d}: no-chase threshold exceeded. Move={trade['chase']:.3f}, max={trade['max_chase']:.3f}.",
                )
            elif trade["kind"] == "stale":
                notify("RFBC SKIP", f"SKIP {SYMBOL}: signal evaluation became stale after {trade['close_dt']} UTC.")

        event = infer_open_trade_and_event(h4, now)
        if event and event["kind"] == "move_be":
            notify(
                "RFBC MOVE SL TO BE",
                f"{SYMBOL}: completed H4 close has reached +1.50R for the latest inferred RFBC trade. If you entered that signal, move SL to cost-adjusted breakeven now.",
                "urgent",
            )
        elif event and event["kind"] == "friday_close":
            notify(
                "RFBC CLOSE NOW",
                f"{SYMBOL}: Friday 16:00 UTC cutoff. If the latest RFBC trade is still open, close it now.",
                "urgent",
            )

        print(f"RFBC monitor OK at {now.isoformat()} latest_h4_close={last_close}")
    except Exception as exc:
        notify("RFBC MONITOR ERROR", f"{type(exc).__name__}: {exc}", "high")
        raise


if __name__ == "__main__":
    main()
