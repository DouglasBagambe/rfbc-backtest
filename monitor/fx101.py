"""Persistent Fx 101 v2 Phase 1 operations layer; no broker execution."""
from __future__ import annotations

import hashlib, json, logging, os, sqlite3, uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

DESK_SYMBOLS = {"EURUSDc", "GBPUSDc", "GBPJPYc", "USDCADc", "EURJPYc"}
RFBC_SYMBOLS = {"USDJPYc", "AUDJPYc"}
ALL_SYMBOLS = DESK_SYMBOLS | RFBC_SYMBOLS
DB_PATH = Path(os.getenv("FX101_DB_PATH", "monitor/fx101.sqlite3"))
LOG = logging.getLogger("fx101")

SCHEMA = """
CREATE TABLE IF NOT EXISTS scans (id TEXT PRIMARY KEY, source TEXT NOT NULL, scanned_at TEXT NOT NULL, result TEXT NOT NULL, payload TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS trades (
 id TEXT PRIMARY KEY, source TEXT NOT NULL, symbol TEXT NOT NULL, side TEXT NOT NULL, state TEXT NOT NULL, created_at TEXT NOT NULL,
 placed_at TEXT, opened_at TEXT, closed_at TEXT, entry REAL NOT NULL, entry_high REAL, stop REAL NOT NULL, target REAL NOT NULL,
 volume REAL NOT NULL, risk_pct REAL NOT NULL, valid_until TEXT NOT NULL, cancel_condition TEXT NOT NULL, confidence TEXT NOT NULL,
 setup_name TEXT, regime TEXT, session TEXT, news_proximity TEXT, exposure_note TEXT, reasoning TEXT, context TEXT NOT NULL,
 last_price REAL, result_price REAL, result_r REAL, result_reason TEXT, UNIQUE(id));
CREATE TABLE IF NOT EXISTS updates (update_id TEXT PRIMARY KEY, received_at TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS trades_state_idx ON trades(state);
"""

def now() -> str: return datetime.now(timezone.utc).isoformat()
def log(event: str, **fields: Any) -> None: LOG.info(json.dumps({"event":event,"at":now(),**fields}, sort_keys=True))
def db() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True); c = sqlite3.connect(DB_PATH); c.row_factory = sqlite3.Row; c.executescript(SCHEMA); return c
def row(x: sqlite3.Row) -> dict[str, Any]:
    d=dict(x); d["context"]=json.loads(d["context"]); return d

def trade_id(decision: dict[str, Any]) -> str:
    supplied = str(decision.get("trade_id", "")).strip()
    if supplied: return supplied
    key = "|".join(str(decision.get(k,"")) for k in ("source","symbol","side","entry","stop","target","valid_until"))
    return f"FX-{hashlib.sha256(key.encode()).hexdigest()[:12].upper()}"

def risk_config() -> dict[str, float]:
    return {"max_total_risk_pct": float(os.getenv("FX101_MAX_TOTAL_RISK_PCT", "1.0")), "max_positions": int(os.getenv("FX101_MAX_POSITIONS", "1")), "daily_loss_lock_r": float(os.getenv("FX101_DAILY_LOSS_LOCK_R", "-2")), "weekly_loss_lock_r": float(os.getenv("FX101_WEEKLY_LOSS_LOCK_R", "-4")), "stale_seconds": int(os.getenv("FX101_STALE_SECONDS", "120"))}

def validate(decision: dict[str, Any]) -> list[str]:
    errors=[]; source=decision.get("source"); symbol=decision.get("symbol"); side=decision.get("side")
    if source not in {"RFBC","G_DESK"}: errors.append("invalid_source")
    if symbol not in ALL_SYMBOLS or (source == "G_DESK" and symbol not in DESK_SYMBOLS): errors.append("invalid_symbol_for_source")
    if side not in {"BUY","SELL"}: errors.append("invalid_side")
    for k in ("entry","stop","target","volume","risk_pct"):
        try:
            if float(decision[k]) <= 0: raise ValueError
        except (KeyError, TypeError, ValueError): errors.append(f"invalid_{k}")
    try:
        entry,stop,target=float(decision["entry"]),float(decision["stop"]),float(decision["target"])
        if side == "BUY" and not(stop < entry < target): errors.append("invalid_sltp_geometry")
        if side == "SELL" and not(target < entry < stop): errors.append("invalid_sltp_geometry")
    except (KeyError, TypeError, ValueError): pass
    if not decision.get("valid_until") or not decision.get("cancel_condition"): errors.append("missing_validity_or_cancellation")
    return errors

def correlated(a: str, b: str) -> bool:
    return bool(set(a[:3]+a[3:]) & set(b[:3]+b[3:]))

def portfolio_gate(d: dict[str, Any]) -> list[str]:
    cfg=risk_config(); c=db(); opens=[row(x) for x in c.execute("SELECT * FROM trades WHERE state IN ('PLACED','OPEN')")]
    errors=[]
    if len(opens) >= cfg["max_positions"]: errors.append("position_limit")
    total=sum(float(x["risk_pct"]) for x in opens)+float(d["risk_pct"])
    if total > cfg["max_total_risk_pct"]: errors.append("portfolio_risk_limit")
    if any(correlated(d["symbol"], x["symbol"]) for x in opens): errors.append("correlated_exposure")
    return errors

def persist_decision(d: dict[str, Any]) -> tuple[bool, str, dict[str, Any]]:
    errors=validate(d)
    if not errors: errors=portfolio_gate(d)
    tid=trade_id(d); c=db(); existing=c.execute("SELECT * FROM trades WHERE id=?", (tid,)).fetchone()
    if existing: return True, "idempotent_existing", row(existing)
    if errors: return False, ",".join(errors), {"trade_id": tid, "errors": errors}
    data={**d, "trade_id":tid}; context=d.get("context", {})
    c.execute("""INSERT INTO trades VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", (tid,d["source"],d["symbol"],d["side"],"SIGNALLED",now(),None,None,None,float(d["entry"]),d.get("entry_high"),float(d["stop"]),float(d["target"]),float(d["volume"]),float(d["risk_pct"]),d["valid_until"],d["cancel_condition"],d.get("confidence","UNSPECIFIED"),d.get("setup_name"),d.get("regime"),d.get("session"),d.get("news_proximity"),d.get("exposure_note"),d.get("reasoning"),json.dumps(context),None,None,None,None)); c.commit()
    return True,"signalled",data

def transition(tid: str, state: str, price: float|None=None, reason: str|None=None) -> dict[str, Any]:
    allowed={"SIGNALLED":{"PLACED","SKIPPED","CANCELLED"},"PLACED":{"OPEN","CANCELLED","EXPIRED","MANUAL_CLOSE"},"OPEN":{"WON","LOST","CANCELLED","EXPIRED","MANUAL_CLOSE"}}
    c=db(); x=c.execute("SELECT * FROM trades WHERE id=?",(tid,)).fetchone()
    if not x: raise KeyError(tid)
    t=row(x)
    if state not in allowed.get(t["state"],set()): raise ValueError(f"invalid_transition:{t['state']}->{state}")
    stamp=now(); updates={"state":state,"last_price":price,"result_reason":reason}
    if state=="PLACED": updates["placed_at"]=stamp
    if state=="OPEN": updates["opened_at"]=stamp
    if state in {"WON","LOST","CANCELLED","EXPIRED","MANUAL_CLOSE"}:
        updates["closed_at"]=stamp; updates["result_price"]=price
        if price is not None: updates["result_r"]=(price-t["entry"])/(t["entry"]-t["stop"]) * (1 if t["side"]=="BUY" else -1)
    sets=", ".join(f"{k}=?" for k in updates); c.execute(f"UPDATE trades SET {sets} WHERE id=?", (*updates.values(),tid)); c.commit(); return row(c.execute("SELECT * FROM trades WHERE id=?",(tid,)).fetchone())

def chart_link(symbol: str) -> str: return f"https://www.tradingview.com/chart/?symbol=FX%3A{symbol[:-1]}"
def card(t: dict[str, Any]) -> str:
    zone=f"{t['entry']}-{t['entry_high']}" if t.get("entry_high") else str(t["entry"])
    return "\n".join([f"{t['source']} | {t['trade_id']}",f"{t['symbol']} {t['side']} | entry {zone}",f"SL {t['stop']} | TP {t['target']} | vol {t['volume']} | risk {t['risk_pct']}%",f"Valid until: {t['valid_until']}",f"Cancel: {t['cancel_condition']}",f"{t.get('setup_name') or 'Setup'} | {t.get('regime') or 'regime n/a'} | {t.get('session') or 'session n/a'}",f"News: {t.get('news_proximity') or 'n/a'} | Exposure: {t.get('exposure_note') or 'n/a'}",f"Confidence: {t.get('confidence') or 'n/a'}",t.get("reasoning") or "No reasoning supplied.",f"Chart: {chart_link(t['symbol'])}"])

def telegram_send(text: str, keyboard: list[list[dict[str,str]]]|None=None) -> tuple[bool,str]:
    token=os.getenv("TELEGRAM_BOT_TOKEN",""); chat=os.getenv("TELEGRAM_CHAT_ID","")
    if not token or not chat: return False,"telegram_not_configured"
    payload={"chat_id":chat,"text":text,"disable_web_page_preview":True}
    if keyboard: payload["reply_markup"]={"inline_keyboard":keyboard}
    r=requests.post(f"https://api.telegram.org/bot{token}/sendMessage",json=payload,timeout=12); return r.ok, str(r.status_code)

def send_signal(t: dict[str, Any]) -> tuple[bool,str]: return telegram_send(card(t), [[{"text":"PLACED","callback_data":f"placed:{t['trade_id']}"},{"text":"SKIPPED","callback_data":f"skipped:{t['trade_id']}"}],[{"text":"WHY?","callback_data":f"why:{t['trade_id']}"},{"text":"CANCEL","callback_data":f"cancel:{t['trade_id']}"}]])

def request_desk_analysis() -> tuple[bool, str]:
    """Request analysis from the configured ChatGPT/G_DESK adapter, never emulate it."""
    url=os.getenv("G_DESK_ANALYZE_URL", "").strip()
    payload={"source":"G_DESK","symbols":sorted(DESK_SYMBOLS),"requested_at":now()}
    c=db(); c.execute("INSERT INTO scans VALUES (?,?,?,?,?)",(str(uuid.uuid4()),"G_DESK",payload["requested_at"],"REQUESTED",json.dumps(payload))); c.commit()
    if not url: return False,"g_desk_adapter_not_configured"
    try:
        token=os.getenv("G_DESK_ADAPTER_TOKEN", "").strip()
        headers={"X-G-Desk-Token": token} if token else {}
        r=requests.post(url,json=payload,headers=headers,timeout=30); log("desk_request", status=r.status_code)
        if not r.ok: return False, f"adapter_http_{r.status_code}"
        response=r.json() if r.content else {"decisions": []}
        ok, status, _ = ingest_desk_response(response)
        return ok, status
    except requests.RequestException as exc: return False,f"adapter_error:{type(exc).__name__}"

def ingest_desk_response(body: dict[str, Any]) -> tuple[bool, str, list[dict[str, Any]]]:
    """Validate the GPT adapter response and announce an explicit NO TRADE."""
    decisions=body.get("decisions", [])
    if not isinstance(decisions, list): return False,"adapter_decisions_must_be_list",[]
    accepted=[]; rejected=[]
    for decision in decisions:
        ok,status,trade=persist_decision({**decision,"source":"G_DESK"})
        if ok:
            accepted.append(trade)
            if status == "signalled": send_signal(trade)
        else: rejected.append(status)
    c=db(); result="TRADE" if accepted else "NO_TRADE" if not rejected else "REJECTED"
    c.execute("INSERT INTO scans VALUES (?,?,?,?,?)",(str(uuid.uuid4()),"G_DESK",now(),result,json.dumps(body))); c.commit()
    if not accepted and not rejected: telegram_send("G_DESK NO TRADE — no qualified setup across EURUSDc, GBPUSDc, GBPJPYc, USDCADc, EURJPYc.")
    log("desk_result", result=result, accepted=len(accepted), rejected=rejected)
    return not rejected,result,accepted

def list_trades(where: str="", args: tuple=()) -> list[dict[str,Any]]:
    c=db(); return [row(x) for x in c.execute("SELECT * FROM trades "+where,args)]

def manage_prices(prices: dict[str, float]) -> list[dict[str, Any]]:
    """Feed-neutral deterministic management; caller supplies fresh executable prices."""
    changed=[]; instant=datetime.now(timezone.utc)
    for t in list_trades("WHERE state IN ('PLACED','OPEN')"):
        price=prices.get(t["symbol"])
        if price is None: continue
        price=float(price)
        if t["state"] == "PLACED":
            t=transition(t["id"], "OPEN", price, "price_snapshot_open")
        if t["side"] == "BUY": outcome="LOST" if price <= t["stop"] else "WON" if price >= t["target"] else None
        else: outcome="LOST" if price >= t["stop"] else "WON" if price <= t["target"] else None
        if outcome: changed.append(transition(t["id"], outcome, price, f"{outcome.lower()}_price_hit"))
        elif instant >= datetime.fromisoformat(t["valid_until"].replace("Z","+00:00")): changed.append(transition(t["id"], "EXPIRED", price, "valid_until"))
        else:
            c=db(); c.execute("UPDATE trades SET last_price=? WHERE id=?",(price,t["id"])); c.commit()
    return changed

def receive_update(update: dict[str,Any]) -> str:
    uid=str(update.get("update_id","")); c=db()
    if not uid or c.execute("SELECT 1 FROM updates WHERE update_id=?",(uid,)).fetchone(): return "duplicate"
    c.execute("INSERT INTO updates VALUES (?,?)",(uid,now())); c.commit()
    cb=update.get("callback_query",{}); data=cb.get("data","")
    if data:
        action,tid=data.split(":",1); mapping={"placed":"PLACED","skipped":"SKIPPED","cancel":"CANCELLED"}
        if action=="why":
            t=list_trades("WHERE id=?",(tid,))[0]; telegram_send(t.get("reasoning") or "No reasoning snapshot."); return "why"
        transition(tid,mapping[action]); return action
    text=update.get("message",{}).get("text","").strip()
    if text.startswith("/open"): telegram_send("\n\n".join(card(t) for t in list_trades("WHERE state IN ('PLACED','OPEN')")) or "No open trades.")
    elif text.startswith("/today"):
        count = len(list_trades("WHERE created_at >= ?", (datetime.now(timezone.utc).date().isoformat(),)))
        telegram_send(f"Today: {count} signals.")
    elif text.startswith("/stats"): telegram_send("Stats: "+json.dumps({s:len(list_trades("WHERE state=?",(s,))) for s in ("WON","LOST","OPEN","SIGNALLED")}))
    elif text.startswith("/why "):
        t=list_trades("WHERE id=?",(text.split(maxsplit=1)[1],)); telegram_send(t[0].get("reasoning", "No reasoning") if t else "Unknown trade ID")
    elif text.startswith("/analyze"):
        ok,status=request_desk_analysis()
        telegram_send("G_DESK scan requested for EURUSDc, GBPUSDc, GBPJPYc, USDCADc, EURJPYc." if ok else f"NO TRADE: analysis adapter unavailable ({status}).")
    return "handled"
