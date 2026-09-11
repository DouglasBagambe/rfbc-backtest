#!/usr/bin/env python3
from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd
from flask import Flask, jsonify, request

import rfbc_monitor_live as m
import selftest
import telegram_notify as tg
import fx101

SELFTEST = selftest.run()
print(f"RFBC_OPERATIONAL_SELFTEST {SELFTEST}", flush=True)

app = Flask(__name__)

# Best-effort duplicate suppression for repeated checks while this process lives.
_last_alert_keys: set[str] = set()


def serialise(value):
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    if isinstance(value, dict):
        return {k: serialise(v) for k, v in value.items()}
    if isinstance(value, list):
        return [serialise(v) for v in value]
    if hasattr(value, "item"):
        try:
            return value.item()
        except Exception:
            return str(value)
    return value


def flatten_result(pair_result: dict, checked_at: str) -> dict:
    action = serialise(pair_result.get("action") or {"kind": "none"})
    out = {
        "ok": True,
        "pair": pair_result["pair"],
        "symbol": pair_result["symbol"],
        "volume": m.VOLUME,
        "risk_cap_pct": m.RISK_CAP_PCT,
        "aggregate_risk_cap_pct": m.AGGREGATE_RISK_CAP_PCT,
        "last_h4_close": serialise(pair_result.get("last_h4_close")),
        "checked_at": checked_at,
        **{k: v for k, v in action.items() if k != "kind"},
        "action": str(action.get("kind", "none")).upper(),
    }
    if pair_result.get("open_trade"):
        out["open_trade"] = serialise(pair_result["open_trade"])
    return out


def alert_key(result: dict) -> str:
    return "|".join(
        str(result.get(k, ""))
        for k in ("action", "symbol", "signal_dt", "entry_dt", "last_h4_close", "reason")
    )


def maybe_send_alert(result: dict) -> dict:
    action = result.get("action", "NONE")
    if action in ("NONE", "OPEN_TRADE"):
        return {"telegram_configured": tg.configured(), "telegram_sent": False, "telegram_status": "not_needed"}

    key = alert_key(result)
    if key in _last_alert_keys:
        return {"telegram_configured": tg.configured(), "telegram_sent": False, "telegram_status": "duplicate_suppressed"}

    ok, status = tg.send_action(result)
    if ok:
        _last_alert_keys.add(key)
    return {"telegram_configured": tg.configured(), "telegram_sent": ok, "telegram_status": status}


@app.get("/")
def root():
    return jsonify({
        "ok": True,
        "service": "rfbc-two-pair-monitor",
        "pairs": [cfg.symbol for cfg in m.PAIR_CONFIGS.values()],
        "logic": "frozen_rfbc_v1_exact",
    })


@app.get("/health")
def health():
    return jsonify({
        "ok": bool(SELFTEST.get("ok")),
        "service": "rfbc-two-pair-monitor",
        "pairs": [cfg.symbol for cfg in m.PAIR_CONFIGS.values()],
        "logic": "frozen_rfbc_v1_exact",
        "equity_usd": float(__import__("os").environ.get("RFBC_EQUITY_USD", "10.01")),
        "risk_cap_pct": m.RISK_CAP_PCT,
        "aggregate_risk_cap_pct": m.AGGREGATE_RISK_CAP_PCT,
        "telegram_configured": tg.configured(),
        "selftest": SELFTEST,
    })


@app.post("/desk/analyze")
def desk_analyze():
    """Accept externally-produced G_DESK decisions; never invent analysis here."""
    body = request.get_json(silent=True) or {}
    decisions = body.get("decisions", [])
    if not isinstance(decisions, list):
        return jsonify({"ok": False, "error": "decisions_must_be_list"}), 400
    accepted, rejected = [], []
    for decision in decisions:
        decision = {**decision, "source": "G_DESK"}
        ok, status, trade = fx101.persist_decision(decision)
        (accepted if ok else rejected).append({"status": status, "trade": trade})
        if ok and status == "signalled": fx101.send_signal(trade)
    c = fx101.db(); c.execute("INSERT INTO scans VALUES (?,?,?,?,?)", (str(__import__('uuid').uuid4()), "G_DESK", datetime.now(timezone.utc).isoformat(), "TRADE" if accepted else "NO_TRADE", __import__('json').dumps(body))); c.commit()
    return jsonify({"ok": not rejected, "accepted": accepted, "rejected": rejected})


@app.post("/telegram/webhook")
def telegram_webhook():
    update = request.get_json(silent=True) or {}
    try:
        return jsonify({"ok": True, "status": fx101.receive_update(update)})
    except Exception as exc:
        app.logger.exception("fx101_telegram_update_failed")
        return jsonify({"ok": False, "error": type(exc).__name__}), 200


@app.get("/fx101/open")
def fx101_open(): return jsonify(fx101.list_trades("WHERE state IN ('PLACED','OPEN')"))


@app.get("/check")
def check():
    now = datetime.now(timezone.utc)
    checked_at = now.isoformat()
    try:
        raw = m.evaluate_all(now)
        results = []
        for item in raw:
            result = flatten_result(item, checked_at)
            result.update(maybe_send_alert(result))
            results.append(result)

        actionable = [r for r in results if r["action"] not in ("NONE", "OPEN_TRADE")]
        return jsonify({
            "ok": True,
            "service": "rfbc-two-pair-monitor",
            "checked_at": checked_at,
            "results": results,
            "actionable": actionable,
        })
    except Exception as exc:
        result = {
            "ok": False,
            "action": "ERROR",
            "error_type": type(exc).__name__,
            "error": str(exc),
            "checked_at": checked_at,
            "symbol": "PORTFOLIO",
        }
        result.update(maybe_send_alert(result))
        return jsonify(result), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
