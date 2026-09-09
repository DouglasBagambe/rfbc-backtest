from datetime import datetime, timezone

import pytest

import rfbc_monitor_multi as m


def test_usdjpy_risk_conversion(monkeypatch):
    cfg = m.PAIR_CONFIGS["USDJPY"]
    risk_usd, pct, conversion = m.risk_pct(
        cfg,
        entry=153.0,
        stop=152.0,
        equity_usd=10.0,
        now=datetime(2026, 9, 9, tzinfo=timezone.utc),
    )
    assert conversion == pytest.approx(153.0)
    assert risk_usd == pytest.approx(10.0 / 153.0)
    assert pct == pytest.approx((10.0 / 153.0) / 10.0 * 100.0)


def test_audjpy_risk_uses_usdjpy_conversion(monkeypatch):
    cfg = m.PAIR_CONFIGS["AUDJPY"]
    monkeypatch.setattr(m, "usd_jpy_mid", lambda now: 153.5)
    risk_usd, pct, conversion = m.risk_pct(
        cfg,
        entry=110.8,
        stop=109.8,
        equity_usd=10.01,
        now=datetime(2026, 9, 9, tzinfo=timezone.utc),
    )
    assert conversion == pytest.approx(153.5)
    assert risk_usd == pytest.approx(10.0 / 153.5)
    assert pct == pytest.approx((10.0 / 153.5) / 10.01 * 100.0)


def test_portfolio_gate_accepts_only_lower_risk_when_both_do_not_fit():
    rows = [
        {"pair": "USDJPY", "action": {"kind": "trade", "risk_pct": 0.70}, "open_trade": None},
        {"pair": "AUDJPY", "action": {"kind": "trade", "risk_pct": 0.55}, "open_trade": None},
    ]
    out = m.apply_portfolio_gate(rows)
    by_pair = {x["pair"]: x for x in out}
    assert by_pair["AUDJPY"]["action"]["kind"] == "trade"
    assert by_pair["USDJPY"]["action"]["kind"] == "skip_portfolio_risk"


def test_portfolio_gate_existing_risk_blocks_new_trade():
    rows = [
        {
            "pair": "USDJPY",
            "action": {"kind": "none"},
            "open_trade": {"initial_risk_pct": 0.70},
        },
        {
            "pair": "AUDJPY",
            "action": {"kind": "trade", "risk_pct": 0.45},
            "open_trade": None,
        },
    ]
    out = m.apply_portfolio_gate(rows)
    aud = next(x for x in out if x["pair"] == "AUDJPY")
    assert aud["action"]["kind"] == "skip_portfolio_risk"
