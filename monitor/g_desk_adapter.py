#!/usr/bin/env python3
"""G_DESK live-analysis adapter and read-only market-context provider."""
from __future__ import annotations

import os, time
from datetime import datetime, timezone

import pandas as pd
import dukascopy_python
from dukascopy_python import instruments
from flask import Flask, jsonify, request

app = Flask(__name__)

# Twelve Data can remain available to the wider Fx101 worker for lightweight
# quote polling, but G_DESK OHLC context is sourced from Dukascopy for free.
PAIR_TO_DUKASCOPY = {
    "EURUSD": instruments.INSTRUMENT_FX_MAJORS_EUR_USD,
    "GBPUSD": instruments.INSTRUMENT_FX_MAJORS_GBP_USD,
    "GBPJPY": instruments.INSTRUMENT_FX_CROSSES_GBP_JPY,
    "USDCAD": instruments.INSTRUMENT_FX_MAJORS_USD_CAD,
    "EURJPY": instruments.INSTRUMENT_FX_CROSSES_EUR_JPY,
}
DESK_SYMBOLS = ["EURUSDc","GBPUSDc","GBPJPYc","USDCADc","EURJPYc"]
_DUKA_CACHE: dict[str, tuple[float, list[dict]]] = {}
_DUKA_CACHE_SECONDS = 300


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
    """Return recent completed H1 BID/ASK context from Dukascopy."""
    now=pd.Timestamp.now(tz="UTC")
    cutoff=now.floor("h")
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


def context_payload(symbols: list[str] | None = None) -> dict:
    """Public, read-only payload for ChatGPT-side G_DESK analysis."""
    requested=list(symbols or DESK_SYMBOLS)
    context=_dukascopy_context(requested)
    latest={s:(bars[-1]["datetime"] if bars else None) for s,bars in context.items()}
    market_closed=datetime.now(timezone.utc).weekday() >= 5
    return {
        "ok":True,
        "source":"Dukascopy BID/ASK",
        "timeframe":"H1 completed bars",
        "generated_at":datetime.now(timezone.utc).isoformat(),
        "symbols":requested,
        "latest_completed_bar":latest,
        "bars":context,
        "market_state":"MARKET_CLOSED" if market_closed else "MARKET_OPEN",
        "freshness":"MARKET_CLOSED" if market_closed else "FRESH",
        "analysis_owner":"ChatGPT subscription automation",
        "execution":"manual",
    }


@app.get("/health")
def health():
    return jsonify({
        "ok":True,
        "service":"g-desk-adapter",
        "market_context_provider":"dukascopy",
        "analysis_mode":"chatgpt_subscription",
        "openai_api_required":False,
    })

@app.get("/context")
def context():
    try:
        return jsonify(context_payload())
    except (RuntimeError,ValueError) as exc:
        return jsonify({"ok":False,"error":str(exc)}),503

if __name__ == "__main__":
    app.run(host="0.0.0.0",port=int(os.getenv("PORT","10000")))
