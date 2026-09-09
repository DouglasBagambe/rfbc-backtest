#!/usr/bin/env python3
from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd
from flask import Flask, jsonify

import rfbc_monitor_exact as m
import telegram_notify as tg

app = Flask(__name__)

# Best-effort duplicate suppression for repeated checks while this process lives.
_last_alert_key = None


def serialise_action(action):
    if action is None:
        return {"action": "NONE"}
    out = {}
    for k, v in action.items():
        if isinstance(v, pd.Timestamp):
            out[k] = v.isoformat()
        elif hasattr(v, "item"):
            try:
                out[k] = v.item()
            except Exception:
                out[k] = str(v)
        else:
            out[k] = v
    out["action"] = out.pop("kind", "UNKNOWN").upper()
    return out


def alert_key(result):
    return "|".join(
        str(result.get(k, ""))
        for k in ("action", "symbol", "signal_dt", "entry_dt", "last_h4_close", "reason")
    )


def maybe_send_alert(result):
    global _last_alert_key
    if result.get("action") == "NONE":
        return {"telegram_configured": tg.configured(), "telegram_sent": False, "telegram_status": "not_needed"}

    key = alert_key(result)
    if key == _last_alert_key:
        return {"telegram_configured": tg.configured(), "telegram_sent": False, "telegram_status": "duplicate_suppressed"}

    ok, status = tg.send_action(result)
    if ok:
        _last_alert_key = key
    return {"telegram_configured": tg.configured(), "telegram_sent": ok, "telegram_status": status}


@app.get("/health")
def health():
    return jsonify({
        "ok": True,
        "service": "rfbc-usdjpy-monitor",
        "logic": "exact_external_v1",
        "telegram_configured": tg.configured(),
    })


@app.get("/check")
def check():
    now = datetime.now(timezone.utc)
    try:
        h4, ask4, h1 = m.build_signal_frame(now)
        last_close = pd.Timestamp(h4.iloc[-1].close_dt)
        freshness = pd.Timestamp(now) - last_close
        if freshness > pd.Timedelta(minutes=20):
            result = {
                "ok": True,
                "action": "STALE",
                "reason": "no_fresh_completed_h4_bar",
                "last_h4_close": last_close.isoformat(),
                "checked_at": now.isoformat(),
                "symbol": m.SYMBOL,
                "volume": m.VOLUME,
                "risk_cap_pct": m.RISK_CAP_PCT,
            }
            result.update(maybe_send_alert(result))
            return jsonify(result)

        trade = m.candidate_trade(h4, now)
        event = m.infer_open_trade_and_event(h4, ask4, h1, now)

        if event and event.get("kind") == "friday_close":
            result = serialise_action(event)
        elif event and event.get("kind") == "move_be":
            result = serialise_action(event)
        elif trade:
            result = serialise_action(trade)
        else:
            result = {"action": "NONE"}

        result.update({
            "ok": True,
            "symbol": m.SYMBOL,
            "volume": m.VOLUME,
            "risk_cap_pct": m.RISK_CAP_PCT,
            "last_h4_close": last_close.isoformat(),
            "checked_at": now.isoformat(),
        })
        result.update(maybe_send_alert(result))
        return jsonify(result)
    except Exception as exc:
        result = {
            "ok": False,
            "action": "ERROR",
            "error_type": type(exc).__name__,
            "error": str(exc),
            "checked_at": now.isoformat(),
            "symbol": getattr(m, "SYMBOL", "USDJPYc"),
        }
        result.update(maybe_send_alert(result))
        return jsonify(result), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
