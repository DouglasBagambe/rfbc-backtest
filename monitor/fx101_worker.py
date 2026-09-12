#!/usr/bin/env python3
"""Always-on non-MT5 price and RFBC worker."""
from __future__ import annotations
import logging, os, signal, time
from datetime import datetime, timezone
import requests
import fx101
import rfbc_monitor_live as rfbc
import telegram_notify as telegram

logging.basicConfig(level=os.getenv("LOG_LEVEL","INFO"), format="%(message)s")
RUNNING=True


def stop(*_):
    global RUNNING
    RUNNING=False


signal.signal(signal.SIGTERM,stop)
signal.signal(signal.SIGINT,stop)


def prices() -> dict[str,float]:
    key=os.getenv("TWELVE_DATA_API_KEY","").strip()
    if not key:
        raise RuntimeError("TWELVE_DATA_API_KEY is required for price worker")
    symbols=",".join(f"{s[0:3]}/{s[3:6]}" for s in sorted(fx101.ALL_SYMBOLS))
    r=requests.get("https://api.twelvedata.com/price",params={"symbol":symbols,"apikey":key},timeout=20)
    r.raise_for_status()
    data=r.json()
    out={}
    for symbol in fx101.ALL_SYMBOLS:
        item=data.get(f"{symbol[:3]}/{symbol[3:6]}",{})
        if "price" in item:
            out[symbol]=float(item["price"])
    if not out:
        raise RuntimeError(f"price_provider_empty:{data}")
    return out


def scan_rfbc() -> None:
    """Run frozen RFBC unchanged; push only genuinely actionable events."""
    now=datetime.now(timezone.utc)
    for item in rfbc.evaluate_all(now):
        action=item.get("action") or {"kind":"none"}
        kind=str(action.get("kind","none")).upper()
        # NONE/OPEN_TRADE/STALE are status states, not user actions. STALE is
        # especially expected over closed/weekend sessions and must not spam.
        if kind in {"NONE","OPEN_TRADE","STALE"}:
            continue
        telegram.send_action({"action":kind,"symbol":item["symbol"],"checked_at":now.isoformat(),**action})
    fx101.log("rfbc_scan", checked_at=now.isoformat())


def _open_trade_count() -> int:
    try:
        return len(fx101.list_trades("WHERE state IN ('PLACED','OPEN')"))
    except Exception:
        return 0


def main() -> None:
    poll=max(10,int(os.getenv("FX101_PRICE_POLL_SECONDS","300")))
    last_hour=None
    last_rfbc=0.0
    price_failures=0
    warned_price_outage=False
    rfbc_every=max(60,int(os.getenv("FX101_RFBC_SCAN_SECONDS","300")))
    mode=os.getenv("G_DESK_RUNTIME_MODE","api").strip()
    fx101.db()
    fx101.log("worker_started", poll_seconds=poll, gdesk_mode=mode)

    while RUNNING:
        # Lifecycle price polling is best-effort and isolated: a provider issue
        # must not block RFBC scans or generate repetitive Telegram noise.
        try:
            changed=fx101.manage_prices(prices())
            for trade in changed:
                fx101.telegram_send(f"{trade['trade_id']} {trade['state']} at {trade['result_price']} ({trade.get('result_r')}R)")
            if price_failures:
                fx101.log("price_provider_recovered", previous_failures=price_failures)
                if warned_price_outage:
                    fx101.telegram_send("Fx101 price tracking recovered.")
            price_failures=0
            warned_price_outage=False
        except Exception as exc:
            price_failures+=1
            fx101.log("price_provider_failure", error=type(exc).__name__, failures=price_failures)
            # Only alert once when live trade management is actually exposed.
            if price_failures == 3 and _open_trade_count() > 0:
                fx101.telegram_send("Fx101 price tracking is temporarily unavailable. Open-trade lifecycle monitoring may be delayed; retrying automatically.")
                warned_price_outage=True

        hour=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H")
        if hour != last_hour:
            last_hour=hour
            if mode == "chatgpt_subscription":
                fx101.log("hourly_desk_scan_delegated", owner="chatgpt_subscription")
            else:
                try:
                    ok,status=fx101.request_desk_analysis()
                    fx101.log("hourly_desk_scan", ok=ok,status=status)
                except Exception as exc:
                    fx101.log("hourly_desk_scan_failure", error=type(exc).__name__)

        if time.monotonic()-last_rfbc >= rfbc_every:
            try:
                scan_rfbc()
            except Exception as exc:
                fx101.log("rfbc_scan_failure", error=type(exc).__name__)
            last_rfbc=time.monotonic()

        time.sleep(poll)

    fx101.log("worker_stopped")


if __name__ == "__main__":
    main()
