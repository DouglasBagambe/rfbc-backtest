"""Persistent Fx 101 v2 Phase 1 operations layer; no broker execution."""
from __future__ import annotations

import hashlib, json, logging, os, sqlite3, threading, uuid
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from pathlib import Path
from typing import Any

import requests

DESK_SYMBOLS = {"EURUSDc", "GBPUSDc", "GBPJPYc", "USDCADc", "EURJPYc"}
RFBC_SYMBOLS = {"USDJPYc", "AUDJPYc"}
ALL_SYMBOLS = DESK_SYMBOLS | RFBC_SYMBOLS
DB_PATH = Path(os.getenv("FX101_DB_PATH", "monitor/fx101.sqlite3"))
LOG = logging.getLogger("fx101")
_SCHEMA_LOCK = threading.Lock()
_SCHEMA_READY = False
_CONNECTION_LOCAL = threading.local()

SCHEMA = """
CREATE TABLE IF NOT EXISTS scans (id TEXT PRIMARY KEY, source TEXT NOT NULL, scanned_at TEXT NOT NULL, result TEXT NOT NULL, payload TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS trades (
 id TEXT PRIMARY KEY, source TEXT NOT NULL, symbol TEXT NOT NULL, side TEXT NOT NULL, state TEXT NOT NULL, created_at TEXT NOT NULL,
 placed_at TEXT, opened_at TEXT, closed_at TEXT, entry REAL NOT NULL, entry_high REAL, stop REAL NOT NULL, target REAL NOT NULL,
 volume REAL NOT NULL, risk_pct REAL NOT NULL, valid_until TEXT NOT NULL, cancel_condition TEXT NOT NULL, confidence TEXT NOT NULL,
 setup_name TEXT, regime TEXT, session TEXT, news_proximity TEXT, exposure_note TEXT, reasoning TEXT, context TEXT NOT NULL,
 last_price REAL, result_price REAL, result_r REAL, result_reason TEXT, UNIQUE(id));
CREATE TABLE IF NOT EXISTS updates (update_id TEXT PRIMARY KEY, received_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS accounts (
 id TEXT PRIMARY KEY, name TEXT NOT NULL UNIQUE, broker TEXT NOT NULL, account_type TEXT NOT NULL,
 base_currency TEXT NOT NULL, tracked_balance REAL NOT NULL, tracked_equity REAL,
 initial_balance REAL NOT NULL, high_water_mark REAL NOT NULL, status TEXT NOT NULL,
 is_default INTEGER NOT NULL DEFAULT 0, min_lot REAL, max_lot REAL, volume_step REAL,
 per_trade_risk_cap REAL NOT NULL, aggregate_risk_cap REAL NOT NULL, daily_loss_limit REAL,
 weekly_loss_limit REAL, max_drawdown REAL, max_positions INTEGER NOT NULL,
 allowed_symbols TEXT, prop_rules TEXT, notes TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS account_ledger (
 id TEXT PRIMARY KEY, account_id TEXT NOT NULL, event_type TEXT NOT NULL, amount REAL NOT NULL,
 note TEXT, created_at TEXT NOT NULL, FOREIGN KEY(account_id) REFERENCES accounts(id));
CREATE TABLE IF NOT EXISTS trade_accounts (trade_id TEXT PRIMARY KEY, account_id TEXT NOT NULL, selection_reason TEXT NOT NULL, FOREIGN KEY(trade_id) REFERENCES trades(id), FOREIGN KEY(account_id) REFERENCES accounts(id));
CREATE TABLE IF NOT EXISTS transition_events (id TEXT PRIMARY KEY, trade_id TEXT NOT NULL, from_state TEXT, to_state TEXT NOT NULL, price REAL, reason TEXT, occurred_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS reconciliation_records (id TEXT PRIMARY KEY, account_id TEXT NOT NULL, reported_balance REAL NOT NULL, computed_balance REAL NOT NULL, drift REAL NOT NULL, note TEXT, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS app_metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS trades_state_idx ON trades(state);
"""

class CompatRow(dict):
    """Row mapping that supports both named and positional access for sqlite/Turso parity."""
    def __init__(self, columns: list[str], values: Any):
        self._values = tuple(values)
        super().__init__(zip(columns, self._values))

    def __getitem__(self, key: Any) -> Any:
        if isinstance(key, int):
            return self._values[key]
        return super().__getitem__(key)


def _turso_row_factory(cursor: Any, values: Any) -> CompatRow:
    columns = [col[0] for col in (cursor.description or [])]
    return CompatRow(columns, values)


def now() -> str: return datetime.now(timezone.utc).isoformat()
def log(event: str, **fields: Any) -> None: LOG.info(json.dumps({"event":event,"at":now(),**fields}, sort_keys=True))
def db() -> sqlite3.Connection:
    """Open local SQLite for development or the shared Turso database in production."""
    existing=getattr(_CONNECTION_LOCAL,"connection",None)
    if existing is not None: return existing
    remote_url = (os.getenv("TURSO_DATABASE_URL") or os.getenv("TURSO_DB_URL") or "").strip()
    if remote_url:
        import turso_serverless
        c = turso_serverless.connect(remote_url, auth_token=os.environ["TURSO_AUTH_TOKEN"])
        c.row_factory = _turso_row_factory
    else:
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        c = sqlite3.connect(DB_PATH)
        c.row_factory = sqlite3.Row
    global _SCHEMA_READY
    if not _SCHEMA_READY:
        with _SCHEMA_LOCK:
            if not _SCHEMA_READY:
                try:
                    for statement in SCHEMA.split(";"):
                        if statement.strip(): c.execute(statement)
                    c.commit()
                    _SCHEMA_READY = True
                except Exception as exc:
                    if remote_url:
                        log("turso_db_unavailable", error=type(exc).__name__)
                    raise
    _CONNECTION_LOCAL.connection=c
    return c

def close_db() -> None:
    connection=getattr(_CONNECTION_LOCAL,"connection",None)
    if connection is not None:
        connection.close(); _CONNECTION_LOCAL.connection=None

def row(x: Any) -> dict[str, Any]:
    d=dict(x); d["context"]=json.loads(d["context"]); return d

def trade_id(decision: dict[str, Any]) -> str:
    supplied = str(decision.get("trade_id", "")).strip()
    if supplied: return supplied
    key = "|".join(str(decision.get(k,"")) for k in ("source","symbol","side","entry","stop","target","valid_until"))
    return f"FX-{hashlib.sha256(key.encode()).hexdigest()[:12].upper()}"

def risk_config() -> dict[str, float]:
    return {"max_total_risk_pct": float(os.getenv("FX101_MAX_TOTAL_RISK_PCT", "1.0")), "max_positions": int(os.getenv("FX101_MAX_POSITIONS", "1")), "daily_loss_lock_r": float(os.getenv("FX101_DAILY_LOSS_LOCK_R", "-2")), "weekly_loss_lock_r": float(os.getenv("FX101_WEEKLY_LOSS_LOCK_R", "-4")), "stale_seconds": int(os.getenv("FX101_STALE_SECONDS", "120"))}

def next_gdesk_scan_eat() -> str:
    instant=datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0) + __import__("datetime").timedelta(hours=1)
    return instant.astimezone(EAT).strftime("%H:%M EAT")

def queue_gdesk_analysis() -> str:
    request_id=f"GDESK-REQUEST-{uuid.uuid4().hex[:16]}"
    c=db(); c.execute("INSERT INTO scans VALUES (?,?,?,?,?)",(request_id,"G_DESK_REQUEST",now(),"QUEUED",json.dumps({"owner":"chatgpt_subscription"}))); c.commit()
    return request_id

def create_account(data: dict[str, Any]) -> dict[str, Any]:
    """Create only explicitly supplied tracked accounts; no broker balance is inferred."""
    required=("name","broker","account_type","base_currency","tracked_balance")
    if any(not str(data.get(k,"")) for k in required): raise ValueError("account_required_fields_missing")
    if data["account_type"] not in {"cent","standard","demo","paper","prop","other"}: raise ValueError("invalid_account_type")
    stamp=now(); aid=str(data.get("id") or uuid.uuid4()); balance=float(data["tracked_balance"]); c=db()
    is_default=1 if not c.execute("SELECT 1 FROM accounts WHERE is_default=1").fetchone() else 0
    c.execute("""INSERT INTO accounts (id,name,broker,account_type,base_currency,tracked_balance,tracked_equity,initial_balance,high_water_mark,status,is_default,min_lot,max_lot,volume_step,per_trade_risk_cap,aggregate_risk_cap,daily_loss_limit,weekly_loss_limit,max_drawdown,max_positions,allowed_symbols,prop_rules,notes,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",(aid,data["name"],data["broker"],data["account_type"],data["base_currency"],balance,data.get("tracked_equity"),balance,balance,"active",is_default,data.get("min_lot"),data.get("max_lot"),data.get("volume_step"),float(data.get("per_trade_risk_cap",.5)),float(data.get("aggregate_risk_cap",1.0)),data.get("daily_loss_limit"),data.get("weekly_loss_limit"),data.get("max_drawdown"),int(data.get("max_positions",1)),json.dumps(data.get("allowed_symbols",[])),json.dumps(data.get("prop_rules",{})),data.get("notes"),stamp,stamp)); c.commit(); return get_account(aid)

def get_account(account_id: str) -> dict[str, Any]:
    x=db().execute("SELECT * FROM accounts WHERE id=?",(account_id,)).fetchone()
    if not x: raise KeyError(account_id)
    d=dict(x); d["allowed_symbols"]=json.loads(d["allowed_symbols"] or "[]"); d["prop_rules"]=json.loads(d["prop_rules"] or "{}"); return d

def list_accounts() -> list[dict[str, Any]]:
    return [get_account(x["id"]) for x in db().execute("SELECT id FROM accounts ORDER BY is_default DESC, name")]

def select_account(decision: dict[str, Any]) -> tuple[dict[str, Any] | None, str]:
    accounts=[a for a in list_accounts() if a["status"]=="active" and (not a["allowed_symbols"] or decision["symbol"] in a["allowed_symbols"])]
    for a in accounts:
        open_count=db().execute("SELECT COUNT(*) FROM trade_accounts ta JOIN trades t ON t.id=ta.trade_id WHERE ta.account_id=? AND t.state IN ('PLACED','OPEN')",(a["id"],)).fetchone()[0]
        if open_count < a["max_positions"] and float(decision["risk_pct"]) <= float(a["per_trade_risk_cap"]): return a,"default_or_first_eligible"
    return None,"no_eligible_account"

def record_ledger(account_id: str, event_type: str, amount: float, note: str="") -> None:
    c=db(); c.execute("INSERT INTO account_ledger VALUES (?,?,?,?,?,?)",(str(uuid.uuid4()),account_id,event_type,float(amount),note,now())); c.commit()

def reconcile_account(account_id: str, reported_balance: float, note: str="") -> dict[str, Any]:
    a=get_account(account_id); computed=float(a["tracked_balance"]); drift=float(reported_balance)-computed; c=db(); c.execute("INSERT INTO reconciliation_records VALUES (?,?,?,?,?,?,?)",(str(uuid.uuid4()),account_id,float(reported_balance),computed,drift,note,now())); c.commit(); return {"account_id":account_id,"tracked_balance":computed,"reported_balance":float(reported_balance),"drift":drift}

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
    else:
        try:
            expiry=datetime.fromisoformat(str(decision["valid_until"]).replace("Z","+00:00")).astimezone(timezone.utc)
            age=(expiry-datetime.now(timezone.utc)).total_seconds()
            if age <= 0 or age > 24*3600: errors.append("invalid_valid_until")
        except ValueError: errors.append("invalid_valid_until")
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
    account, selection_reason = select_account(d) if not errors else (None, "invalid_decision")
    if not errors and not account: errors.append(selection_reason)
    if not errors: errors=portfolio_gate(d)
    tid=trade_id(d); c=db(); existing=c.execute("SELECT * FROM trades WHERE id=?", (tid,)).fetchone()
    if existing: return True, "idempotent_existing", row(existing)
    if errors: return False, ",".join(errors), {"trade_id": tid, "errors": errors}
    data={**d, "trade_id":tid}; context=d.get("context", {})
    stamp=now(); c.execute("""INSERT INTO trades VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", (tid,d["source"],d["symbol"],d["side"],"SIGNALLED",stamp,None,None,None,float(d["entry"]),d.get("entry_high"),float(d["stop"]),float(d["target"]),float(d["volume"]),float(d["risk_pct"]),d["valid_until"],d["cancel_condition"],d.get("confidence","UNSPECIFIED"),d.get("setup_name"),d.get("regime"),d.get("session"),d.get("news_proximity"),d.get("exposure_note"),d.get("reasoning"),json.dumps(context),None,None,None,None)); c.execute("INSERT INTO trade_accounts VALUES (?,?,?)",(tid,account["id"],selection_reason)); c.execute("INSERT INTO transition_events VALUES (?,?,?,?,?,?,?)",(str(uuid.uuid4()),tid,None,"SIGNALLED",None,"decision_ingested",stamp)); c.commit()
    data["account_name"]=account["name"]; return True,"signalled",data

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
    sets=", ".join(f"{k}=?" for k in updates); c.execute(f"UPDATE trades SET {sets} WHERE id=?", (*updates.values(),tid)); c.execute("INSERT INTO transition_events VALUES (?,?,?,?,?,?,?)",(str(uuid.uuid4()),tid,t["state"],state,price,reason,stamp)); c.commit(); return row(c.execute("SELECT * FROM trades WHERE id=?",(tid,)).fetchone())

def chart_link(symbol: str) -> str: return f"https://www.tradingview.com/chart/?symbol=FX%3A{symbol[:-1]}"
EAT=ZoneInfo("Africa/Kampala")
def eat(value: str | None) -> str:
    if not value: return "—"
    return datetime.fromisoformat(value.replace("Z","+00:00")).astimezone(EAT).strftime("%d %b %H:%M EAT")
def card(t: dict[str, Any]) -> str:
    zone=f"{t['entry']}-{t['entry_high']}" if t.get("entry_high") else str(t["entry"])
    account=t.get("account_name") or "Account pending"
    return "\n".join([f"{t['source']} • {t['symbol']} • {t['side']}",f"Trade ID: {t['trade_id']}",f"\nENTRY\n{zone}\n\nSTOP\n{t['stop']}\n\nTARGET\n{t['target']}",f"Risk: {t['risk_pct']}%  •  Volume: {t['volume']}",f"Valid until: {eat(t['valid_until'])}\nAccount: {account}",f"Setup: {t.get('setup_name') or '—'}\nRegime: {t.get('regime') or '—'}  •  Session: {t.get('session') or '—'}",f"News: {t.get('news_proximity') or 'Unknown'}\nExposure: {t.get('exposure_note') or '—'}",f"Why: {t.get('reasoning') or 'Stored reasoning unavailable.'}",f"Cancel if: {t['cancel_condition']}",f"Chart: {chart_link(t['symbol'])}"])

def telegram_send(text: str, keyboard: list[list[dict[str,str]]]|None=None) -> tuple[bool,str]:
    token=os.getenv("TELEGRAM_BOT_TOKEN",""); chat=os.getenv("TELEGRAM_CHAT_ID","")
    if not token or not chat: return False,"telegram_not_configured"
    payload={"chat_id":chat,"text":text,"disable_web_page_preview":True}
    if keyboard: payload["reply_markup"]={"inline_keyboard":keyboard}
    r=requests.post(f"https://api.telegram.org/bot{token}/sendMessage",json=payload,timeout=12); return r.ok, str(r.status_code)

def telegram_callback_ack(callback_id: str, text: str) -> None:
    token=os.getenv("TELEGRAM_BOT_TOKEN","")
    if token and callback_id: requests.post(f"https://api.telegram.org/bot{token}/answerCallbackQuery",json={"callback_query_id":callback_id,"text":text[:180]},timeout=8)

def home() -> str:
    return "G’s Fx 101\n\nTrading desk online\n\nG DESK • RFBC • Market Data • Journal\n\nAnalyze Now  |  Open Trades\nToday  |  Stats\nG Desk  |  RFBC\nAccounts  |  Health\nHelp"
def home_keyboard() -> list[list[dict[str,str]]]:
    return [[{"text":"Analyze Now","callback_data":"menu:analyze"},{"text":"Open Trades","callback_data":"menu:open"}],[{"text":"Today","callback_data":"menu:today"},{"text":"Stats","callback_data":"menu:stats"}],[{"text":"G Desk","callback_data":"menu:gdesk"},{"text":"RFBC","callback_data":"menu:rfbc"}],[{"text":"Accounts","callback_data":"menu:accounts"},{"text":"Health","callback_data":"menu:health"}],[{"text":"Help","callback_data":"menu:help"}]]

def stats_text() -> str:
    closed=list_trades("WHERE state IN ('WON','LOST','MANUAL_CLOSE')"); rs=[float(x['result_r']) for x in closed if x.get('result_r') is not None]
    wins=sum(1 for r in rs if r>0); losses=sum(1 for r in rs if r<0); total=len(rs); net=sum(rs)
    return "\n".join(["PERFORMANCE",f"Trades: {total}  •  Wins: {wins}  •  Losses: {losses}",f"Net R: {net:.2f}  •  Win rate: {(wins/total*100 if total else 0):.0f}%",f"Average R: {(net/total if total else 0):.2f}","Insufficient sample for reliable inference." if total<30 else "Tracked statistics only; not a prediction."])

def accounts_text() -> str:
    accounts=list_accounts()
    if not accounts: return "ACCOUNTS\n\nNo tracked account is configured. Add an account through the authenticated admin route before signals can be accepted. Tracked balance is not broker-live."
    return "\n\n".join(["ACCOUNTS"]+[f"{a['name']}\nTracked balance: {a['tracked_balance']} {a['base_currency']}\nStatus: {a['status'].title()}{' • Default' if a['is_default'] else ''}" for a in accounts])

def send_signal(t: dict[str, Any]) -> tuple[bool,str]: return telegram_send(card(t), [[{"text":"PLACED","callback_data":f"placed:{t['trade_id']}"},{"text":"SKIPPED","callback_data":f"skipped:{t['trade_id']}"}],[{"text":"WHY?","callback_data":f"why:{t['trade_id']}"},{"text":"CANCEL","callback_data":f"cancel:{t['trade_id']}"}]])

def register_telegram_webhook(webhook_url: str) -> tuple[bool, str]:
    """Register Telegram webhook with optional secret-token validation."""
    token=os.getenv("TELEGRAM_BOT_TOKEN","").strip()
    if not token or not webhook_url: return False,"telegram_or_webhook_not_configured"
    payload={"url":webhook_url,"allowed_updates":["message","callback_query"]}
    secret=os.getenv("TELEGRAM_WEBHOOK_SECRET","").strip()
    if secret: payload["secret_token"]=secret
    r=requests.post(f"https://api.telegram.org/bot{token}/setWebhook",json=payload,timeout=15)
    return r.ok,str(r.status_code)

def request_desk_analysis() -> tuple[bool, str]:
    """Legacy API-backed analysis path; subscription mode delegates to ChatGPT automation."""
    if os.getenv("G_DESK_RUNTIME_MODE","").strip()=="chatgpt_subscription":
        return False,"analysis_owned_by_chatgpt_subscription"
    url=os.getenv("G_DESK_ANALYZE_URL", "").strip()
    payload={"source":"G_DESK","symbols":sorted(DESK_SYMBOLS),"requested_at":now()}
    c=db(); c.execute("INSERT INTO scans VALUES (?,?,?,?,?)",(str(uuid.uuid4()),"G_DESK",payload["requested_at"],"REQUESTED",json.dumps(payload))); c.commit()
    if not url: return False,"g_desk_adapter_not_configured"
    try:
        if url == "internal://gdesk":
            from g_desk_adapter import analyze_payload
            response=analyze_payload(payload)
            log("desk_request", status="internal")
        else:
            token=os.getenv("G_DESK_ADAPTER_TOKEN", "").strip()
            headers={"X-G-Desk-Token": token} if token else {}
            r=requests.post(url,json=payload,headers=headers,timeout=30); log("desk_request", status=r.status_code)
            if not r.ok: return False, f"adapter_http_{r.status_code}"
            response=r.json() if r.content else {"decisions": []}
        ok, status, _ = ingest_desk_response(response)
        return ok, status
    except requests.HTTPError as exc:
        response=exc.response
        status=response.status_code if response is not None else "unknown"
        body=(response.text if response is not None else "")[:500].replace("\n"," ").replace("\r"," ")
        log("desk_provider_http_error", provider="legacy_ai_adapter", http_status=status, response_body=body)
        return False,f"adapter_http_{status}"
    except requests.RequestException as exc: return False,f"adapter_error:{type(exc).__name__}"

def ingest_desk_response(body: dict[str, Any]) -> tuple[bool, str, list[dict[str, Any]]]:
    """Validate externally produced G_DESK decisions and announce explicit NO TRADE."""
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
        if action=="menu":
            telegram_callback_ack(cb.get("id",""),"Opening")
            return receive_update({"update_id":f"menu-{uid}","message":{"text":"/"+tid}})
        if action=="why":
            t=list_trades("WHERE id=?",(tid,))[0]; telegram_callback_ack(cb.get("id",""),"Stored reasoning"); telegram_send("WHY • "+tid+"\n\n"+(t.get("reasoning") or "No reasoning snapshot.")); return "why"
        if action not in mapping: telegram_callback_ack(cb.get("id",""),"Unknown action"); return "unknown_callback"
        try: transition(tid,mapping[action]); telegram_callback_ack(cb.get("id",""),f"Trade marked {mapping[action].lower()}.")
        except ValueError: telegram_callback_ack(cb.get("id",""),"Already processed.")
        return action
    text=update.get("message",{}).get("text","").strip()
    if text.startswith(("/start","/menu")): telegram_send(home(), home_keyboard())
    elif text.startswith("/open"): telegram_send("OPEN TRADES\n\n"+"\n\n".join(card(t) for t in list_trades("WHERE state IN ('PLACED','OPEN')")) if list_trades("WHERE state IN ('PLACED','OPEN')") else "OPEN TRADES\n\nNo open trades.")
    elif text.startswith("/today"):
        items=list_trades("WHERE created_at >= ?", (datetime.now(timezone.utc).date().isoformat(),)); closed=[x for x in items if x['state'] in ('WON','LOST')]; net=sum(float(x['result_r'] or 0) for x in closed)
        telegram_send(f"TODAY\n\nTrades: {len(items)}  •  Open: {sum(x['state'] in ('PLACED','OPEN') for x in items)}\nNet R: {net:.2f}\nG DESK: {sum(x['source']=='G_DESK' for x in items)}  •  RFBC: {sum(x['source']=='RFBC' for x in items)}")
    elif text.startswith("/stats"): telegram_send(stats_text())
    elif text.startswith("/accounts"): telegram_send(accounts_text())
    elif text.startswith("/help"): telegram_send("G DESK is interpreted by connected ChatGPT subscription automation. RFBC is frozen deterministic logic. Trades are always placed manually in MT5. PLACED starts tracking; it never sends a broker order. Tracked balances require manual reconciliation.")
    elif text.startswith("/history"):
        arg=text.split(maxsplit=1)[1].upper() if len(text.split(maxsplit=1))>1 else ""; items=list_trades("WHERE state NOT IN ('SIGNALLED') ORDER BY created_at DESC LIMIT 8"); items=[x for x in items if not arg or arg in (x['symbol'],x['source'],x['state'])]; telegram_send("HISTORY\n\n"+"\n".join(f"{x['symbol']} • {x['state']} • {x.get('result_r') if x.get('result_r') is not None else '—'}R" for x in items) if items else "HISTORY\n\nNo matching tracked trades.")
    elif text.startswith("/gdesk"): telegram_send("G DESK\n\nAnalysis owner: ChatGPT subscription automation\nMarket context: Dukascopy completed H1 BID/ASK\nExecution: Manual")
    elif text.startswith("/rfbc"): telegram_send("RFBC\n\nUSDJPYc • AUDJPYc\nFrozen RFBC v1.0 • Manual MT5 execution\nSTALE/NONE states remain quiet unless a meaningful issue occurs.")
    elif text.startswith("/health"): telegram_send("SYSTEM HEALTH\n\nAPI • Online\nDatabase • Checked on request\nTelegram • Configured status available to operator\nMarket Data • Dukascopy\nG DESK • ChatGPT subscription\nExecution • Manual")
    elif text.startswith("/version"): telegram_send("G’s Fx 101 • v2 production build\nManual execution only.")
    elif text.startswith("/why "):
        t=list_trades("WHERE id=?",(text.split(maxsplit=1)[1],)); telegram_send(t[0].get("reasoning", "No reasoning") if t else "Unknown trade ID")
    elif text.startswith("/analyze"):
        if os.getenv("G_DESK_RUNTIME_MODE","").strip()=="chatgpt_subscription":
            queue_gdesk_analysis()
            telegram_send(f"G DESK\n\nAnalysis queued.\n\nNext ChatGPT desk scan: {next_gdesk_scan_eat()}\nStatus: Waiting for G\n\nChatGPT subscription automation owns discretionary analysis; no paid API is used.")
        else:
            ok,status=request_desk_analysis()
            telegram_send("G_DESK scan requested for EURUSDc, GBPUSDc, GBPJPYc, USDCADc, EURJPYc." if ok else f"G_DESK SYSTEM ERROR: analysis adapter unavailable ({status}).")
    return "handled"
