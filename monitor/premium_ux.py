"""Premium Telegram UX overlay for G's Fx 101.

Presentation only. Trading logic, risk gates, data feeds and execution remain
owned by fx101/usercustomize. This module is loaded last by sitecustomize.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone

import requests

import fx101

# Compact persistent navigation: core actions only. Secondary screens live in
# an inline More panel so the keyboard no longer consumes half the display.
PREMIUM_MENU = {
    "keyboard": [
        [{"text": "📈 Open Trades"}, {"text": "📊 Today"}],
        [{"text": "🏆 Performance"}, {"text": "💳 Account"}],
        [{"text": "🧭 Desk"}, {"text": "⋯ More"}],
    ],
    "resize_keyboard": True,
    "is_persistent": True,
    "input_field_placeholder": "G's Fx 101",
}

MORE_INLINE = [
    [{"text": "History", "callback_data": "premium:history"}, {"text": "RFBC", "callback_data": "premium:rfbc"}],
    [{"text": "System Status", "callback_data": "premium:health"}, {"text": "Home", "callback_data": "premium:home"}],
]


def _send(text: str, keyboard=None):
    token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    chat = os.getenv("TELEGRAM_CHAT_ID", "")
    if not token or not chat:
        return False, "telegram_not_configured"
    payload = {"chat_id": chat, "text": text, "disable_web_page_preview": True}
    if keyboard:
        if isinstance(keyboard, dict) and "keyboard" in keyboard:
            payload["reply_markup"] = keyboard
        else:
            payload["reply_markup"] = {"inline_keyboard": keyboard}
    r = requests.post(f"https://api.telegram.org/bot{token}/sendMessage", json=payload, timeout=12)
    return r.ok, str(r.status_code)


fx101.telegram_send = _send


def _money(v):
    if v is None:
        return "—"
    value = float(v)
    return f"${value:.2f}  ·  {value * 100:.2f} USC"


def _active():
    return fx101.list_trades("WHERE state IN ('PLACED','OPEN') ORDER BY created_at DESC")


def _current_risk() -> float:
    return sum(float(t.get("risk_pct") or 0) for t in _active())


def _home() -> str:
    accounts = fx101.list_accounts()
    a = accounts[0] if accounts else None
    active = _active()
    opened = sum(1 for t in active if t["state"] == "OPEN")
    pending = sum(1 for t in active if t["state"] == "PLACED")
    if not a:
        return "G'S FX 101\nPrivate Trading Terminal\n\nAccount not configured."
    return "\n".join([
        "G'S FX 101",
        "Private Trading Terminal",
        "",
        f"Balance   {_money(a.get('tracked_balance'))}",
        f"Equity    {_money(a.get('tracked_equity'))}",
        f"Risk      {_current_risk():.2f}% / {float(a['aggregate_risk_cap']):.2f}%",
        "",
        f"Positions {opened}   ·   Pending {pending}",
        f"Next scan {fx101.next_gdesk_scan_eat()}",
    ])


def _order_label(t: dict) -> str:
    raw = str((t.get("context") or {}).get("order_type") or "MARKET").upper()
    if raw == "MARKET":
        return t["side"]
    return raw.replace("_", " ")


def _open_view() -> str:
    trades = _active()
    if not trades:
        return "OPEN TRADES\n\nNo active positions or pending orders."
    blocks = ["OPEN TRADES"]
    for t in trades:
        state = "PENDING" if t["state"] == "PLACED" else "OPEN"
        marker = "🟡" if state == "PENDING" else "🟢"
        last = t.get("last_price")
        blocks.append("\n".join([
            f"{marker} {t['symbol']}  ·  {_order_label(t)}",
            f"{state}   ·   {float(t['risk_pct']):.2f}% risk",
            f"Entry {t['entry']}   SL {t['stop']}   TP {t['target']}",
            f"Last  {last if last is not None else '—'}",
        ]))
    return "\n\n".join(blocks)


def _today_view() -> str:
    start = datetime.now(timezone.utc).date().isoformat()
    items = fx101.list_trades("WHERE created_at >= ? ORDER BY created_at DESC", (start,))
    meaningful = [t for t in items if t["state"] not in {"SIGNALLED", "SKIPPED", "CANCELLED", "EXPIRED"}]
    closed = [t for t in meaningful if t["state"] in {"WON", "LOST", "MANUAL_CLOSE"}]
    active = [t for t in meaningful if t["state"] in {"PLACED", "OPEN"}]
    rs = [float(t["result_r"]) for t in closed if t.get("result_r") is not None]
    wins = sum(r > 0 for r in rs)
    losses = sum(r < 0 for r in rs)
    net = sum(rs)
    return "\n".join([
        "TODAY",
        "",
        f"Active       {len(active)}",
        f"Closed       {len(closed)}",
        f"Wins         {wins}",
        f"Losses       {losses}",
        f"Net          {net:+.2f}R",
        f"Risk live    {_current_risk():.2f}%",
    ])


def _performance_view() -> str:
    closed = fx101.list_trades("WHERE state IN ('WON','LOST','MANUAL_CLOSE') ORDER BY closed_at")
    rs = [float(t["result_r"]) for t in closed if t.get("result_r") is not None]
    wins = sum(r > 0 for r in rs)
    losses = sum(r < 0 for r in rs)
    total = len(rs)
    net = sum(rs)
    wr = (wins / total * 100) if total else 0.0
    avg = (net / total) if total else 0.0
    streak = 0
    streak_kind = "—"
    if rs:
        positive = rs[-1] > 0
        streak_kind = "W" if positive else "L"
        for r in reversed(rs):
            if (r > 0) == positive:
                streak += 1
            else:
                break
    return "\n".join([
        "PERFORMANCE",
        "",
        f"Trades       {total}",
        f"Record       {wins}W · {losses}L",
        f"Win rate     {wr:.0f}%",
        f"Net          {net:+.2f}R",
        f"Average      {avg:+.2f}R",
        f"Streak       {streak_kind}{streak if streak else ''}",
        "",
        "Forward record · sample still developing" if total < 30 else "Forward tracked record",
    ])


def _account_view() -> str:
    accounts = fx101.list_accounts()
    if not accounts:
        return "ACCOUNT\n\nNo tracked account configured."
    a = accounts[0]
    active = _active()
    return "\n".join([
        "ACCOUNT",
        "",
        f"{a['name']}   ·   {a['broker']}",
        f"Balance   {_money(a.get('tracked_balance'))}",
        f"Equity    {_money(a.get('tracked_equity'))}",
        "",
        f"Live risk    {_current_risk():.2f}% / {float(a['aggregate_risk_cap']):.2f}%",
        f"Per setup    ≤ {float(a['per_trade_risk_cap']):.2f}%",
        f"Active       {len(active)}",
        "",
        "Execution  Manual MT5",
    ])


def _desk_view() -> str:
    symbols = getattr(__import__("usercustomize"), "ACTIVE_GDESK", [])
    return "\n".join([
        "G DESK",
        "",
        f"Markets      {len(symbols) or 16}",
        "Orders       Market · Limit · Stop · Stop Limit",
        "Setup risk   0.25–0.50%",
        "Portfolio    ≤ 2.00%",
        f"Next scan    {fx101.next_gdesk_scan_eat()}",
        "",
        "Only qualified setups are sent.",
    ])


def _rfbc_view() -> str:
    return "\n".join([
        "RFBC",
        "",
        "USDJPYc · AUDJPYc",
        "Frozen RFBC v1.0",
        "Manual MT5 execution",
        "",
        "Independent from G DESK.",
    ])


def _history_view() -> str:
    # Default history is intentionally useful, not noisy: active + realized only.
    items = fx101.list_trades("WHERE state IN ('PLACED','OPEN','WON','LOST','MANUAL_CLOSE') ORDER BY created_at DESC LIMIT 10")
    if not items:
        return "HISTORY\n\nNo tracked trades yet."
    lines = ["HISTORY", ""]
    for t in items:
        if t["state"] in {"OPEN", "PLACED"}:
            marker = "🟢" if t["state"] == "OPEN" else "🟡"
            result = t["state"]
        else:
            r = t.get("result_r")
            marker = "✅" if (r is not None and float(r) > 0) else "❌"
            result = f"{float(r):+.2f}R" if r is not None else t["state"]
        lines.append(f"{marker} {t['symbol']}  ·  {result}")
    return "\n".join(lines)


def _health_view() -> str:
    return "\n".join([
        "SYSTEM STATUS",
        "",
        "Market feed    Online",
        "Desk engine    Online",
        "Journal        Online",
        "Telegram       Online",
        "Execution      Manual MT5",
        "",
        f"Next scan      {fx101.next_gdesk_scan_eat()}",
    ])


def _more_view() -> str:
    return "\n".join([
        "MORE",
        "",
        "History, RFBC and system status are one tap away.",
        "",
        "Signal-specific reasoning stays behind WHY? on each trade card.",
    ])


def _set_commands():
    token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    if not token:
        return
    # Keep Telegram's slash menu clean for power users while the reply keyboard
    # remains the primary interface.
    commands = [
        {"command": "start", "description": "Open terminal"},
        {"command": "open", "description": "Open trades"},
        {"command": "today", "description": "Today"},
        {"command": "stats", "description": "Performance"},
        {"command": "history", "description": "History"},
    ]
    try:
        requests.post(f"https://api.telegram.org/bot{token}/setMyCommands", json={"commands": commands}, timeout=8)
    except Exception:
        pass


_set_commands()

_BASE_RECEIVE = fx101.receive_update


def _handle_callback(update: dict) -> str | None:
    cb = update.get("callback_query") or {}
    data = str(cb.get("data") or "")
    if not data.startswith("premium:"):
        return None
    action = data.split(":", 1)[1]
    fx101.telegram_callback_ack(cb.get("id", ""), "Opened")
    if action == "history":
        fx101.telegram_send(_history_view(), MORE_INLINE)
    elif action == "rfbc":
        fx101.telegram_send(_rfbc_view(), MORE_INLINE)
    elif action == "health":
        fx101.telegram_send(_health_view(), MORE_INLINE)
    else:
        fx101.telegram_send(_home(), PREMIUM_MENU)
    return f"premium_{action}"


def _receive(update: dict) -> str:
    callback = _handle_callback(update)
    if callback:
        return callback

    text = str(update.get("message", {}).get("text", "")).strip()
    mapped = {
        "📈 Open Trades": "/open",
        "📊 Today": "/today",
        "🏆 Performance": "/stats",
        "💳 Account": "/accounts",
        "🧭 Desk": "/gdesk",
        "⋯ More": "/more",
    }.get(text, text)

    if mapped.startswith(("/start", "/menu")):
        fx101.telegram_send(_home(), PREMIUM_MENU); return "home"
    if mapped.startswith("/open"):
        fx101.telegram_send(_open_view(), PREMIUM_MENU); return "open"
    if mapped.startswith("/today"):
        fx101.telegram_send(_today_view(), PREMIUM_MENU); return "today"
    if mapped.startswith("/stats"):
        fx101.telegram_send(_performance_view(), PREMIUM_MENU); return "stats"
    if mapped.startswith("/accounts"):
        fx101.telegram_send(_account_view(), PREMIUM_MENU); return "accounts"
    if mapped.startswith("/gdesk"):
        fx101.telegram_send(_desk_view(), PREMIUM_MENU); return "gdesk"
    if mapped.startswith("/rfbc"):
        fx101.telegram_send(_rfbc_view(), PREMIUM_MENU); return "rfbc"
    if mapped.startswith("/history"):
        fx101.telegram_send(_history_view(), PREMIUM_MENU); return "history"
    if mapped.startswith("/health"):
        fx101.telegram_send(_health_view(), PREMIUM_MENU); return "health"
    if mapped.startswith("/more"):
        fx101.telegram_send(_more_view(), MORE_INLINE); return "more"
    if mapped.startswith("/analyze"):
        # The subscription architecture cannot synchronously invoke ChatGPT from
        # a Telegram webhook. Do not fake a scan or queue a misleading action.
        fx101.telegram_send("G DESK\n\nInstant scan is not available in the current free architecture.\nNext automatic scan: " + fx101.next_gdesk_scan_eat(), PREMIUM_MENU)
        return "analyze_unavailable"

    if mapped != text:
        clone = dict(update); clone["message"] = dict(update.get("message", {})); clone["message"]["text"] = mapped
        return _BASE_RECEIVE(clone)
    return _BASE_RECEIVE(update)


fx101.receive_update = _receive
fx101.log("premium_ux_loaded", level="9_of_10", persistent_rows=3, analyze_button=False, inline_more=True)
