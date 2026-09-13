#!/usr/bin/env python3
"""Always-on non-MT5 lifecycle-price, RFBC, and free G_DESK bridge worker."""
from __future__ import annotations
import json, logging, os, signal, time
import uuid
from datetime import datetime, timezone

import pandas as pd
import requests
import dukascopy_python
from dukascopy_python import instruments

import fx101
import rfbc_monitor_live as rfbc
import telegram_notify as telegram

logging.basicConfig(level=os.getenv("LOG_LEVEL","INFO"), format="%(message)s")
RUNNING=True

PAIR_TO_INSTRUMENT = {
    "EURUSD": instruments.INSTRUMENT_FX_MAJORS_EUR_USD,
    "GBPUSD": instruments.INSTRUMENT_FX_MAJORS_GBP_USD,
    "GBPJPY": instruments.INSTRUMENT_FX_CROSSES_GBP_JPY,
    "USDCAD": instruments.INSTRUMENT_FX_MAJORS_USD_CAD,
    "EURJPY": instruments.INSTRUMENT_FX_CROSSES_EUR_JPY,
    "USDJPY": instruments.INSTRUMENT_FX_MAJORS_USD_JPY,
    "AUDJPY": instruments.INSTRUMENT_FX_CROSSES_AUD_JPY,
}

GDESK_RUNTIME_URL = os.getenv(
    "G_DESK_RUNTIME_URL",
    "https://raw.githubusercontent.com/DouglasBagambe/rfbc-backtest/gdesk-runtime/runtime/gdesk_decision.json",
).strip()


def stop(*_):
    global RUNNING
    RUNNING=False


signal.signal(signal.SIGTERM, stop)
signal.signal(signal.SIGINT, stop)


def _normalise(frame) -> pd.DataFrame:
    if frame is None or frame.empty:
        return pd.DataFrame(columns=["dt", "close", "volume"])
    reset = frame.reset_index()
    out = reset.rename(columns={reset.columns[0]: "dt"})
    out["dt"] = pd.to_datetime(out["dt"], utc=True, errors="coerce")
    for col in ("close", "volume"):
        if col in out.columns:
            out[col] = pd.to_numeric(out[col], errors="coerce")
    out = out.dropna(subset=["dt", "close"])
    if "volume" in out.columns:
        out = out[out["volume"].fillna(0) > 0]
    return out.sort_values("dt").drop_duplicates("dt")


def _fetch_side(pair: str, side: str, start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    offer = dukascopy_python.OFFER_SIDE_BID if side == "bid" else dukascopy_python.OFFER_SIDE_ASK
    last_exc = None
    for attempt in range(1, 4):
        try:
            frame = dukascopy_python.fetch(
                instrument=PAIR_TO_INSTRUMENT[pair],
                interval=dukascopy_python.INTERVAL_MIN_1,
                offer_side=offer,
                start=start.to_pydatetime().replace(tzinfo=None),
                end=end.to_pydatetime().replace(tzinfo=None),
                max_retries=3,
                debug=False,
            )
            out = _normalise(frame)
            if out.empty:
                raise RuntimeError(f"empty_dukascopy_m1:{pair}:{side}")
            return out
        except Exception as exc:
            last_exc = exc
            if attempt < 3:
                time.sleep(attempt)
    raise RuntimeError(f"dukascopy_m1_failed:{pair}:{side}:{type(last_exc).__name__}")


def prices() -> dict[str, float]:
    """Free lifecycle snapshots from Dukascopy M1 BID/ASK; no Twelve Data quota."""
    now = pd.Timestamp.now(tz="UTC")
    start = now - (pd.Timedelta(hours=72) if now.weekday() >= 5 else pd.Timedelta(minutes=30))
    out: dict[str, float] = {}
    latest_ts: list[pd.Timestamp] = []
    for symbol in sorted(fx101.ALL_SYMBOLS):
        pair = symbol[:6]
        if pair not in PAIR_TO_INSTRUMENT:
            continue
        bid = _fetch_side(pair, "bid", start, now)
        ask = _fetch_side(pair, "ask", start, now)
        merged = bid[["dt", "close"]].merge(ask[["dt", "close"]], on="dt", how="inner", suffixes=("_bid", "_ask"))
        if merged.empty:
            raise RuntimeError(f"no_aligned_dukascopy_m1:{pair}")
        row = merged.sort_values("dt").iloc[-1]
        ts = pd.Timestamp(row["dt"])
        if now.weekday() < 5 and now - ts > pd.Timedelta(minutes=20):
            raise RuntimeError(f"stale_dukascopy_m1:{pair}:{ts.isoformat()}")
        latest_ts.append(ts)
        out[symbol] = float((row["close_bid"] + row["close_ask"]) / 2)
    if not out:
        raise RuntimeError("dukascopy_price_provider_empty")
    fx101.log("price_snapshot", provider="dukascopy_m1", symbols=len(out), latest=max(latest_ts).isoformat() if latest_ts else None)
    return out


def scan_rfbc() -> None:
    """Run frozen RFBC unchanged; push only genuinely actionable events."""
    now = datetime.now(timezone.utc)
    for item in rfbc.evaluate_all(now):
        action = item.get("action") or {"kind":"none"}
        kind = str(action.get("kind","none")).upper()
        if kind in {"NONE", "OPEN_TRADE", "STALE"}:
            continue
        telegram.send_action({"action":kind,"symbol":item["symbol"],"checked_at":now.isoformat(),**action})
    fx101.log("rfbc_scan", checked_at=now.isoformat())


def _open_trade_count() -> int:
    try:
        return len(fx101.list_trades("WHERE state IN ('PLACED','OPEN')"))
    except Exception:
        return 0


def _emit_gdesk_context_snapshot(hour_key: str) -> None:
    """Publish live G_DESK context into Render logs for ChatGPT automation.

    Context is emitted one symbol per log line so each JSON event remains small
    enough for the logging pipeline. The scheduled ChatGPT task reads the five
    events sharing the same scan_id and performs the actual analysis itself.
    """
    # Lazy import keeps lifecycle/RFBC operational if the optional Flask route
    # dependencies are absent from a focused worker test environment.
    import g_desk_adapter
    payload = g_desk_adapter.context_payload()
    scan_id = f"GDESK-{hour_key}-{uuid.uuid4().hex[:10]}"
    for symbol in payload["symbols"]:
        fx101.log(
            "gdesk_context_symbol",
            scan_id=scan_id,
            generated_at=payload["generated_at"],
            symbol=symbol,
            latest_completed_bar=payload["latest_completed_bar"].get(symbol),
            market_state=payload["market_state"],
            freshness=payload["freshness"],
            source=payload["source"],
            timeframe=payload["timeframe"],
            bars=payload["bars"][symbol],
        )
    fx101.log(
        "gdesk_context_ready",
        scan_id=scan_id,
        generated_at=payload["generated_at"],
        symbols=payload["symbols"],
        market_state=payload["market_state"],
        freshness=payload["freshness"],
        owner="chatgpt_subscription",
    )


def _bridge_marker_exists(decision_id: str) -> bool:
    c = fx101.db()
    return bool(list(c.execute("SELECT id FROM scans WHERE id=?", (decision_id,))))


def _mark_bridge_consumed(decision_id: str, result: str, payload: dict) -> None:
    c = fx101.db()
    c.execute(
        "INSERT INTO scans VALUES (?,?,?,?,?)",
        (decision_id, "G_DESK_BRIDGE", fx101.now(), result, json.dumps(payload, separators=(",", ":"))),
    )
    c.commit()


def _reject_bridge(decision_id: str, reason: str, payload: dict) -> None:
    _mark_bridge_consumed(decision_id, "REJECTED", {"reason":reason,"payload":payload})
    fx101.log("gdesk_bridge_rejected", reason=reason, decision_id=decision_id)


def _consume_gdesk_runtime_decision() -> None:
    """Consume the newest ChatGPT decision from the non-deployed runtime branch."""
    if not GDESK_RUNTIME_URL:
        return
    r = requests.get(
        GDESK_RUNTIME_URL,
        params={"cache_bust": int(time.time())},
        headers={"Cache-Control": "no-cache"},
        timeout=15,
    )
    r.raise_for_status()
    body = r.json()
    decision_id = str(body.get("decision_id") or "").strip()
    result = str(body.get("result") or "").upper().strip()
    if not decision_id or decision_id == "INIT" or result == "NONE":
        return
    if _bridge_marker_exists(decision_id):
        return

    generated_at = str(body.get("generated_at") or "")
    try:
        generated = datetime.fromisoformat(generated_at.replace("Z", "+00:00"))
        age = datetime.now(timezone.utc) - generated.astimezone(timezone.utc)
    except Exception:
        _reject_bridge(decision_id, "invalid_generated_at", body)
        return
    if age.total_seconds() < -300 or age.total_seconds() > 3600:
        _reject_bridge(decision_id, "future_or_stale_decision", body)
        return

    if result == "SYSTEM_FAILURE":
        message = str(body.get("message") or "G_DESK analysis bridge reported a system failure.")[:700]
        fx101.telegram_send(f"G DESK SYSTEM FAILURE\n{message}")
        _mark_bridge_consumed(decision_id, result, body)
        fx101.log("gdesk_bridge_consumed", decision_id=decision_id, result=result)
        return

    if result == "NO_TRADE":
        ok, status, _ = fx101.ingest_desk_response({"decisions": []})
    elif result == "TRADE":
        decisions = body.get("decisions")
        if not isinstance(decisions, list) or len(decisions) != 1:
            _reject_bridge(decision_id, "trade_requires_one_decision", body)
            return
        ok, status, _ = fx101.ingest_desk_response({"decisions": decisions})
    else:
        _reject_bridge(decision_id, "invalid_result", body)
        return

    if ok:
        _mark_bridge_consumed(decision_id, result, body)
        fx101.log("gdesk_bridge_consumed", decision_id=decision_id, result=result, ingest_status=status)
    else:
        _reject_bridge(decision_id, f"ingest_failed:{status}", body)


def main() -> None:
    poll = max(10, int(os.getenv("FX101_PRICE_POLL_SECONDS", "300")))
    last_hour = None
    last_rfbc = 0.0
    price_failures = 0
    warned_price_outage = False
    rfbc_every = max(60, int(os.getenv("FX101_RFBC_SCAN_SECONDS", "300")))
    mode = os.getenv("G_DESK_RUNTIME_MODE", "api").strip()
    fx101.db()
    fx101.log("worker_started", poll_seconds=poll, gdesk_mode=mode, price_provider="dukascopy_m1", gdesk_bridge=bool(GDESK_RUNTIME_URL))

    while RUNNING:
        try:
            changed = fx101.manage_prices(prices())
            for trade in changed:
                fx101.telegram_send(f"{trade['trade_id']} {trade['state']} at {trade['result_price']} ({trade.get('result_r')}R)")
            if price_failures:
                fx101.log("price_provider_recovered", previous_failures=price_failures)
                if warned_price_outage:
                    fx101.telegram_send("Fx101 price tracking recovered.")
            price_failures = 0
            warned_price_outage = False
        except Exception as exc:
            price_failures += 1
            fx101.log("price_provider_failure", provider="dukascopy_m1", error=type(exc).__name__, detail=str(exc)[:180], failures=price_failures)
            if price_failures == 3 and _open_trade_count() > 0:
                fx101.telegram_send("Fx101 price tracking is temporarily unavailable. Open-trade lifecycle monitoring may be delayed; retrying automatically.")
                warned_price_outage = True

        hour = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H")
        if hour != last_hour:
            last_hour = hour
            if mode == "chatgpt_subscription":
                try:
                    _emit_gdesk_context_snapshot(hour)
                    fx101.log("hourly_desk_scan_delegated", owner="chatgpt_subscription", scan_id=f"GDESK-{hour}")
                except Exception as exc:
                    fx101.log("gdesk_context_publish_failure", error=type(exc).__name__, detail=str(exc)[:180])
            else:
                try:
                    ok,status = fx101.request_desk_analysis()
                    fx101.log("hourly_desk_scan", ok=ok,status=status)
                except Exception as exc:
                    fx101.log("hourly_desk_scan_failure", error=type(exc).__name__)

        if mode == "chatgpt_subscription":
            try:
                _consume_gdesk_runtime_decision()
            except Exception as exc:
                fx101.log("gdesk_bridge_poll_failure", error=type(exc).__name__, detail=str(exc)[:180])

        if time.monotonic() - last_rfbc >= rfbc_every:
            try:
                scan_rfbc()
            except Exception as exc:
                fx101.log("rfbc_scan_failure", error=type(exc).__name__, detail=str(exc)[:180])
            last_rfbc = time.monotonic()

        time.sleep(poll)

    fx101.log("worker_stopped")


if __name__ == "__main__":
    main()
