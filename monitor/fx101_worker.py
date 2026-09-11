#!/usr/bin/env python3
"""Always-on non-MT5 price and scheduled G_DESK worker."""
from __future__ import annotations
import json, logging, os, signal, sys, time
from datetime import datetime, timezone
import requests
import fx101

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

def main() -> None:
    poll=max(10,int(os.getenv("FX101_PRICE_POLL_SECONDS","30"))); last_hour=None; failures=0
    fx101.db(); fx101.log("worker_started", poll_seconds=poll)
    while RUNNING:
        try:
            changed=fx101.manage_prices(prices())
            for trade in changed: fx101.telegram_send(f"{trade['trade_id']} {trade['state']} at {trade['result_price']} ({trade.get('result_r')}R)")
            hour=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H")
            if hour != last_hour:
                last_hour=hour; ok,status=fx101.request_desk_analysis(); fx101.log("hourly_desk_scan", ok=ok,status=status)
            failures=0
        except Exception as exc:
            failures+=1; fx101.log("worker_failure", error=type(exc).__name__, detail=str(exc), failures=failures)
            if failures in (1,5,20): fx101.telegram_send(f"Fx101 worker warning: {type(exc).__name__}; retrying safely.")
        time.sleep(poll)
    fx101.log("worker_stopped")
if __name__ == "__main__": main()
