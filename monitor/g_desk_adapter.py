#!/usr/bin/env python3
"""G_DESK live-analysis adapter. It never synthesizes a trade locally."""
from __future__ import annotations

import json, os
from datetime import datetime, timedelta, timezone

import requests
from flask import Flask, jsonify, request

app = Flask(__name__)
TD = "https://api.twelvedata.com"

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

def _td_context(symbols: list[str]) -> dict:
    """Fetch all desk pairs in one Twelve Data request to stay within the free rate limit."""
    key=os.getenv("TWELVE_DATA_API_KEY","").strip()
    if not key: raise RuntimeError("TWELVE_DATA_API_KEY is required")
    pairs=[f"{symbol[:3]}/{symbol[3:6]}" for symbol in symbols]
    r=requests.get(f"{TD}/time_series",params={"symbol":",".join(pairs),"interval":"1h","outputsize":60,"apikey":key},timeout=25)
    r.raise_for_status(); data=r.json()
    result={}
    for symbol,pair in zip(symbols,pairs):
        payload=data if len(symbols)==1 else data.get(pair,{})
        values=payload.get("values") if isinstance(payload,dict) else None
        if not isinstance(values,list) or len(values)<60: raise RuntimeError(f"insufficient_live_data:{pair}")
        result[symbol]=[{"datetime":x["datetime"],"open":float(x["open"]),"high":float(x["high"]),"low":float(x["low"]),"close":float(x["close"])} for x in values[:120]]
    return result

def _decision(symbols: list[str], requested_at: str, context: dict) -> dict:
    key=os.getenv("OPENAI_API_KEY","").strip()
    if not key: raise RuntimeError("OPENAI_API_KEY is required")
    model=os.getenv("G_DESK_MODEL","gpt-5-mini")
    valid_until=(datetime.now(timezone.utc)+timedelta(hours=2)).isoformat()
    instructions=(
        "You are G_DESK, a conservative discretionary forex analysis desk. "
        "Use only the supplied live OHLC context. Return a qualified trade only when a clear setup is presently actionable; otherwise return decisions: []. "
        "Never invent missing market, spread, news, or account information. "
        "At most one decision. If trading, geometry must be valid: BUY stop < entry < target; SELL target < entry < stop. "
        "Set volume conservatively to 0.01 and risk_pct <= 0.5. valid_until must be no later than "+valid_until+". "
        "This is analysis and alerting only, never execution."
    )
    payload={
        "model":model,
        "instructions":instructions,
        "input":json.dumps({"requested_at":requested_at,"symbols":symbols,"ohlc_1h":context},separators=(",",":")),
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
    context=_td_context(symbols)
    return _decision(symbols,str(body.get("requested_at") or datetime.now(timezone.utc).isoformat()),context)

@app.get("/health")
def health():
    return jsonify({"ok":True,"service":"g-desk-adapter","openai_configured":bool(os.getenv("OPENAI_API_KEY")),"twelve_data_configured":bool(os.getenv("TWELVE_DATA_API_KEY"))})

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
