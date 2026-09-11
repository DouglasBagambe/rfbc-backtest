#!/usr/bin/env python3
"""Always-on non-MT5 price and scheduled G_DESK worker."""
from __future__ import annotations
import json, logging, os, signal, sys, time
from datetime import datetime, timezone
import requests
import fx101
import rfbc_monitor_live as rfbc
import telegram_notify as telegram

logging.basicConfig(level=os.getenv("LOG_LEVEL","INFO"), format="%(message)s")
RUNNING=True
def stop(*_):
    global RUNNING; RUNNING=False
signal.signal(signal.SIGTERM,stop); signal.signal(signal.SIGINT,stop)

def prices() -> dict[str,float]:
    key=os.getenv("TWELVE_DATA_API_KEY","").strip()
    if not key: raise RuntimeError("TWELVE_DATA_API_KEY is required for price worker")
    symbols=",".join(f"{s[0:3]}/{s[3:6]}" for s in sorted(fx101.ALL_SYMBOLS))
    r=requests.get("https://api.twelvedata.com/price",params={"symbol":symbols,"apikey":key},timeout=20); r.raise_for_status(); data=r.json()
    out={}
    for symbol in fx101.ALL_SYMBOLS:
        item=data.get(f"{symbol[:3]}/{symbol[3:6]}",{})
        if "price" in item: out[symbol]=float(item["price"])
    if not out: raise RuntimeError(f"price_provider_empty:{data}")
    return out

def scan_rfbc() -> None:
    """Run the frozen RFBC evaluator unchanged and alert only on actionable events."""
    now=datetime.now(timezone.utc)
    for item in rfbc.evaluate_all(now):
        action=item.get("action") or {"kind":"none"}
        kind=str(action.get("kind","none")).upper()
        if kind in {"NONE","OPEN_TRADE"}: continue
        telegram.send_action({"action":kind,"symbol":item["symbol"],"checked_at":now.isoformat(),**action})
    fx101.log("rfbc_scan", checked_at=now.isoformat())

def main() -> None:
    poll=max(10,int(os.getenv("FX101_PRICE_POLL_SECONDS","300"))); last_hour=None; last_rfbc=0.0; failures=0
    rfbc_every=max(60,int(os.getenv("FX101_RFBC_SCAN_SECONDS","300")))
    fx101.db(); fx101.log("worker_started", poll_seconds=poll)
    while RUNNING:
        try:
            changed=fx101.manage_prices(prices())
            for trade in changed: fx101.telegram_send(f"{trade['trade_id']} {trade['state']} at {trade['result_price']} ({trade.get('result_r')}R)")
            hour=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H")
            if hour != last_hour:
                last_hour=hour; ok,status=fx101.request_desk_analysis(); fx101.log("hourly_desk_scan", ok=ok,status=status)
            if time.monotonic()-last_rfbc >= rfbc_every:
                scan_rfbc(); last_rfbc=time.monotonic()
            failures=0
        except Exception as exc:
            failures+=1; fx101.log("worker_failure", error=type(exc).__name__, failures=failures)
            if failures in (1,5,20): fx101.telegram_send(f"Fx101 worker warning: {type(exc).__name__}; retrying safely.")
        time.sleep(poll)
    fx101.log("worker_stopped")
if __name__ == "__main__": main()
