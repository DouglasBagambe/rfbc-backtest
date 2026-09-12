#!/usr/bin/env python3
"""Always-on non-MT5 lifecycle-price and RFBC worker."""
from __future__ import annotations
import logging, os, signal, time
from datetime import datetime, timezone

import pandas as pd
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


def stop(*_):
    global RUNNING
    RUNNING=False


signal.signal(signal.SIGTERM, stop)
signal.signal(signal.SIGINT, stop)


def _normalise(frame) -> pd.DataFrame:
    if frame is None or frame.empty:
        return pd.DataFrame(columns=["dt", "close", "volume"])
    out = frame.reset_index().rename(columns={frame.reset_index().columns[0]: "dt"})
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
    # On weekends/closed sessions retain the latest Friday quote for state display.
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
        action = item.get("action") or {"kind": "none"}
        kind = str(action.get("kind", "none")).upper()
        if kind in {"NONE", "OPEN_TRADE", "STALE"}:
            continue
        telegram.send_action({"action": kind, "symbol": item["symbol"], "checked_at": now.isoformat(), **action})
    fx101.log("rfbc_scan", checked_at=now.isoformat())


def _open_trade_count() -> int:
    try:
        return len(fx101.list_trades("WHERE state IN ('PLACED','OPEN')"))
    except Exception:
        return 0


def main() -> None:
    poll = max(10, int(os.getenv("FX101_PRICE_POLL_SECONDS", "300")))
    last_hour = None
    last_rfbc = 0.0
    price_failures = 0
    warned_price_outage = False
    rfbc_every = max(60, int(os.getenv("FX101_RFBC_SCAN_SECONDS", "300")))
    mode = os.getenv("G_DESK_RUNTIME_MODE", "api").strip()
    fx101.db()
    fx101.log("worker_started", poll_seconds=poll, gdesk_mode=mode, price_provider="dukascopy_m1")

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
                fx101.log("hourly_desk_scan_delegated", owner="chatgpt_subscription")
            else:
                try:
                    ok, status = fx101.request_desk_analysis()
                    fx101.log("hourly_desk_scan", ok=ok, status=status)
                except Exception as exc:
                    fx101.log("hourly_desk_scan_failure", error=type(exc).__name__)

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
