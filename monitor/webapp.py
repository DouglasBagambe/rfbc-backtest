#!/usr/bin/env python3
from __future__ import annotations

from datetime import datetime, timezone
import os
import threading

import pandas as pd
import requests
from flask import Flask, jsonify, request
from waitress import serve

import rfbc_monitor_live as m
import selftest
import telegram_notify as tg
import fx101
import fx101_worker
import g_desk_adapter

SELFTEST = selftest.run()
print(f"RFBC_OPERATIONAL_SELFTEST {SELFTEST}", flush=True)

app = Flask(__name__)
_last_alert_keys: set[str] = set()


def _internal_ok() -> bool:
    token = os.getenv("G_DESK_ADAPTER_TOKEN", "").strip()
    return bool(token) and request.headers.get("X-G-Desk-Token", "") == token


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
    return "|".join(str(result.get(k, "")) for k in ("action", "symbol", "signal_dt", "entry_dt", "last_h4_close", "reason"))


def maybe_send_alert(result: dict) -> dict:
    action = result.get("action", "NONE")
    if action in ("NONE", "OPEN_TRADE", "STALE"):
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
        "equity_usd": float(os.environ.get("RFBC_EQUITY_USD", "10.01")),
        "risk_cap_pct": m.RISK_CAP_PCT,
        "aggregate_risk_cap_pct": m.AGGREGATE_RISK_CAP_PCT,
        "telegram_configured": tg.configured(),
        "selftest": SELFTEST,
    })


@app.get("/gdesk/health")
def gdesk_health():
    mode = os.getenv("G_DESK_RUNTIME_MODE", "api")
    return jsonify({
        "ok": True,
        "service": "g-desk-adapter",
        "market_context_provider": "dukascopy",
        "analysis_mode": mode,
        "openai_api_required": mode != "chatgpt_subscription",
        "execution": "manual",
    })


@app.get("/gdesk/context")
def gdesk_context():
    """Public read-only market context consumed by ChatGPT subscription automation."""
    try:
        return jsonify(g_desk_adapter.context_payload())
    except (RuntimeError, ValueError) as exc:
        fx101.log("gdesk_context_error", error=type(exc).__name__, detail=str(exc)[:200])
        return jsonify({"ok": False, "error": str(exc)}), 503


@app.post("/gdesk/analyze")
def gdesk_analyze():
    """Legacy paid-API path; disabled while ChatGPT subscription owns analysis."""
    if os.getenv("G_DESK_RUNTIME_MODE", "").strip() == "chatgpt_subscription":
        return jsonify({"ok": False, "error": "analysis_owned_by_chatgpt_subscription"}), 409
    if not _internal_ok():
        return jsonify({"ok": False, "error": "unauthorized"}), 401
    try:
        return jsonify(g_desk_adapter.analyze_payload(request.get_json(silent=True) or {}))
    except requests.RequestException as exc:
        return jsonify({"ok": False, "error": f"provider_error:{type(exc).__name__}"}), 502
    except (RuntimeError, ValueError) as exc:
        return jsonify({"ok": False, "error": str(exc)}), 503


@app.post("/analyze")
def analyze():
    """Paid-API trigger is intentionally unavailable in zero-cost subscription mode."""
    if os.getenv("G_DESK_RUNTIME_MODE", "").strip() == "chatgpt_subscription":
        return jsonify({"ok": False, "status": "analysis_owned_by_chatgpt_subscription"}), 409
    if not _internal_ok():
        return jsonify({"ok": False, "error": "unauthorized"}), 401
    ok, status = fx101.request_desk_analysis()
    return jsonify({"ok": ok, "status": status}), (200 if ok else 503)


@app.post("/desk/analyze")
def desk_analyze():
    """Authenticated external-decision ingest; never invent analysis here."""
    if not _internal_ok():
        return jsonify({"ok": False, "error": "unauthorized"}), 401
    body = request.get_json(silent=True) or {}
    ok, status, accepted = fx101.ingest_desk_response(body)
    return jsonify({"ok": ok, "status": status, "accepted": accepted}), (200 if ok else 400)


@app.post("/telegram/webhook")
def telegram_webhook():
    update = request.get_json(silent=True) or {}
    try:
        return jsonify({"ok": True, "status": fx101.receive_update(update)})
    except Exception as exc:
        app.logger.exception("fx101_telegram_update_failed")
        return jsonify({"ok": False, "error": type(exc).__name__}), 200


@app.get("/fx101/open")
def fx101_open():
    return jsonify(fx101.list_trades("WHERE state IN ('PLACED','OPEN')"))


@app.get("/fx101/health")
def fx101_health():
    try:
        open_trades = len(fx101.list_trades("WHERE state IN ('PLACED','OPEN')"))
        return jsonify({
            "ok": True,
            "service": "fx101",
            "open_trades": open_trades,
            "telegram_configured": bool(os.environ.get("TELEGRAM_BOT_TOKEN")),
            "gdesk_analysis_mode": os.getenv("G_DESK_RUNTIME_MODE", "api"),
            "gdesk_market_data": "dukascopy_h1_bid_ask",
            "lifecycle_price_data": "dukascopy_m1_bid_ask",
            "execution": "manual",
        })
    except Exception as exc:
        fx101.log("fx101_health_db_error", error=type(exc).__name__, detail=str(exc)[:200])
        return jsonify({"ok": False, "error": type(exc).__name__}), 503


@app.post("/fx101/prices")
def fx101_prices():
    """Authenticated deterministic lifecycle test/feed endpoint."""
    if not _internal_ok():
        return jsonify({"ok": False, "error": "unauthorized"}), 401
    body = request.get_json(silent=True) or {}
    prices = body.get("prices", {})
    if not isinstance(prices, dict):
        return jsonify({"ok": False, "error": "prices_must_be_object"}), 400
    changed = fx101.manage_prices(prices)
    for trade in changed:
        fx101.telegram_send(f"{trade['trade_id']} {trade['state']} at {trade['result_price']} ({trade.get('result_r')}R)")
    return jsonify({"ok": True, "changed": changed})


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
        actionable = [r for r in results if r["action"] not in ("NONE", "OPEN_TRADE", "STALE")]
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
    webhook_url = os.getenv("TELEGRAM_WEBHOOK_URL", "").strip()
    if webhook_url:
        ok, status = fx101.register_telegram_webhook(webhook_url)
        fx101.log("telegram_webhook_registration", ok=ok, status=status)
    threading.Thread(target=fx101_worker.main, name="fx101-worker", daemon=True).start()
    serve(app, host="0.0.0.0", port=int(os.getenv("PORT", "10000")), threads=6, channel_timeout=90)
