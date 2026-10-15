#!/usr/bin/env python3
"""G_DESK live-analysis adapter and read-only market-context provider."""
from __future__ import annotations

import os, time, math
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

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
DESK_SYMBOLS = ["EURUSD.x","GBPUSD.x","GBPJPY.x","USDCAD.x","EURJPY.x"]
_DUKA_CACHE: dict[str, tuple[float, pd.Timestamp, list[dict]]] = {}
_DUKA_CACHE_SECONDS = 300


# Dukascopy settles at 17:00 New York time (DST aware).
# XAU/USD has a daily 17:00-18:00 NY break:
# https://www.dukascopy.com/swiss/english/forex/forex-trading-accounts/link/
def _is_trading_hour(symbol: str, stamp: pd.Timestamp) -> bool:
    local = pd.Timestamp(stamp).tz_convert("America/New_York")
    day, hour = local.weekday(), local.hour
    if day == 5 or (day == 4 and hour >= 17) or (day == 6 and hour < 17):
        return False
    if symbol[:6] == "XAUUSD" and hour == 17:
        return False
    return True


def _expected_latest(symbol: str, cutoff: pd.Timestamp) -> pd.Timestamp:
    stamp = cutoff - pd.Timedelta(hours=1)
    while not _is_trading_hour(symbol, stamp):
        stamp -= pd.Timedelta(hours=1)
    return stamp


def _validate_bars(symbol: str, bars: list[dict], cutoff: pd.Timestamp) -> None:
    if len(bars) < 15:
        raise RuntimeError(f"insufficient_live_data:{symbol}:{len(bars)}")
    previous = None
    for bar in bars:
        stamp = pd.Timestamp(bar["datetime"])
        if stamp.tzinfo is None or stamp != stamp.floor("h") or stamp >= cutoff:
            raise RuntimeError(f"invalid_bar_time:{symbol}:{stamp}")
        prices = [float(bar[k]) for k in ("open", "high", "low", "close", "bid_close", "ask_close", "spread")]
        if not all(math.isfinite(v) for v in prices) or min(prices[:6]) <= 0:
            raise RuntimeError(f"invalid_bar_prices:{symbol}:{stamp}")
        if bar["high"] < max(bar["open"], bar["close"]) or bar["low"] > min(bar["open"], bar["close"]) or bar["ask_close"] < bar["bid_close"] or bar["spread"] < 0:
            raise RuntimeError(f"invalid_bar_ohlc_or_spread:{symbol}:{stamp}")
        if previous is not None:
            if stamp <= previous:
                raise RuntimeError(f"duplicate_or_unordered_bar:{symbol}:{stamp}")
            missing = previous + pd.Timedelta(hours=1)
            while missing < stamp:
                if _is_trading_hour(symbol, missing):
                    raise RuntimeError(f"missing_trading_bar:{symbol}:{missing.isoformat()}")
                missing += pd.Timedelta(hours=1)
        previous = stamp
    expected = _expected_latest(symbol, cutoff)
    if previous != expected:
        raise RuntimeError(f"stale_dukascopy_data:{symbol}:latest={previous}:expected={expected.isoformat()}")


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
        if cached and cached[1] == cutoff and time.time()-cached[0] < _DUKA_CACHE_SECONDS and cached[2] and pd.Timestamp(cached[2][-1]["datetime"]) == _expected_latest(symbol, cutoff):
            _validate_bars(symbol, cached[2], cutoff)
            result[symbol]=cached[2]
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
        _validate_bars(symbol, bars, cutoff)
        _DUKA_CACHE[symbol]=(time.time(),cutoff,bars)
        result[symbol]=bars
    return result


def fx_weekend_closed(now):
    # FX reopens Sunday evening; UTC weekday alone mislabels that session.
    ny=now.astimezone(ZoneInfo('America/New_York'))
    return ny.weekday()==5 or ny.weekday()==4 and ny.hour>=17 or ny.weekday()==6 and ny.hour<17


def context_payload(symbols: list[str] | None = None) -> dict:
    """Public, read-only payload for ChatGPT-side G_DESK analysis."""
    requested=list(symbols or DESK_SYMBOLS)
    context=_dukascopy_context(requested)
    latest={s:(bars[-1]["datetime"] if bars else None) for s,bars in context.items()}
    now=datetime.now(timezone.utc)
    market_closed=not any(_is_trading_hour(s, pd.Timestamp(now).floor('h')) for s in requested)
    expected=pd.Timestamp(now).floor('h')-pd.Timedelta(hours=1)
    expected_by_symbol={s:_expected_latest(s,pd.Timestamp(now).floor('h')) for s in requested}
    stale=[symbol for symbol,stamp in latest.items() if stamp is None or pd.Timestamp(stamp)!=expected_by_symbol[symbol]]
    return {
        "ok":True,
        "source":"Dukascopy BID/ASK",
        "timeframe":"H1 completed bars",
        "generated_at":now.isoformat(),
        "symbols":requested,
        "latest_completed_bar":latest,
        "expected_latest_completed_bar":expected.isoformat(),
        "expected_latest_completed_bar_by_symbol":{s:t.isoformat() for s,t in expected_by_symbol.items()},
        "stale_symbols":stale if not market_closed else [],
        "bars":context,
        "market_state":"MARKET_CLOSED" if market_closed else "MARKET_OPEN",
        "freshness":"MARKET_CLOSED" if market_closed else "INCOMPLETE" if stale else "FRESH",
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
