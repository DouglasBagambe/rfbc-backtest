#!/usr/bin/env python3
from __future__ import annotations

from datetime import datetime, timezone

import rfbc_monitor_multi as m
import rfbc_monitor_live as live
import telegram_notify as tg


def _assert_contains(text: str, *parts: str) -> None:
    for part in parts:
        assert part in text, f"missing {part!r} from formatted alert: {text!r}"


def run() -> dict:
    now = datetime(2026, 9, 9, tzinfo=timezone.utc)

    # Frozen live universe / broker symbol mapping.
    assert set(m.PAIR_CONFIGS) == {"USDJPY", "AUDJPY"}
    assert m.PAIR_CONFIGS["USDJPY"].symbol == "USDJPYc"
    assert m.PAIR_CONFIGS["AUDJPY"].symbol == "AUDJPYc"
    assert m.VOLUME == 0.01
    assert m.RISK_CAP_PCT == 1.0
    assert m.AGGREGATE_RISK_CAP_PCT == 1.0

    # USDJPY risk conversion.
    usd_cfg = m.PAIR_CONFIGS["USDJPY"]
    risk_usd, pct, conversion = m.risk_pct(usd_cfg, 153.0, 152.0, 10.0, now)
    assert abs(conversion - 153.0) < 1e-12
    assert abs(risk_usd - (10.0 / 153.0)) < 1e-12
    assert abs(pct - ((10.0 / 153.0) / 10.0 * 100.0)) < 1e-12

    # AUDJPY conversion must use USDJPY, not AUDJPY entry.
    original_mid = m.usd_jpy_mid
    try:
        m.usd_jpy_mid = lambda _now: 153.5
        aud_cfg = m.PAIR_CONFIGS["AUDJPY"]
        risk_usd, pct, conversion = m.risk_pct(aud_cfg, 110.8, 109.8, 10.01, now)
        assert abs(conversion - 153.5) < 1e-12
        assert abs(risk_usd - (10.0 / 153.5)) < 1e-12
        assert abs(pct - ((10.0 / 153.5) / 10.01 * 100.0)) < 1e-12
    finally:
        m.usd_jpy_mid = original_mid

    # Same-checkpoint aggregate gate: lower-risk candidate wins.
    rows = [
        {"pair": "USDJPY", "action": {"kind": "trade", "risk_pct": 0.70}, "open_trade": None},
        {"pair": "AUDJPY", "action": {"kind": "trade", "risk_pct": 0.55}, "open_trade": None},
    ]
    out = m.apply_portfolio_gate(rows)
    by_pair = {x["pair"]: x for x in out}
    assert by_pair["AUDJPY"]["action"]["kind"] == "trade"
    assert by_pair["USDJPY"]["action"]["kind"] == "skip_portfolio_risk"

    # Existing initial risk consumes the aggregate cap.
    rows = [
        {"pair": "USDJPY", "action": {"kind": "none"}, "open_trade": {"initial_risk_pct": 0.70}},
        {"pair": "AUDJPY", "action": {"kind": "trade", "risk_pct": 0.45}, "open_trade": None},
    ]
    out = m.apply_portfolio_gate(rows)
    aud = next(x for x in out if x["pair"] == "AUDJPY")
    assert aud["action"]["kind"] == "skip_portfolio_risk"

    # Alert vocabulary / operator-readable ticket formatting.
    samples = [
        ({"action":"TRADE","symbol":"USDJPYc","direction":"BUY","volume":0.01,"entry":153.1,"stop":152.1,"target":155.6,"risk_pct":0.7}, ("RFBC TRADE","Direction: BUY","Volume: 0.01","SL:","TP:","Estimated risk %:")),
        ({"action":"SKIP_RISK","symbol":"AUDJPYc","risk_pct":1.2,"reason":"risk cap"}, ("RFBC SKIP_RISK","Estimated risk %: 1.2","Reason: risk cap")),
        ({"action":"SKIP_CHASE","symbol":"USDJPYc","reason":"chase gate"}, ("RFBC SKIP_CHASE","Reason: chase gate")),
        ({"action":"SKIP_PORTFOLIO_RISK","symbol":"AUDJPYc","aggregate_open_risk_before_pct":0.7}, ("RFBC SKIP_PORTFOLIO_RISK","aggregate_open_risk_before_pct: 0.7")),
        ({"action":"MOVE_BE","symbol":"USDJPYc","direction":"BUY","be_stop":153.1}, ("RFBC MOVE_BE","BE stop: 153.1")),
        ({"action":"FRIDAY_CLOSE","symbol":"AUDJPYc","direction":"SELL"}, ("RFBC FRIDAY_CLOSE","Direction: SELL")),
        ({"action":"STALE","symbol":"PORTFOLIO","reason":"no_fresh_completed_h4_bar"}, ("RFBC STALE","Reason: no_fresh_completed_h4_bar")),
        ({"action":"ERROR","symbol":"PORTFOLIO","error":"synthetic"}, ("RFBC ERROR","Error: synthetic")),
    ]
    for payload, expected in samples:
        text = tg.format_action(payload)
        _assert_contains(text, *expected)

    decision_paths = live.run_operational_selftests()
    assert decision_paths["ok"] is True

    return {
        "ok": True,
        "pairs": [m.PAIR_CONFIGS[p].symbol for p in ("USDJPY", "AUDJPY")],
        "risk_cap_pct": m.RISK_CAP_PCT,
        "aggregate_risk_cap_pct": m.AGGREGATE_RISK_CAP_PCT,
        "alert_actions_tested": [x[0]["action"] for x in samples],
        "decision_path_selftest": decision_paths,
    }


if __name__ == "__main__":
    print(run())
