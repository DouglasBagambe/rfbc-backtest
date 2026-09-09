#!/usr/bin/env python3
from __future__ import annotations

import os
from datetime import datetime, timezone

import numpy as np
import pandas as pd

import rfbc_monitor_multi as base

# Re-export the live constants/config expected by webapp.py.
PAIR_CONFIGS = base.PAIR_CONFIGS
VOLUME = base.VOLUME
RISK_CAP_PCT = base.RISK_CAP_PCT
AGGREGATE_RISK_CAP_PCT = base.AGGREGATE_RISK_CAP_PCT


def infer_open_trade_and_event(cfg, h4: pd.DataFrame, ask4: pd.DataFrame, h1: pd.DataFrame, now: datetime):
    """Reconstruct the latest frozen trade and emit management events deterministically.

    This is the production wrapper around the validated multi-pair monitor logic. It fixes the
    checkpoint notification edge case by emitting MOVE_BE exactly on the completed H4 close that
    first reaches +1.50R. On later checkpoints the trade remains OPEN_TRADE rather than repeatedly
    alerting MOVE_BE.
    """
    current_close = pd.Timestamp(h4.iloc[-1].close_dt)
    candidates = np.flatnonzero((h4.signal.to_numpy() != 0) & h4.close_dt.map(base.eligible_close).to_numpy())
    for i in reversed(candidates.tolist()):
        if i + 1 >= len(h4):
            continue
        s = h4.iloc[i]
        if pd.Timestamp(s.close_dt) >= current_close:
            continue

        side = int(s.signal)
        entry = float(ask4.open.iat[i + 1] if side == 1 else h4.open.iat[i + 1])
        if side * (entry - float(s.close)) > base.CHASE_ATR * float(s.atr):
            continue

        risk = base.ATR_MULT * float(s.atr)
        stop = entry - side * risk
        target = entry + side * base.RR * risk
        entry_dt = pd.Timestamp(h4.dt.iat[i + 1])
        armed = False
        active = True
        be_trigger_dt = None

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
            if boundary in h4_close_map and not armed:
                close_r = side * (float(h4_close_map[boundary]) - entry) / risk
                if close_r >= 1.50:
                    armed = True
                    be_trigger_dt = boundary

        if not active:
            continue

        equity = float(os.environ.get("RFBC_EQUITY_USD", "10.01"))
        risk_usd, initial_risk_pct, conversion = base.risk_pct(cfg, entry, stop, equity, now)
        common = {
            "side": side,
            "direction": "BUY" if side == 1 else "SELL",
            "signal_dt": pd.Timestamp(s.close_dt),
            "entry_dt": entry_dt,
            "entry_reference": entry,
            "initial_stop": stop,
            "target": target,
            "initial_risk_usd": risk_usd,
            "initial_risk_pct": initial_risk_pct,
            "conversion_usdjpy": conversion,
            "armed_be": armed,
        }

        if current_close.weekday() == 4 and current_close.hour == 16:
            return {"kind": "friday_close", **common}
        if be_trigger_dt is not None and be_trigger_dt == current_close:
            return {"kind": "move_be", "be_stop": entry, "be_trigger_dt": be_trigger_dt, **common}
        return {"kind": "open_trade", "be_trigger_dt": be_trigger_dt, **common}
    return None


def evaluate_all(now: datetime) -> list[dict]:
    results = []
    for pair, cfg in PAIR_CONFIGS.items():
        h4, ask4, h1 = base.build_signal_frame(cfg, now)
        last_close = pd.Timestamp(h4.iloc[-1].close_dt)
        freshness = pd.Timestamp(now) - last_close
        if freshness > pd.Timedelta(minutes=20):
            results.append({
                "pair": pair,
                "symbol": cfg.symbol,
                "last_h4_close": last_close,
                "action": {"kind": "stale", "reason": "no_fresh_completed_h4_bar"},
                "open_trade": None,
            })
            continue

        action = base.candidate_trade(cfg, h4, now)
        open_event = infer_open_trade_and_event(cfg, h4, ask4, h1, now)
        if open_event and open_event.get("kind") in ("friday_close", "move_be"):
            action = open_event

        results.append({
            "pair": pair,
            "symbol": cfg.symbol,
            "last_h4_close": last_close,
            "action": action or {"kind": "none"},
            "open_trade": open_event if open_event and open_event.get("kind") == "open_trade" else None,
        })
    return base.apply_portfolio_gate(results)


def _h4(rows):
    return pd.DataFrame(rows)


def _path(start: str, periods: int, low: float, high: float):
    idx = pd.date_range(start, periods=periods, freq="1h", tz="UTC")
    return pd.DataFrame(
        {
            "low_bid": [low] * periods,
            "high_bid": [high] * periods,
            "low_ask": [low] * periods,
            "high_ask": [high] * periods,
        },
        index=idx,
    )


def run_operational_selftests() -> dict:
    """Pure deterministic tests for every critical live decision path.

    No market request and no Telegram message is sent by these tests.
    """
    passed = []

    # Portfolio gate: only lower-risk candidate may fit when both exceed aggregate 1% together.
    rows = [
        {"pair": "USDJPY", "action": {"kind": "trade", "risk_pct": 0.70}, "open_trade": None},
        {"pair": "AUDJPY", "action": {"kind": "trade", "risk_pct": 0.55}, "open_trade": None},
    ]
    gated = base.apply_portfolio_gate(rows)
    by_pair = {x["pair"]: x for x in gated}
    assert by_pair["AUDJPY"]["action"]["kind"] == "trade"
    assert by_pair["USDJPY"]["action"]["kind"] == "skip_portfolio_risk"
    passed.append("SKIP_PORTFOLIO_RISK")

    # Existing open risk must block a new trade when aggregate risk would exceed 1%.
    rows = [
        {"pair": "USDJPY", "action": {"kind": "none"}, "open_trade": {"initial_risk_pct": 0.70}},
        {"pair": "AUDJPY", "action": {"kind": "trade", "risk_pct": 0.45}, "open_trade": None},
    ]
    gated = base.apply_portfolio_gate(rows)
    assert next(x for x in gated if x["pair"] == "AUDJPY")["action"]["kind"] == "skip_portfolio_risk"
    passed.append("OPEN_RISK_BLOCK")

    # MOVE_BE must fire exactly at the first completed H4 close >= +1.50R.
    cfg = PAIR_CONFIGS["USDJPY"]
    h4 = _h4([
        {"dt": pd.Timestamp("2026-09-07T04:00:00Z"), "close_dt": pd.Timestamp("2026-09-07T08:00:00Z"), "signal": 1, "atr": 1.0, "close": 100.0, "open": 99.8},
        {"dt": pd.Timestamp("2026-09-07T08:00:00Z"), "close_dt": pd.Timestamp("2026-09-07T12:00:00Z"), "signal": 0, "atr": 1.0, "close": 102.5, "open": 100.0},
    ])
    ask4 = _h4([
        {"open": 99.9},
        {"open": 100.1},
    ])
    path = _path("2026-09-07T08:00:00Z", 4, low=99.0, high=102.6)
    original_risk_pct = base.risk_pct
    base.risk_pct = lambda cfg, entry, stop, equity, now: (0.10, 0.90, 153.0)
    try:
        event = infer_open_trade_and_event(cfg, h4, ask4, path, datetime(2026, 9, 7, 12, 3, tzinfo=timezone.utc))
    finally:
        base.risk_pct = original_risk_pct
    assert event and event["kind"] == "move_be" and event["be_stop"] == 100.1
    passed.append("MOVE_BE")

    # Friday close must fire at the frozen Friday 16:00 UTC checkpoint for an active trade.
    h4_rows = []
    starts = pd.date_range("2026-09-10T12:00:00Z", periods=7, freq="4h")
    for j, dt in enumerate(starts):
        h4_rows.append({
            "dt": dt,
            "close_dt": dt + pd.Timedelta(hours=4),
            "signal": 1 if j == 0 else 0,
            "atr": 1.0,
            "close": 100.0 if j == 0 else 100.2,
            "open": 100.0,
        })
    h4 = _h4(h4_rows)
    ask4 = _h4([{"open": 100.1}] * len(h4_rows))
    path = _path("2026-09-10T16:00:00Z", 24, low=99.5, high=101.0)
    base.risk_pct = lambda cfg, entry, stop, equity, now: (0.10, 0.90, 153.0)
    try:
        event = infer_open_trade_and_event(cfg, h4, ask4, path, datetime(2026, 9, 11, 16, 3, tzinfo=timezone.utc))
    finally:
        base.risk_pct = original_risk_pct
    assert event and event["kind"] == "friday_close"
    passed.append("FRIDAY_CLOSE")

    # Candidate TRADE / SKIP_RISK / SKIP_CHASE / STALE paths.
    signal_h4 = _h4([
        {"close_dt": pd.Timestamp("2026-09-07T08:00:00Z"), "signal": 1, "atr": 1.0, "close": 100.0}
    ])
    original_latest_quote = base.latest_quote
    original_risk_pct = base.risk_pct
    try:
        base.latest_quote = lambda cfg, now: (100.05, 100.10, pd.Timestamp("2026-09-07T08:02:00Z"))
        base.risk_pct = lambda cfg, entry, stop, equity, now: (0.08, 0.80, 153.0)
        action = base.candidate_trade(cfg, signal_h4, datetime(2026, 9, 7, 8, 3, tzinfo=timezone.utc))
        assert action and action["kind"] == "trade"
        passed.append("TRADE")

        base.risk_pct = lambda cfg, entry, stop, equity, now: (0.12, 1.20, 153.0)
        action = base.candidate_trade(cfg, signal_h4, datetime(2026, 9, 7, 8, 3, tzinfo=timezone.utc))
        assert action and action["kind"] == "skip_risk"
        passed.append("SKIP_RISK")

        base.latest_quote = lambda cfg, now: (100.25, 100.30, pd.Timestamp("2026-09-07T08:02:00Z"))
        action = base.candidate_trade(cfg, signal_h4, datetime(2026, 9, 7, 8, 3, tzinfo=timezone.utc))
        assert action and action["kind"] == "skip_chase"
        passed.append("SKIP_CHASE")

        action = base.candidate_trade(cfg, signal_h4, datetime(2026, 9, 7, 8, 30, tzinfo=timezone.utc))
        assert action and action["kind"] == "stale"
        passed.append("STALE")
    finally:
        base.latest_quote = original_latest_quote
        base.risk_pct = original_risk_pct

    return {"ok": True, "passed": passed, "count": len(passed)}
