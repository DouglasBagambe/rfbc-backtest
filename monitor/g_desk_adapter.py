#!/usr/bin/env python3
"""G_DESK live-analysis adapter. It never synthesizes a trade locally."""
from __future__ import annotations

import json, os, time
from datetime import datetime, timedelta, timezone

import pandas as pd
import requests
import dukascopy_python
from dukascopy_python import instruments
from flask import Flask, jsonify, request

app = Flask(__name__)

# Keep Twelve Data available to the wider Fx101 worker for lightweight quote
# polling, but G_DESK OHLC context no longer depends on Twelve Data credits.
PAIR_TO_DUKASCOPY = {
    "EURUSD": instruments.INSTRUMENT_FX_MAJORS_EUR_USD,
    "GBPUSD": instruments.INSTRUMENT_FX_MAJORS_GBP_USD,
    "GBPJPY": instruments.INSTRUMENT_FX_CROSSES_GBP_JPY,
    "USDCAD": instruments.INSTRUMENT_FX_MAJORS_USD_CAD,
    "EURJPY": instruments.INSTRUMENT_FX_CROSSES_EUR_JPY,
}
_DUKA_CACHE: dict[str, tuple[float, list[dict]]] = {}
_DUKA_CACHE_SECONDS = 300

DECISION_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["decisions"],
    "properties": {
        "decisions": {
            "type": "array",
            "maxItems": 1,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["symbol","side","entry","stop","target","volume","risk_pct","valid_until","cancel_condition","confidence","setup_name","regime","session","news_proximity","exposure_note","reasoning","context"],
                "properties": {
                    "symbol":{"type":"string","enum":["EURUSDc","GBPUSDc","GBPJPYc","USDCADc","EURJPYc"]},
                    "side":{"type":"string","enum":["BUY","SELL"]},
                    "entry":{"type":"number"},"stop":{"type":"number"},"target":{"type":"number"},
                    "volume":{"type":"number","minimum":0.01},"risk_pct":{"type":"number","minimum":0.01,"maximum":1},
                    "valid_until":{"type":"string"},"cancel_condition":{"type":"string"},
                    "confidence":{"type":"string"},"setup_name":{"type":"string"},"regime":{"type":"string"},
                    "session":{"type":"string"},"news_proximity":{"type":"string"},
                    "exposure_note":{"type":"string"},"reasoning":{"type":"string"},
                    "context":{"type":"object","additionalProperties":True}
                }
            }
        }
    }
}

def _secret_ok() -> bool:
    expected=os.getenv("G_DESK_ADAPTER_TOKEN","").strip()
    return bool(expected) and request.headers.get("X-G-Desk-Token","") == expected


def _normalise_duka_frame(frame) -> pd.DataFrame:
    if frame is None or frame.empty:
        return pd.DataFrame(columns=["dt","open","high","low","close","volume"])
    out=frame.reset_index()
    out=out.rename(columns={out.columns[0]:"dt"})
    out["dt"]=pd.to_datetime(out["dt"],utc=True,errors="coerce")
    for col in ("open","high","low","close","volume"):
        if col in out.columns:
            out[col]=pd.to_numeric(out[col],errors="coerce")
    out=out.dropna(subset=["dt","open","high","low","close"])
    if "volume" in out.columns:
        # Zero-volume padding is not tradable market data and must not enter
        # the live analysis context.
        out=out[out["volume"].fillna(0)>0]
    return out.sort_values("dt").drop_duplicates("dt")


def _fetch_duka_side(pair: str, side: str, start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    inst=PAIR_TO_DUKASCOPY[pair]
    offer=dukascopy_python.OFFER_SIDE_BID if side=="bid" else dukascopy_python.OFFER_SIDE_ASK
    last_exc=None
    for attempt in range(1,4):
        try:
            frame=dukascopy_python.fetch(
                instrument=inst,
                interval=dukascopy_python.INTERVAL_HOUR_1,
                offer_side=offer,
                start=start.to_pydatetime().replace(tzinfo=None),
                end=end.to_pydatetime().replace(tzinfo=None),
                max_retries=3,
                debug=False,
            )
            out=_normalise_duka_frame(frame)
            if out.empty:
                raise RuntimeError(f"empty_dukascopy_data:{pair}:{side}")
            return out
        except Exception as exc:
            last_exc=exc
            if attempt<3:
                time.sleep(attempt)
    raise RuntimeError(f"dukascopy_fetch_failed:{pair}:{side}:{type(last_exc).__name__}")


def _dukascopy_context(symbols: list[str]) -> dict:
    """Return recent completed H1 BID/ASK context without a paid market-data quota.

    Dukascopy is already the repository's independent FX data source. We fetch
    both sides, align timestamps strictly, exclude zero-volume padding/current
    incomplete H1, and expose mid OHLC plus the contemporaneous BID/ASK close.
    """
    now=pd.Timestamp.now(tz="UTC")
    cutoff=now.floor("h")
    # 96h covers the weekend while still keeping live requests small. We retain
    # only the latest 24 completed tradable H1 bars.
    start=cutoff-pd.Timedelta(hours=96)
    result={}
    for symbol in symbols:
        pair=symbol[:6]
        if pair not in PAIR_TO_DUKASCOPY:
            raise ValueError(f"unsupported_g_desk_symbol:{symbol}")
        cached=_DUKA_CACHE.get(symbol)
        if cached and time.time()-cached[0] < _DUKA_CACHE_SECONDS:
            result[symbol]=cached[1]
            continue

        bid=_fetch_duka_side(pair,"bid",start,cutoff)
        ask=_fetch_duka_side(pair,"ask",start,cutoff)
        merged=bid[["dt","open","high","low","close"]].merge(
            ask[["dt","open","high","low","close"]],on="dt",how="inner",suffixes=("_bid","_ask")
        )
        merged=merged[merged["dt"]<cutoff].sort_values("dt").tail(24)
        if len(merged)<12:
            raise RuntimeError(f"insufficient_live_data:{pair}:{len(merged)}")

        latest=pd.Timestamp(merged.iloc[-1]["dt"])
        # During a normal weekday session, context older than 3 completed hours
        # is an infrastructure/data failure, not a NO_TRADE decision.
        if cutoff.weekday()<5 and (cutoff-latest)>pd.Timedelta(hours=3):
            raise RuntimeError(f"stale_dukascopy_data:{pair}:{latest.isoformat()}")

        bars=[]
        for _,row in merged.iterrows():
            bars.append({
                "datetime":pd.Timestamp(row["dt"]).isoformat(),
                "open":float((row["open_bid"]+row["open_ask"])/2),
                "high":float((row["high_bid"]+row["high_ask"])/2),
                "low":float((row["low_bid"]+row["low_ask"])/2),
                "close":float((row["close_bid"]+row["close_ask"])/2),
                "bid_close":float(row["close_bid"]),
                "ask_close":float(row["close_ask"]),
                "spread":float(row["close_ask"]-row["close_bid"]),
            })
        _DUKA_CACHE[symbol]=(time.time(),bars)
        result[symbol]=bars
    return result


def _decision(symbols: list[str], requested_at: str, context: dict) -> dict:
    key=os.getenv("OPENAI_API_KEY","").strip()
    if not key: raise RuntimeError("OPENAI_API_KEY is required")
    model=os.getenv("G_DESK_MODEL","gpt-5-mini")
    valid_until=(datetime.now(timezone.utc)+timedelta(hours=2)).isoformat()
    instructions=(
        "You are G_DESK, a conservative discretionary forex analysis desk. "
        "Use only the supplied completed Dukascopy H1 BID/ASK market context. Return a qualified trade only when a clear setup is presently actionable; otherwise return decisions: []. "
        "Never invent missing market, spread, news, or account information. If news context is unavailable, state that rather than guessing. "
        "At most one decision. If trading, geometry must be valid: BUY stop < entry < target; SELL target < entry < stop. "
        "Set volume conservatively to 0.01 and risk_pct <= 0.5. valid_until must be no later than "+valid_until+". "
        "This is analysis and alerting only, never execution."
    )
    payload={
        "model":model,
        "instructions":instructions,
        "input":json.dumps({"requested_at":requested_at,"symbols":symbols,"ohlc_1h":context,"market_data_source":"Dukascopy BID/ASK"},separators=(",",":")),
        "text":{"format":{"type":"json_schema","name":"g_desk_decision","strict":True,"schema":DECISION_SCHEMA}}
    }
    r=requests.post("https://api.openai.com/v1/responses",headers={"Authorization":f"Bearer {key}","Content-Type":"application/json"},json=payload,timeout=75)
    r.raise_for_status(); response=r.json()
    output=response.get("output_text")
    if not output: raise RuntimeError("openai_empty_output")
    return json.loads(output)


def analyze_payload(body: dict) -> dict:
    """Execute the real live-data/OpenAI analysis path for an internal or HTTP caller."""
    symbols=body.get("symbols")
    if not isinstance(symbols,list) or not symbols: raise ValueError("symbols_required")
    context=_dukascopy_context(symbols)
    return _decision(symbols,str(body.get("requested_at") or datetime.now(timezone.utc).isoformat()),context)

@app.get("/health")
def health():
    return jsonify({
        "ok":True,
        "service":"g-desk-adapter",
        "openai_configured":bool(os.getenv("OPENAI_API_KEY")),
        "market_context_provider":"dukascopy",
        "twelve_data_configured":bool(os.getenv("TWELVE_DATA_API_KEY")),
    })

@app.post("/analyze")
def analyze():
    if not _secret_ok(): return jsonify({"ok":False,"error":"unauthorized"}),401
    body=request.get_json(silent=True) or {}
    try:
        return jsonify(analyze_payload(body))
    except requests.RequestException as exc:
        app.logger.exception("g_desk_provider_error")
        return jsonify({"ok":False,"error":f"provider_error:{type(exc).__name__}"}),502
    except (RuntimeError,ValueError,json.JSONDecodeError) as exc:
        app.logger.exception("g_desk_analysis_error")
        return jsonify({"ok":False,"error":str(exc)}),503

if __name__ == "__main__":
    app.run(host="0.0.0.0",port=int(os.getenv("PORT","10000")))
