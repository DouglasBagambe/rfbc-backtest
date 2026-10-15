"""dnb Desk context publisher colocated with the permanent gateway."""
import os
import threading
import uuid
from datetime import datetime, timezone
import fx101
import g_desk_adapter as adapter
from dukascopy_python import instruments
from mt5_symbols import DESK_PAIRS

def configure():
    mapping={}
    for pair in DESK_PAIRS:
        values={v for v in vars(instruments).values() if isinstance(v,str) and v.upper()==pair[:3]+"/"+pair[3:]}
        if len(values)==1:mapping[pair]=values.pop()
    if len(mapping)!=18:raise RuntimeError("dnb_context_universe_incomplete")
    adapter.PAIR_TO_DUKASCOPY.update(mapping)
    adapter.DESK_SYMBOLS[:]=[p+".x" for p in DESK_PAIRS]

def emit():
    payload=adapter.context_payload()
    if len(payload["symbols"])!=18:raise RuntimeError("dnb_context_universe_incomplete")
    scan_id="GDESK-"+datetime.now(timezone.utc).strftime("%Y-%m-%dT%H")+"-"+uuid.uuid4().hex[:10]
    for symbol in payload["symbols"]:
        fx101.log("gdesk_context_symbol",scan_id=scan_id,generated_at=payload["generated_at"],symbol=symbol,
            latest_completed_bar=payload["latest_completed_bar"][symbol],market_state=payload["market_state"],
            freshness=payload["freshness"],source=payload["source"],timeframe=payload["timeframe"],bars=payload["bars"][symbol])
    fx101.log("gdesk_context_ready",scan_id=scan_id,generated_at=payload["generated_at"],symbols=payload["symbols"],
        market_state=payload["market_state"],freshness=payload["freshness"],owner="chatgpt_subscription")
    return scan_id

def start():
    if os.getenv("DNB_PRODUCERS_ENABLED","0")!="1":return None
    configure()
    stop=threading.Event()
    def work():
        last_hour=None
        while not stop.is_set():
            hour=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H")
            if hour!=last_hour:
                try:
                    emit()
                    last_hour=hour
                except Exception as exc:
                    fx101.log("dnb_context_publish_failure",error=type(exc).__name__,detail=str(exc)[:180])
            stop.wait(60)
    threading.Thread(target=work,name="dnb-desk-context",daemon=True).start()
    return stop
