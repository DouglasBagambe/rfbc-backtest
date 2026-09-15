"""Production state repair and broker-order lifecycle support.

No broker orders are sent here. Telegram PLACED means the user confirms a
market/pending order exists in MT5; Dukascopy prices then track its lifecycle.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

import fx101
import fx101_worker

# --- Existing manual-position repair -------------------------------------------------

def _ensure_manual_open(trade_id, symbol, side, entry, stop, target, volume, risk_pct, valid_until, note):
    c = fx101.db()
    if c.execute("SELECT 1 FROM trades WHERE id=?", (trade_id,)).fetchone():
        return
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
    context = json.dumps({"manual_backfill": True, "user_confirmed_placed": True, "source": "ChatGPT conversation", "order_type": side})
    c.execute("""INSERT INTO trades VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",(
        trade_id,"G_DESK",symbol,side,"OPEN",stamp,stamp,stamp,None,entry,None,stop,target,volume,risk_pct,valid_until,
        "Broker position was already placed manually; manage by SL/TP.","MANUAL","manual tracking repair",None,None,None,
        "Existing broker position",note,context,entry,None,None,None))
    c.execute("INSERT INTO trade_accounts VALUES (?,?,?)",(trade_id,account["id"],"manual_user_confirmed"))
    c.execute("INSERT INTO transition_events VALUES (?,?,?,?,?,?,?)",(str(uuid.uuid4()),trade_id,None,"OPEN",entry,"manual_user_confirmed_backfill",stamp))
    c.commit()
    fx101.log("manual_trade_tracking_repaired", trade_id=trade_id, reused_existing=False)

_ensure_manual_open("MANUAL-GBPUSD-20260915-A","GBPUSDc","SELL",1.34875,1.34975,1.34675,0.01,0.5,"2026-09-15T07:15:00Z","First GBPUSD SELL placed before Telegram trade tracking was repaired.")
_ensure_manual_open("MANUAL-GBPUSD-20260915-B","GBPUSDc","SELL",1.34870,1.35020,1.34600,0.01,0.5,"2026-09-15T10:15:00Z","Second GBPUSD SELL placed before Telegram trade tracking was repaired.")

# --- Order types --------------------------------------------------------------------
ORDER_TYPES = {"BUY","SELL","BUY_LIMIT","SELL_LIMIT","BUY_STOP","SELL_STOP","BUY_STOP_LIMIT","SELL_STOP_LIMIT"}
_base_persist = fx101.persist_decision


def _persist_decision(decision):
    d = dict(decision)
    order_type = str(d.get("order_type") or d.get("side") or "").upper().replace(" ", "_")
    if order_type not in ORDER_TYPES:
        return False, "invalid_order_type", {"trade_id": fx101.trade_id(d), "errors": ["invalid_order_type"]}
    side = "BUY" if order_type.startswith("BUY") else "SELL"
    if str(d.get("side") or side).upper() != side:
        return False, "order_type_side_mismatch", {"trade_id": fx101.trade_id(d), "errors": ["order_type_side_mismatch"]}
    d["side"] = side
    context = dict(d.get("context") or {})
    context["order_type"] = order_type
    if order_type.endswith("STOP_LIMIT"):
        trigger = d.get("stop_trigger") or context.get("stop_trigger")
        try:
            trigger = float(trigger)
            if trigger <= 0:
                raise ValueError
        except (TypeError, ValueError):
            return False, "missing_stop_trigger", {"trade_id": fx101.trade_id(d), "errors": ["missing_stop_trigger"]}
        context["stop_trigger"] = trigger
    d["context"] = context
    return _base_persist(d)

fx101.persist_decision = _persist_decision


def _order_type(trade):
    return str((trade.get("context") or {}).get("order_type") or trade.get("side") or "").upper()


def _compact_card(trade):
    order_type = _order_type(trade).replace("_", " ")
    zone = f"{trade['entry']}-{trade['entry_high']}" if trade.get("entry_high") else str(trade["entry"])
    account = trade.get("account_name") or "Exness Cent"
    reasoning = " ".join(str(trade.get("reasoning") or "").split())
    if reasoning:
        reasoning = reasoning.split(". ",1)[0].rstrip(".") + "."
        if len(reasoning) > 120: reasoning = reasoning[:117].rstrip() + "..."
    lines = [
        f"G DESK • {trade['symbol']} • {order_type}", "",
        f"Entry: {zone}",
    ]
    if _order_type(trade).endswith("STOP_LIMIT"):
        lines.append(f"Stop trigger: {(trade.get('context') or {}).get('stop_trigger')}")
    lines += [
        f"SL: {trade['stop']}", f"TP: {trade['target']}", f"Volume: {trade['volume']}",
        f"Risk: {trade['risk_pct']}%", f"Account: {account}", f"Valid until: {fx101.eat(trade['valid_until'])}", "",
        f"Cancel: {trade['cancel_condition']}", f"Chart: {fx101.chart_link(trade['symbol'])}"
    ]
    if reasoning: lines += ["", reasoning]
    return "\n".join(lines)

fx101.card = _compact_card

# --- Correct R accounting ------------------------------------------------------------
# Core v2 originally inverted SELL R. Correct all historical closed executions that
# have a result price, and use the corrected formula for future transitions.
_base_transition = fx101.transition


def _transition(tid, state, price=None, reason=None):
    result = _base_transition(tid, state, price, reason)
    if state in {"WON","LOST","MANUAL_CLOSE"} and price is not None:
        denom = abs(float(result["entry"]) - float(result["stop"]))
        r = 0.0 if denom == 0 else (float(price) - float(result["entry"])) / denom * (1.0 if result["side"] == "BUY" else -1.0)
        c = fx101.db(); c.execute("UPDATE trades SET result_r=? WHERE id=?",(r,tid)); c.commit()
        result = fx101.list_trades("WHERE id=?",(tid,))[0]
    return result

fx101.transition = _transition

try:
    c = fx101.db()
    for t in fx101.list_trades("WHERE state IN ('WON','LOST','MANUAL_CLOSE') AND result_price IS NOT NULL"):
        denom = abs(float(t["entry"]) - float(t["stop"]))
        r = 0.0 if denom == 0 else (float(t["result_price"]) - float(t["entry"])) / denom * (1.0 if t["side"] == "BUY" else -1.0)
        c.execute("UPDATE trades SET result_r=? WHERE id=?",(r,t["id"]))
    c.commit()
    fx101.log("historical_r_recomputed")
except Exception as exc:
    fx101.log("historical_r_recompute_failed", error=type(exc).__name__)

# --- Pending-order-aware lifecycle ---------------------------------------------------
def _metadata_get(key):
    row = fx101.db().execute("SELECT value FROM app_metadata WHERE key=?",(key,)).fetchone()
    return row[0] if row else None


def _metadata_set(key, value):
    c = fx101.db(); stamp = fx101.now()
    c.execute("INSERT OR REPLACE INTO app_metadata (key,value,updated_at) VALUES (?,?,?)",(key,str(value),stamp)); c.commit()


def _pending_filled(trade, price):
    ot = _order_type(trade)
    entry = float(trade["entry"])
    if ot in {"BUY","SELL"}: return True
    if ot == "BUY_LIMIT": return price <= entry
    if ot == "SELL_LIMIT": return price >= entry
    if ot == "BUY_STOP": return price >= entry
    if ot == "SELL_STOP": return price <= entry
    ctx = trade.get("context") or {}; trigger = float(ctx["stop_trigger"])
    key = f"pending_trigger:{trade['id']}"
    triggered = _metadata_get(key) == "1"
    if not triggered:
        if ot == "BUY_STOP_LIMIT" and price >= trigger: triggered = True
        elif ot == "SELL_STOP_LIMIT" and price <= trigger: triggered = True
        if triggered: _metadata_set(key,"1")
    if not triggered: return False
    return price <= entry if ot == "BUY_STOP_LIMIT" else price >= entry


def _manage_prices(prices):
    changed = []; now_utc = datetime.now(timezone.utc)
    for trade in fx101.list_trades("WHERE state IN ('PLACED','OPEN')"):
        price = prices.get(trade["symbol"])
        if price is None: continue
        price = float(price)
        if trade["state"] == "PLACED":
            try: expiry = datetime.fromisoformat(str(trade["valid_until"]).replace("Z","+00:00")).astimezone(timezone.utc)
            except Exception: expiry = None
            if expiry and now_utc >= expiry:
                changed.append(fx101.transition(trade["id"],"EXPIRED",price,"pending_order_valid_until")); continue
            if not _pending_filled(trade,price):
                c=fx101.db(); c.execute("UPDATE trades SET last_price=? WHERE id=?",(price,trade["id"])); c.commit(); continue
            trade = fx101.transition(trade["id"],"OPEN",price,"market_or_pending_entry_triggered")
        if trade["side"] == "BUY": outcome = "LOST" if price <= trade["stop"] else "WON" if price >= trade["target"] else None
        else: outcome = "LOST" if price >= trade["stop"] else "WON" if price <= trade["target"] else None
        if outcome: changed.append(fx101.transition(trade["id"],outcome,price,f"{outcome.lower()}_price_hit"))
        else:
            c=fx101.db(); c.execute("UPDATE trades SET last_price=? WHERE id=?",(price,trade["id"])); c.commit()
    return changed

fx101.manage_prices = _manage_prices

# --- MT5 screenshot reconciliation (2026-09-15 14:19 EAT) --------------------------
def _reconcile_mt5_snapshot():
    c = fx101.db(); stamp = fx101.now()
    account = next((a for a in fx101.list_accounts() if a["status"] == "active"),None)
    if account:
        # Standard Cent screen: 996.19 USC balance = USD 9.9619; equity 993.55 USC = USD 9.9355.
        if _metadata_get("mt5_snapshot_20260915_1419") != "done":
            old = float(account["tracked_balance"])
            c.execute("UPDATE accounts SET tracked_balance=?, tracked_equity=?, updated_at=? WHERE id=?",(9.9619,9.9355,stamp,account["id"]))
            c.execute("INSERT INTO reconciliation_records VALUES (?,?,?,?,?,?,?)",(str(uuid.uuid4()),account["id"],9.9619,old,9.9619-old,"MT5 screenshot 15 Sep 2026 14:19 EAT; 996.19 USC balance / 993.55 USC equity",stamp))
            _metadata_set("mt5_snapshot_20260915_1419","done")

    def latest(symbol, stop=None):
        if stop is None: return c.execute("SELECT id FROM trades WHERE symbol=? ORDER BY created_at DESC LIMIT 1",(symbol,)).fetchone()
        return c.execute("SELECT id FROM trades WHERE symbol=? AND ABS(stop-?)<1e-6 ORDER BY created_at DESC LIMIT 1",(symbol,stop)).fetchone()

    # Closed broker executions shown in History.
    for symbol, actual_entry, stop in [("XAUUSDc",4273.696,4281.200),("CADJPYc",111.318,111.245)]:
        r = latest(symbol,stop)
        if r:
            tid = r[0]
            c.execute("UPDATE trades SET state='LOST', entry=?, result_price=?, result_r=-1.0, closed_at=COALESCE(closed_at,?), last_price=?, result_reason=? WHERE id=?",(actual_entry,stop,stamp,stop,"MT5 screenshot: broker stop-loss hit",tid))

    # Exact current broker entry for the unique USDCAD position.
    r = latest("USDCADc")
    if r: c.execute("UPDATE trades SET entry=? WHERE id=? AND state IN ('PLACED','OPEN')",(1.39176,r[0]))

    # Two open GBPUSD sells; map MT5 display order to the two tracked positions.
    gbp = c.execute("SELECT id FROM trades WHERE symbol='GBPUSDc' AND side='SELL' AND state IN ('PLACED','OPEN') ORDER BY created_at ASC LIMIT 2").fetchall()
    for row_, actual_entry in zip(gbp,[1.34697,1.34759]): c.execute("UPDATE trades SET entry=? WHERE id=?",(actual_entry,row_[0]))
    c.commit()
    fx101.log("mt5_snapshot_reconciled", balance_usd=9.9619, equity_usd=9.9355, open_expected=["GBPUSDc","GBPUSDc","USDCADc"], closed_repaired=["XAUUSDc","CADJPYc"])

try:
    _reconcile_mt5_snapshot()
except Exception as exc:
    fx101.log("mt5_snapshot_reconcile_failed", error=type(exc).__name__, detail=str(exc)[:160])

# --- Lightweight active-position M1 polling -----------------------------------------
def _active_trade_prices():
    import pandas as pd
    active = fx101.list_trades("WHERE state IN ('PLACED','OPEN')")
    targets = sorted({t["symbol"] for t in active})
    if not targets:
        fx101.log("price_snapshot",provider="dukascopy_m1_active_only",symbols=0,latest=None); return {}
    now = pd.Timestamp.now(tz="UTC")
    start = now - (pd.Timedelta(hours=72) if now.weekday() >= 5 else pd.Timedelta(minutes=30))
    out={}; latest_ts=[]
    for symbol in targets:
        pair=symbol[:6]
        if pair not in fx101_worker.PAIR_TO_INSTRUMENT:
            fx101.log("active_price_symbol_unsupported",symbol=symbol); continue
        bid=fx101_worker._fetch_side(pair,"bid",start,now); ask=fx101_worker._fetch_side(pair,"ask",start,now)
        merged=bid[["dt","close"]].merge(ask[["dt","close"]],on="dt",how="inner",suffixes=("_bid","_ask"))
        if merged.empty: raise RuntimeError(f"no_aligned_dukascopy_m1:{pair}")
        row=merged.sort_values("dt").iloc[-1]; ts=pd.Timestamp(row["dt"])
        if now.weekday()<5 and now-ts>pd.Timedelta(minutes=20): raise RuntimeError(f"stale_dukascopy_m1:{pair}:{ts.isoformat()}")
        latest_ts.append(ts); out[symbol]=float((row["close_bid"]+row["close_ask"])/2)
    fx101.log("price_snapshot",provider="dukascopy_m1_active_only",symbols=len(out),latest=max(latest_ts).isoformat() if latest_ts else None)
    return out

fx101_worker.prices = _active_trade_prices
fx101.log("production_hotfix_loaded", lifecycle_polling="active_positions_only", order_types=sorted(ORDER_TYPES), mt5_reconciliation=True)
