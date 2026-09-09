#!/usr/bin/env python3
from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd
from flask import Flask, jsonify

import rfbc_monitor as m

app = Flask(__name__)


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


@app.get("/health")
def health():
    return jsonify({"ok": True, "service": "rfbc-usdjpy-monitor"})


@app.get("/check")
def check():
    now = datetime.now(timezone.utc)
    try:
        h4, _, _ = m.build_signal_frame(now)
        last_close = pd.Timestamp(h4.iloc[-1].close_dt)
        freshness = pd.Timestamp(now) - last_close
        if freshness > pd.Timedelta(minutes=20):
            return jsonify({
                "ok": True,
                "action": "NONE",
                "reason": "no_fresh_h4_close",
                "last_h4_close": last_close.isoformat(),
                "checked_at": now.isoformat(),
            })

        trade = m.candidate_trade(h4, now)
        event = m.infer_open_trade_and_event(h4, now)

        # Manual management actions take priority at the Friday cutoff, then BE, then new trade/skip.
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
        return jsonify(result)
    except Exception as exc:
        return jsonify({
            "ok": False,
            "action": "ERROR",
            "error_type": type(exc).__name__,
            "error": str(exc),
            "checked_at": now.isoformat(),
        }), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
