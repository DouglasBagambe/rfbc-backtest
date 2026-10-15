"""User-facing dnb names. Protocol/source identifiers remain compatible."""
import os
import threading
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
import requests

NAMES = {"system":"dnb Fx", "desk":"dnb Desk", "risk":"dnb Risk", "ea":"dnb EA", "bot":"dnb Bot"}
REPLACEMENTS = (
    ("G'S FX 101","dnb Fx"), ("G’S FX 101","dnb Fx"), ("G’s Fx 101","dnb Fx"),
    ("G's Fx 101","dnb Fx"), ("G’s FX 101","dnb Fx"), ("G_DESK","dnb Desk"),
    ("G DESK","dnb Desk"), ("Fx101","dnb Fx"), ("FX101","dnb Fx"),
)

def text(value):
    for old, new in REPLACEMENTS:
        value = value.replace(old,new)
    return value

def markup(value):
    if isinstance(value,list): return [markup(v) for v in value]
    if isinstance(value,dict):
        return {k:(text(v).replace("🧭 Desk","🧭 dnb Desk") if k in {"text","input_field_placeholder"} and isinstance(v,str) else markup(v) if isinstance(v,(dict,list)) else v) for k,v in value.items()}
    return value

def next_scan():
    now=datetime.now(timezone.utc).astimezone(ZoneInfo("Africa/Kampala"))
    candidate=now.replace(minute=20,second=0,microsecond=0)
    if candidate<=now:candidate+=timedelta(hours=1)
    return candidate.strftime("%H:%M EAT")

def account_view():
    return "\n".join(["dnb Bot • Account","","GOAT Stride / Instant HERO","Initial account size: $2,500",
        "Current balance, exposure and lot size require a fresh broker snapshot.",
        "dnb EA is the source of broker state.","Execution: manual. Live AUTO unavailable."])

def desk_view():
    return "\n".join(["dnb Desk","","18 markets • Completed H1 BID/ASK bars",
        "Qualified setups, NO TRADE and system issues are reported.",
        "Risk input: at most 0.25%; actual lot size requires broker verification.",
        "Next scheduled scan: "+next_scan()])

def home_view():
    return "\n".join(["dnb Bot","dnb Fx trading interface","","GOAT Stride / Instant HERO • $2,500 initial",
        "Analysis: dnb Desk • 18 markets","Controls: dnb Risk","Broker observer: dnb EA",
        "Next scheduled scan: "+next_scan(),"","Manual execution. Broker sizing must be verified."])

def health_view():
    try:
        response=requests.get("https://dnb-fx.onrender.com/health",timeout=8)
        response.raise_for_status()
        body=response.json()
        if not body.get("ok"):raise ValueError("unhealthy")
        states="\n".join(s["source"].replace("G_DESK","dnb Desk")+": "+s["status"] for s in body.get("sources",[]))
        return "dnb Fx • System status\n\nGateway: online\n"+states+"\nLive AUTO: unavailable\nNext scheduled scan: "+next_scan()
    except Exception:
        return "dnb Fx • System status\n\nGateway health could not be verified.\nLive execution remains unavailable."

def configure_bot():
    import fx101
    token=os.getenv("TELEGRAM_BOT_TOKEN","").strip()
    if not token:return
    values={
        "setMyName":{"name":NAMES["bot"]},
        "setMyDescription":{"description":"dnb Bot is the Telegram interface for dnb Fx: dnb Desk market analysis, trade alerts and dnb EA monitoring. Execution status and broker verification requirements are shown explicitly."},
        "setMyShortDescription":{"short_description":"dnb Fx • Analysis, alerts and MT5 monitoring."},
    }
    for method,payload in values.items():
        try:
            response=requests.post("https://api.telegram.org/bot"+token+"/"+method,json=payload,timeout=10)
            ok=response.ok and response.json().get("ok") is True
        except Exception:
            ok=False
        fx101.log("dnb_bot_branding",method=method,ok=ok)

def install():
    import fx101
    if getattr(fx101.telegram_send,"_dnb_brand",False):return
    original=fx101.telegram_send
    def send(message,keyboard=None):
        return original(text(message),markup(keyboard))
    send._dnb_brand=True
    fx101.telegram_send=send
    fx101.next_gdesk_scan_eat=next_scan
    fx101.home=home_view
    fx101.accounts_text=account_view
    # The existing bot webhook remains compatible with saved menu callbacks.
    import sys
    premium=sys.modules.get("premium_ux")
    if premium:
        premium._home=home_view
        premium._account_view=account_view
        premium._desk_view=desk_view
        premium._health_view=health_view
        base_receive=fx101.receive_update
        def receive(update):
            message=update.get("message",{})
            if message.get("text")=="🧭 dnb Desk":
                update={**update,"message":{**message,"text":"🧭 Desk"}}
            return base_receive(update)
        fx101.receive_update=receive
    threading.Thread(target=configure_bot,name="dnb-bot-branding",daemon=True).start()
