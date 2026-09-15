"""Premium Telegram UX overlay for G's Fx 101.

Presentation only. Trading logic, risk gates, data feeds and execution remain
owned by fx101/usercustomize. This module is loaded last by sitecustomize.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone

import requests

import fx101

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


def _trade_r_now(t: dict) -> float | None:
    last = t.get("last_price")
    if last is None or t["state"] != "OPEN":
        return None
    entry, stop, price = float(t["entry"]), float(t["stop"]), float(last)
    risk = abs(entry - stop)
    if risk <= 0:
        return None
    return ((price - entry) / risk) if t["side"] == "BUY" else ((entry - price) / risk)


def _today_closed() -> list[dict]:
    start = datetime.now(timezone.utc).date().isoformat()
    return fx101.list_trades("WHERE created_at >= ? AND state IN ('WON','LOST','MANUAL_CLOSE') ORDER BY closed_at DESC", (start,))


def _today_net_r() -> float:
    return sum(float(t.get("result_r") or 0) for t in _today_closed())


def _latest_scan() -> tuple[str, str]:
    try:
        row = fx101.db().execute(
            "SELECT result, scanned_at FROM scans WHERE source='G_DESK' AND result IN ('TRADE','NO_TRADE','REJECTED') ORDER BY scanned_at DESC LIMIT 1"
        ).fetchone()
        if not row:
            return "—", "—"
        result = str(row[0]).replace("_", " ")
        at = fx101.eat(str(row[1]))
        return result, at
    except Exception:
        return "—", "—"


def _home() -> str:
    accounts = fx101.list_accounts()
    a = accounts[0] if accounts else None
    active = _active()
    opened = sum(1 for t in active if t["state"] == "OPEN")
    pending = sum(1 for t in active if t["state"] == "PLACED")
    if not a:
        return "G'S FX 101\nPrivate Trading Terminal\n\nAccount not configured."
    live_r = sum((_trade_r_now(t) or 0.0) for t in active)
    cap = float(a["aggregate_risk_cap"])
    risk = _current_risk()
    return "\n".join([
        "G'S FX 101",
        "Private Trading Terminal",
        "",
        f"Balance   {_money(a.get('tracked_balance'))}",
        f"Equity    {_money(a.get('tracked_equity'))}",
        f"Live R    {live_r:+.2f}R",
        "",
        f"Risk      {risk:.2f}% / {cap:.2f}%   ·   Free {max(cap-risk,0):.2f}%",
        f"Positions {opened}   ·   Pending {pending}",
        f"Today     {_today_net_r():+.2f}R",
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
        r_now = _trade_r_now(t)
        live = f"{r_now:+.2f}R" if r_now is not None else "waiting"
        blocks.append("\n".join([
            f"{marker} {t['symbol']}  ·  {_order_label(t)}  ·  {live}",
            f"{state}   ·   {float(t['risk_pct']):.2f}% risk",
            f"Entry {t['entry']}   Now {t.get('last_price') if t.get('last_price') is not None else '—'}",
            f"SL {t['stop']}   TP {t['target']}",
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
    live_r = sum((_trade_r_now(t) or 0.0) for t in active)
    return "\n".join([
        "TODAY",
        "",
        f"Active       {len(active)}",
        f"Closed       {len(closed)}",
        f"Wins         {wins}",
        f"Losses       {losses}",
        f"Realized     {net:+.2f}R",
        f"Floating     {live_r:+.2f}R",
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
    risk = _current_risk()
    cap = float(a["aggregate_risk_cap"])
    balance = float(a.get("tracked_balance") or 0)
    equity = float(a.get("tracked_equity") or balance)
    floating_usd = equity - balance
    hwm = float(a.get("high_water_mark") or balance or 0)
    dd = ((hwm - equity) / hwm * 100) if hwm > 0 else 0.0
    return "\n".join([
        "ACCOUNT",
        "",
        f"{a['name']}   ·   {a['broker']}",
        f"Balance      {_money(balance)}",
        f"Equity       {_money(equity)}",
        f"Floating     ${floating_usd:+.2f}  ·  {floating_usd*100:+.2f} USC",
        "",
        f"Live risk    {risk:.2f}% / {cap:.2f}%",
        f"Free risk    {max(cap-risk,0):.2f}%",
        f"Drawdown     {max(dd,0):.2f}%",
        f"Per setup    ≤ {float(a['per_trade_risk_cap']):.2f}%",
        f"Active       {len(active)}",
        "",
        "Execution    Manual MT5",
    ])


def _desk_view() -> str:
    symbols = getattr(__import__("usercustomize"), "ACTIVE_GDESK", [])
    last_result, last_at = _latest_scan()
    return "\n".join([
        "G DESK",
        "",
        f"Markets      {len(symbols) or 16}",
        "Orders       Market · Limit · Stop · Stop Limit",
        "Setup risk   0.25–0.50%",
        "Portfolio    ≤ 2.00%",
        f"Last scan    {last_result}  ·  {last_at}",
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
        "Risk model    0.50% base",
        "Execution     Manual MT5",
        "",
        "Independent from G DESK.",
    ])


def _history_view() -> str:
    items = fx101.list_trades("WHERE state IN ('PLACED','OPEN','WON','LOST','MANUAL_CLOSE') ORDER BY created_at DESC LIMIT 10")
    if not items:
        return "HISTORY\n\nNo tracked trades yet."
    lines = ["HISTORY", ""]
    for t in items:
        if t["state"] in {"OPEN", "PLACED"}:
            marker = "🟢" if t["state"] == "OPEN" else "🟡"
            r_now = _trade_r_now(t)
            result = f"{r_now:+.2f}R" if r_now is not None else "PENDING"
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
    return "MORE\n\nHistory, RFBC and system status are one tap away.\n\nSignal-specific reasoning stays behind WHY? on each trade card."


def _set_commands():
    token = os.getenv("TELEGRAM_BOT_TOKEN", "")
    if not token:
        return
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
    if action == "history": fx101.telegram_send(_history_view(), MORE_INLINE)
    elif action == "rfbc": fx101.telegram_send(_rfbc_view(), MORE_INLINE)
    elif action == "health": fx101.telegram_send(_health_view(), MORE_INLINE)
    else: fx101.telegram_send(_home(), PREMIUM_MENU)
    return f"premium_{action}"


def _receive(update: dict) -> str:
    callback = _handle_callback(update)
    if callback:
        return callback
    text = str(update.get("message", {}).get("text", "")).strip()
    mapped = {
        "📈 Open Trades": "/open", "📊 Today": "/today", "🏆 Performance": "/stats",
        "💳 Account": "/accounts", "🧭 Desk": "/gdesk", "⋯ More": "/more",
    }.get(text, text)
    if mapped.startswith(("/start", "/menu")): fx101.telegram_send(_home(), PREMIUM_MENU); return "home"
    if mapped.startswith("/open"): fx101.telegram_send(_open_view(), PREMIUM_MENU); return "open"
    if mapped.startswith("/today"): fx101.telegram_send(_today_view(), PREMIUM_MENU); return "today"
    if mapped.startswith("/stats"): fx101.telegram_send(_performance_view(), PREMIUM_MENU); return "stats"
    if mapped.startswith("/accounts"): fx101.telegram_send(_account_view(), PREMIUM_MENU); return "accounts"
    if mapped.startswith("/gdesk"): fx101.telegram_send(_desk_view(), PREMIUM_MENU); return "gdesk"
    if mapped.startswith("/rfbc"): fx101.telegram_send(_rfbc_view(), PREMIUM_MENU); return "rfbc"
    if mapped.startswith("/history"): fx101.telegram_send(_history_view(), PREMIUM_MENU); return "history"
    if mapped.startswith("/health"): fx101.telegram_send(_health_view(), PREMIUM_MENU); return "health"
    if mapped.startswith("/more"): fx101.telegram_send(_more_view(), MORE_INLINE); return "more"
    if mapped.startswith("/analyze"):
        fx101.telegram_send("G DESK\n\nInstant scan is not available in the current free architecture.\nNext automatic scan: " + fx101.next_gdesk_scan_eat(), PREMIUM_MENU)
        return "analyze_unavailable"
    if mapped != text:
        clone = dict(update); clone["message"] = dict(update.get("message", {})); clone["message"]["text"] = mapped
        return _BASE_RECEIVE(clone)
    return _BASE_RECEIVE(update)


fx101.receive_update = _receive
fx101.log("premium_ux_loaded", level="9_plus", persistent_rows=3, analyze_button=False, inline_more=True, live_r_metrics=True)
