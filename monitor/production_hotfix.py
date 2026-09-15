"""One-time production state repair plus lightweight lifecycle polling.

This module does not place broker orders. It records the two GBPUSD positions
that the user explicitly confirmed were already placed manually, and limits
M1 lifecycle polling to positions that actually need tracking.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

import pandas as pd

import fx101
import fx101_worker


def _ensure_manual_open(
    trade_id: str,
    symbol: str,
    side: str,
    entry: float,
    stop: float,
    target: float,
    volume: float,
    risk_pct: float,
    valid_until: str,
    note: str,
) -> None:
    c = fx101.db()
    if c.execute("SELECT 1 FROM trades WHERE id=?", (trade_id,)).fetchone():
        return

    # Reuse an exact historical signal when present instead of duplicating it.
    existing = c.execute(
        "SELECT id,state FROM trades WHERE symbol=? AND side=? AND ABS(entry-?)<1e-9 AND ABS(stop-?)<1e-9 AND ABS(target-?)<1e-9 ORDER BY created_at DESC LIMIT 1",
        (symbol, side, entry, stop, target),
    ).fetchone()
    if existing:
        tid, state = existing[0], existing[1]
        try:
            if state == "SIGNALLED":
                fx101.transition(tid, "PLACED", entry, "user_confirmed_manual_placement")
                fx101.transition(tid, "OPEN", entry, "user_confirmed_manual_placement")
            elif state == "PLACED":
                fx101.transition(tid, "OPEN", entry, "user_confirmed_manual_placement")
        except ValueError:
            pass
        fx101.log("manual_trade_tracking_repaired", trade_id=tid, reused_existing=True)
        return

    account = next((a for a in fx101.list_accounts() if a["status"] == "active"), None)
    if not account:
        fx101.log("manual_trade_backfill_failed", trade_id=trade_id, reason="no_active_account")
        return

    stamp = fx101.now()
    context = json.dumps({
        "manual_backfill": True,
        "user_confirmed_placed": True,
        "source": "ChatGPT conversation",
    })
    c.execute(
        """INSERT INTO trades VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            trade_id, "G_DESK", symbol, side, "OPEN", stamp, stamp, stamp, None,
            entry, None, stop, target, volume, risk_pct, valid_until,
            "Broker position was already placed manually; manage by SL/TP.",
            "MANUAL", "manual tracking repair", None, None,
            "Existing broker position", note, context,
            entry, None, None, None,
        ),
    )
    c.execute("INSERT INTO trade_accounts VALUES (?,?,?)", (trade_id, account["id"], "manual_user_confirmed"))
    c.execute(
        "INSERT INTO transition_events VALUES (?,?,?,?,?,?,?)",
        (str(uuid.uuid4()), trade_id, None, "OPEN", entry, "manual_user_confirmed_backfill", stamp),
    )
    c.commit()
    fx101.log("manual_trade_tracking_repaired", trade_id=trade_id, reused_existing=False)


# The user explicitly confirmed both positions were already placed.
_ensure_manual_open(
    "MANUAL-GBPUSD-20260915-A",
    "GBPUSDc", "SELL", 1.34875, 1.34975, 1.34675, 0.01, 0.5,
    "2026-09-15T07:15:00Z",
    "First GBPUSD SELL placed before Telegram trade tracking was repaired.",
)
_ensure_manual_open(
    "MANUAL-GBPUSD-20260915-B",
    "GBPUSDc", "SELL", 1.34870, 1.35020, 1.34600, 0.01, 0.5,
    "2026-09-15T10:15:00Z",
    "Second GBPUSD SELL placed before Telegram trade tracking was repaired.",
)


def _active_trade_prices() -> dict[str, float]:
    """Fetch M1 prices only for PLACED/OPEN positions that need lifecycle tracking."""
    active = fx101.list_trades("WHERE state IN ('PLACED','OPEN')")
    targets = sorted({t["symbol"] for t in active})
    if not targets:
        fx101.log("price_snapshot", provider="dukascopy_m1_active_only", symbols=0, latest=None)
        return {}

    now = pd.Timestamp.now(tz="UTC")
    start = now - (pd.Timedelta(hours=72) if now.weekday() >= 5 else pd.Timedelta(minutes=30))
    out: dict[str, float] = {}
    latest_ts: list[pd.Timestamp] = []
    for symbol in targets:
        pair = symbol[:6]
        if pair not in fx101_worker.PAIR_TO_INSTRUMENT:
            fx101.log("active_price_symbol_unsupported", symbol=symbol)
            continue
        bid = fx101_worker._fetch_side(pair, "bid", start, now)
        ask = fx101_worker._fetch_side(pair, "ask", start, now)
        merged = bid[["dt", "close"]].merge(
            ask[["dt", "close"]], on="dt", how="inner", suffixes=("_bid", "_ask")
        )
        if merged.empty:
            raise RuntimeError(f"no_aligned_dukascopy_m1:{pair}")
        row = merged.sort_values("dt").iloc[-1]
        ts = pd.Timestamp(row["dt"])
        if now.weekday() < 5 and now - ts > pd.Timedelta(minutes=20):
            raise RuntimeError(f"stale_dukascopy_m1:{pair}:{ts.isoformat()}")
        latest_ts.append(ts)
        out[symbol] = float((row["close_bid"] + row["close_ask"]) / 2)

    fx101.log(
        "price_snapshot",
        provider="dukascopy_m1_active_only",
        symbols=len(out),
        latest=max(latest_ts).isoformat() if latest_ts else None,
    )
    return out


fx101_worker.prices = _active_trade_prices
fx101.log("production_hotfix_loaded", manual_positions=2, lifecycle_polling="active_positions_only")
