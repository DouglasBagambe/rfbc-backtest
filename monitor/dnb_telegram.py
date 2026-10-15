"""dnb Bot: authenticated owner-only, read-only Telegram interface."""
import hashlib
import hmac
import os
import threading
import time
from datetime import datetime, timezone
from flask import Blueprint, jsonify, request
import requests
import fx101
import dnb_branding as brand

bp=Blueprint("dnb_telegram",__name__)
SCHEMA=("CREATE TABLE IF NOT EXISTS dnb_bot_updates (id TEXT PRIMARY KEY, received_at INTEGER NOT NULL)",)
MENU={"keyboard":[[{"text":"📈 Open Trades"},{"text":"📊 Today"}],[{"text":"🏆 Performance"},{"text":"💳 Account"}],[{"text":"🧭 dnb Desk"},{"text":"⋯ More"}]],"resize_keyboard":True,"is_persistent":True,"input_field_placeholder":"dnb Bot"}
ALIASES={"📈 Open Trades":"/open","📊 Today":"/today","🏆 Performance":"/stats","💳 Account":"/accounts","🧭 dnb Desk":"/gdesk","🧭 Desk":"/gdesk","⋯ More":"/more"}

def secret():
    token=os.getenv("TELEGRAM_BOT_TOKEN","")
    return hmac.new(token.encode(),b"dnb-fx-telegram-webhook",hashlib.sha256).hexdigest() if token else ""

def account():
    import mt5_bridge
    snap=mt5_bridge.latest_snapshot()
    if not snap or not snap["fresh"]:return brand.account_view()
    p=snap["payload"]
    return "\n".join(["dnb Bot • GOAT Stride / Instant HERO",f"Balance ${p['balance']:.2f} • Equity ${p['equity']:.2f}",
        f"Floating ${p['floating_pnl']:.2f} • Free margin ${p['free_margin']:.2f}",
        f"Positions {len(p['positions'])} • Pending {len(p['orders'])}","Fresh broker snapshot • Manual execution"])

def open_trades():
    import mt5_bridge
    snap=mt5_bridge.latest_snapshot()
    if not snap or not snap["fresh"]:return "dnb Bot • Open Trades\n\nFresh GOAT broker state is unavailable. Check MT5; signals are not evidence of open positions."
    p=snap["payload"]
    rows=p["positions"]+p["orders"]
    if not rows:return "dnb Bot • Open Trades\n\nNo open positions or pending orders in the fresh GOAT snapshot."
    return "dnb Bot • Broker positions and orders\n\n"+"\n".join(f"{r['symbol']} • {r['order_type']} • {r['volume']} lot\nEntry {r['entry']} • SL {r['sl']} • TP {r['tp']}" for r in rows)

def status():
    import dnb_sources
    states="\n".join(brand.text(s["source"])+": "+s["status"] for s in dnb_sources.status())
    return "dnb Fx • System status\n\nGateway: online\n"+states+"\nLive AUTO: unavailable\nNext scheduled scan: "+brand.next_scan()

def performance():
    import dnb_history
    history=dnb_history.latest()
    if not history:return "dnb Bot • Performance\n\nVerified GOAT trade history is unavailable. Sync broker history before performance can be calculated."
    return "dnb Bot • Broker history\n\nLast verified capture: "+datetime.fromtimestamp(history["captured_at"],timezone.utc).isoformat()+"\nUse reconciled MT5 history for realised performance."

def respond(command):
    import mt5_store
    if command.startswith(("/start","/menu")):return brand.home_view()
    if command.startswith("/accounts"):return account()
    if command.startswith("/open"):return open_trades()
    if command.startswith("/gdesk"):return brand.desk_view()
    if command.startswith("/health"):return status()
    if command.startswith(("/stats","/history")):return performance()
    if command.startswith("/today"):
        start=int(datetime.now(timezone.utc).replace(hour=0,minute=0,second=0,microsecond=0).timestamp())
        rows=list(mt5_store.db().execute("SELECT trade_id FROM dnb_alert_intents WHERE created_at>=? AND state='SENT'",(start,)))
        return f"dnb Bot • Today\n\nAnalysis alerts delivered: {len(rows)}\nBroker positions and PnL require fresh GOAT evidence."
    if command.startswith("/analyze"):return "dnb Desk\n\nNext scheduled analysis: "+brand.next_scan()+"\nThe free scanner runs through your ChatGPT subscription."
    if command.startswith("/more"):return "dnb Bot\n\n/history • Broker history\n/health • System status\n/why DECISION_ID • Setup reasoning"
    if command.startswith("/why "):
        identifier=command.split(maxsplit=1)[1][:128]
        row=mt5_store.db().execute("SELECT payload FROM dnb_alert_intents WHERE trade_id=?",(identifier,)).fetchone()
        if row:
            import json
            return "dnb Desk • Reasoning\n\n"+json.loads(row["payload"]).get("reasoning","No stored reasoning.")
        return "dnb Desk • Unknown decision ID."
    return "dnb Bot\n\nUse the menu below or /health for current system status."

@bp.post("/telegram/webhook")
def webhook():
    configured=secret()
    if not configured or not hmac.compare_digest(request.headers.get("X-Telegram-Bot-Api-Secret-Token",""),configured):
        return jsonify(ok=False,error="unauthorized"),403
    request.max_content_length=65536
    update=request.get_json(silent=True) or {}
    message=update.get("message") or (update.get("callback_query") or {}).get("message") or {}
    owner=os.getenv("TELEGRAM_CHAT_ID","")
    if not owner or str((message.get("chat") or {}).get("id"))!=owner:
        return jsonify(ok=False,error="wrong_chat"),403
    uid=update.get("update_id")
    if type(uid) is not int or uid<0:return jsonify(ok=False,error="invalid_update"),400
    import mt5_bridge,mt5_store
    mt5_bridge._ensure_schema()
    c=mt5_store.lock_account()
    if c.execute("SELECT id FROM dnb_bot_updates WHERE id=?",(str(uid),)).fetchone():
        c.commit()
        return jsonify(ok=True,status="duplicate")
    c.execute("INSERT INTO dnb_bot_updates VALUES (?,?)",(str(uid),int(time.time())))
    c.commit()
    command=ALIASES.get(str(message.get("text","")).strip(),str(message.get("text","")).strip())
    cb=update.get("callback_query") or {}
    if cb:
        fx101.telegram_callback_ack(cb.get("id",""),"Opened")
        data=str(cb.get("data",""))
        command={"/premium:health":"/health","premium:health":"/health","premium:history":"/history","premium:home":"/start"}.get(data,"/start")
    ok,detail=fx101.telegram_send(respond(command),MENU)
    fx101.log("dnb_bot_command",command=command.split(" ",1)[0][:30],delivered=ok)
    return jsonify(ok=True,delivered=ok)

def configure_webhook():
    token=os.getenv("TELEGRAM_BOT_TOKEN","").strip()
    if not token:return
    payload={"url":"https://dnb-fx.onrender.com/telegram/webhook","secret_token":secret(),"allowed_updates":["message","callback_query"]}
    for attempt in range(3):
        try:
            response=requests.post("https://api.telegram.org/bot"+token+"/setWebhook",json=payload,timeout=10)
            ok=response.ok and response.json().get("ok") is True
        except Exception:ok=False
        fx101.log("dnb_bot_webhook",ok=ok,attempt=attempt+1)
        if ok:return
        time.sleep(2)

def start():
    threading.Thread(target=configure_webhook,name="dnb-bot-webhook",daemon=True).start()
