"""Runtime product/risk policy for G's Fx 101.

Broadens the free G_DESK opportunity set without changing frozen RFBC logic.
Position count is not the limiting factor: aggregate risk and directional
currency exposure are. Telegram UX is optimized as a persistent private
trading terminal rather than a slash-command console.
"""
from __future__ import annotations

import hashlib
import json
import os
import time
import uuid
from datetime import datetime, timedelta, timezone

from dukascopy_python import instruments

os.environ["FX101_MAX_POSITIONS"] = "99"
os.environ["FX101_MAX_TOTAL_RISK_PCT"] = "2.0"

import fx101

REQUESTED_GDESK = [
    "EURUSDc", "GBPUSDc", "GBPJPYc", "USDCADc", "EURJPYc",
    "AUDUSDc", "NZDUSDc", "USDCHFc", "EURGBPc", "CADJPYc",
    "CHFJPYc", "EURAUDc", "GBPAUDc", "EURCADc", "GBPCADc",
    "XAUUSDc",
]
CURRENCY_EXPOSURE_CAP = 1.0


def _resolve_instrument(pair: str):
    wanted = f"{pair[:3]}/{pair[3:6]}".upper()
    for value in vars(instruments).values():
        if isinstance(value, str) and value.upper() == wanted:
            return value
    return None


PROVIDER_MAP = {}
for _symbol in REQUESTED_GDESK:
    _pair = _symbol[:6]
    _inst = _resolve_instrument(_pair)
    if _inst is not None:
        PROVIDER_MAP[_pair] = _inst

ACTIVE_GDESK = [s for s in REQUESTED_GDESK if s[:6] in PROVIDER_MAP]
SKIPPED_GDESK = [s for s in REQUESTED_GDESK if s not in ACTIVE_GDESK]
fx101.DESK_SYMBOLS = set(ACTIVE_GDESK)
fx101.ALL_SYMBOLS = fx101.DESK_SYMBOLS | fx101.RFBC_SYMBOLS


def _legs(symbol: str, side: str, risk: float) -> dict[str, float]:
    pair = symbol[:6]
    base, quote = pair[:3], pair[3:6]
    sign = 1.0 if side == "BUY" else -1.0
    return {base: sign * risk, quote: -sign * risk}


def _active_risk_trades() -> list[dict]:
    now_utc = datetime.now(timezone.utc)
    active = fx101.list_trades("WHERE state IN ('SIGNALLED','PLACED','OPEN')")
    out = []
    for trade in active:
        if trade["state"] == "SIGNALLED":
            try:
                expiry = datetime.fromisoformat(str(trade["valid_until"]).replace("Z", "+00:00")).astimezone(timezone.utc)
            except Exception:
                continue
            if expiry <= now_utc:
                continue
        out.append(trade)
    return out


def _exposures(trades: list[dict]) -> dict[str, float]:
    out: dict[str, float] = {}
    for trade in trades:
        for currency, amount in _legs(trade["symbol"], trade["side"], float(trade["risk_pct"])).items():
            out[currency] = out.get(currency, 0.0) + amount
    return out


def _portfolio_gate(decision: dict) -> list[str]:
    active = _active_risk_trades()
    errors: list[str] = []
    if any(t["symbol"] == decision["symbol"] for t in active):
        errors.append("duplicate_active_symbol")
    total = sum(float(t["risk_pct"]) for t in active) + float(decision["risk_pct"])
    if total > 2.0 + 1e-9:
        errors.append("portfolio_risk_limit")
    exposure = _exposures(active)
    for currency, amount in _legs(decision["symbol"], decision["side"], float(decision["risk_pct"])).items():
        exposure[currency] = exposure.get(currency, 0.0) + amount
    if any(abs(v) > CURRENCY_EXPOSURE_CAP + 1e-9 for v in exposure.values()):
        errors.append("directional_currency_exposure_limit")
    return errors


fx101.portfolio_gate = _portfolio_gate


def _select_account(decision: dict):
    accounts = [
        a for a in fx101.list_accounts()
        if a["status"] == "active"
        and (not a["allowed_symbols"] or decision["symbol"] in a["allowed_symbols"])
    ]
    for account in accounts:
        if float(decision["risk_pct"]) <= float(account["per_trade_risk_cap"]):
            return account, "default_or_first_eligible"
    return None, "no_eligible_account"


fx101.select_account = _select_account

try:
    c = fx101.db()
    c.execute(
        "UPDATE accounts SET max_positions=?, aggregate_risk_cap=?, per_trade_risk_cap=?, allowed_symbols=?, updated_at=? WHERE id=? OR name=?",
        (99, 2.0, 0.5, json.dumps(sorted(fx101.ALL_SYMBOLS)), fx101.now(), "exness-cent-default", "Exness Cent"),
    )
    c.commit()
except Exception as exc:
    fx101.log("fx101_account_policy_update_failed", error=type(exc).__name__)


def _chart_link(symbol: str) -> str:
    pair = symbol[:6]
    if pair == "XAUUSD":
        return "https://www.tradingview.com/chart/?symbol=OANDA%3AXAUUSD"
    return f"https://www.tradingview.com/chart/?symbol=FX%3A{pair}"


fx101.chart_link = _chart_link


def _order_label(trade: dict) -> str:
    raw = str((trade.get("context") or {}).get("order_type") or trade.get("order_type") or trade.get("setup_name") or "MARKET").upper()
    aliases = {
        "BUY": "BUY", "SELL": "SELL", "MARKET": trade.get("side", ""),
        "BUY_LIMIT": "BUY LIMIT", "SELL_LIMIT": "SELL LIMIT",
        "BUY_STOP": "BUY STOP", "SELL_STOP": "SELL STOP",
        "BUY_STOP_LIMIT": "BUY STOP LIMIT", "SELL_STOP_LIMIT": "SELL STOP LIMIT",
    }
    return aliases.get(raw, trade.get("side", raw).replace("_", " "))


def _compact_card(trade: dict) -> str:
    zone = f"{trade['entry']}-{trade['entry_high']}" if trade.get("entry_high") else str(trade["entry"])
    account = trade.get("account_name") or "Exness Cent"
    reasoning = " ".join(str(trade.get("reasoning") or "").split())
    if reasoning:
        reasoning = reasoning.split(". ", 1)[0].rstrip(".") + "."
        if len(reasoning) > 120:
            reasoning = reasoning[:117].rstrip() + "..."
    order = _order_label(trade)
    lines = [
        f"{trade['symbol']}  •  {order}",
        "",
        f"Entry  {zone}",
    ]
    stop_trigger = (trade.get("context") or {}).get("stop_trigger")
    if stop_trigger is not None:
        lines.append(f"Trigger  {stop_trigger}")
    lines += [
        f"SL  {trade['stop']}",
        f"TP  {trade['target']}",
        "",
        f"0.01 lot  •  {trade['risk_pct']}% risk",
        f"{account}  •  valid {fx101.eat(trade['valid_until'])}",
        "",
        f"Cancel: {trade['cancel_condition']}",
        f"Chart: {_chart_link(trade['symbol'])}",
    ]
    if reasoning:
        lines += ["", reasoning]
    return "\n".join(lines)


fx101.card = _compact_card


def _next_scan_eat() -> str:
    eat_now = datetime.now(timezone.utc).astimezone(fx101.EAT)
    candidate = eat_now.replace(minute=15, second=0, microsecond=0)
    if candidate <= eat_now:
        candidate += timedelta(hours=1)
    return candidate.strftime("%H:%M EAT")


fx101.next_gdesk_scan_eat = _next_scan_eat

import fx101_worker
import g_desk_adapter

fx101_worker.PAIR_TO_INSTRUMENT.update(PROVIDER_MAP)
g_desk_adapter.PAIR_TO_DUKASCOPY.clear()
g_desk_adapter.PAIR_TO_DUKASCOPY.update(PROVIDER_MAP)
g_desk_adapter.DESK_SYMBOLS[:] = ACTIVE_GDESK


def _consume_multi_gdesk_runtime_decision() -> None:
    if not fx101_worker.GDESK_RUNTIME_URL:
        return
    r = fx101_worker.requests.get(
        fx101_worker.GDESK_RUNTIME_URL,
        params={"cache_bust": int(time.time())},
        headers={"Cache-Control": "no-cache"},
        timeout=15,
    )
    r.raise_for_status()
    body = r.json()
    decision_id = str(body.get("decision_id") or "").strip()
    result = str(body.get("result") or "").upper().strip()
    if not decision_id or decision_id == "INIT" or result == "NONE" or fx101_worker._bridge_marker_exists(decision_id):
        return
    try:
        generated = datetime.fromisoformat(str(body.get("generated_at") or "").replace("Z", "+00:00"))
        age = datetime.now(timezone.utc) - generated.astimezone(timezone.utc)
    except Exception:
        fx101_worker._reject_bridge(decision_id, "invalid_generated_at", body)
        return
    if age.total_seconds() < -300 or age.total_seconds() > 3600:
        fx101_worker._reject_bridge(decision_id, "future_or_stale_decision", body)
        return
    if result == "SYSTEM_FAILURE":
        fx101.telegram_send("G DESK • SYSTEM ISSUE\n\n" + str(body.get("message") or "Analysis bridge failure.")[:500])
        fx101_worker._mark_bridge_consumed(decision_id, result, body)
        return
    if result == "NO_TRADE":
        ok, status, _ = fx101.ingest_desk_response({"decisions": []})
        if ok:
            fx101_worker._mark_bridge_consumed(decision_id, result, body)
        else:
            fx101_worker._reject_bridge(decision_id, f"ingest_failed:{status}", body)
        return
    if result != "TRADE":
        fx101_worker._reject_bridge(decision_id, "invalid_result", body)
        return
    decisions = body.get("decisions")
    if not isinstance(decisions, list) or not decisions:
        fx101_worker._reject_bridge(decision_id, "trade_requires_nonempty_decisions", body)
        return
    accepted, rejected = [], []
    for decision in decisions:
        context = dict(decision.get("context") or {})
        if decision.get("order_type"):
            context["order_type"] = decision["order_type"]
        if decision.get("stop_trigger") is not None:
            context["stop_trigger"] = decision["stop_trigger"]
        decision = {**decision, "context": context}
        ok, status, trade = fx101.persist_decision({**decision, "source": "G_DESK"})
        if ok:
            accepted.append(trade)
            if status == "signalled":
                fx101.send_signal(trade)
        else:
            rejected.append({"symbol": decision.get("symbol"), "reason": status})
    outcome = "TRADE" if accepted else "REJECTED"
    fx101_worker._mark_bridge_consumed(decision_id, outcome, {**body, "accepted": len(accepted), "rejected": rejected})
    fx101.log("gdesk_bridge_consumed", decision_id=decision_id, result=outcome, accepted=len(accepted), rejected=rejected)


fx101_worker._consume_gdesk_runtime_decision = _consume_multi_gdesk_runtime_decision


def _manage_prices(prices: dict[str, float]) -> list[dict]:
    changed = []
    for trade in fx101.list_trades("WHERE state IN ('PLACED','OPEN')"):
        price = prices.get(trade["symbol"])
        if price is None:
            continue
        price = float(price)
        order_type = str((trade.get("context") or {}).get("order_type") or "MARKET").upper()
        if trade["state"] == "PLACED":
            triggered = True
            if order_type == "BUY_LIMIT": triggered = price <= trade["entry"]
            elif order_type == "SELL_LIMIT": triggered = price >= trade["entry"]
            elif order_type == "BUY_STOP": triggered = price >= trade["entry"]
            elif order_type == "SELL_STOP": triggered = price <= trade["entry"]
            elif order_type == "BUY_STOP_LIMIT":
                trigger = float((trade.get("context") or {}).get("stop_trigger", trade["entry"]))
                triggered = price >= trigger and price <= trade["entry"]
            elif order_type == "SELL_STOP_LIMIT":
                trigger = float((trade.get("context") or {}).get("stop_trigger", trade["entry"]))
                triggered = price <= trigger and price >= trade["entry"]
            if triggered:
                trade = fx101.transition(trade["id"], "OPEN", price, "entry_triggered")
            else:
                c = fx101.db(); c.execute("UPDATE trades SET last_price=? WHERE id=?", (price, trade["id"])); c.commit(); continue
        if trade["side"] == "BUY":
            outcome = "LOST" if price <= trade["stop"] else "WON" if price >= trade["target"] else None
        else:
            outcome = "LOST" if price >= trade["stop"] else "WON" if price <= trade["target"] else None
        if outcome:
            changed.append(fx101.transition(trade["id"], outcome, price, f"{outcome.lower()}_price_hit"))
        else:
            c = fx101.db(); c.execute("UPDATE trades SET last_price=? WHERE id=?", (price, trade["id"])); c.commit()
    return changed


fx101.manage_prices = _manage_prices

# -------- Premium Telegram terminal UX --------

_BASE_TELEGRAM_SEND = fx101.telegram_send
_BASE_RECEIVE_UPDATE = fx101.receive_update

PERSISTENT_MENU = {
    "keyboard": [
        [{"text": "⚡ Analyze"}, {"text": "📈 Open Trades"}],
        [{"text": "◫ Today"}, {"text": "◎ Performance"}],
        [{"text": "◉ Account"}, {"text": "⌁ Desk"}],
        [{"text": "◆ RFBC"}, {"text": "☰ More"}],
    ],
    "resize_keyboard": True,
    "is_persistent": True,
    "input_field_placeholder": "G's Fx 101",
}


def _telegram_send(text: str, keyboard=None):
    import requests
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


fx101.telegram_send = _telegram_send


def _money(v: float | None) -> str:
    if v is None: return "—"
    return f"${float(v):.2f}  /  {float(v)*100:.2f} USC"


def _dashboard() -> str:
    accounts = fx101.list_accounts()
    account = accounts[0] if accounts else None
    active = _active_risk_trades()
    pending = sum(1 for t in active if t["state"] in {"SIGNALLED", "PLACED"})
    opened = sum(1 for t in active if t["state"] == "OPEN")
    risk = sum(float(t["risk_pct"]) for t in active)
    if account:
        balance = _money(account.get("tracked_balance"))
        equity = _money(account.get("tracked_equity"))
        account_name = account["name"]
    else:
        balance = equity = "Not configured"
        account_name = "No account"
    return "\n".join([
        "G'S FX 101",
        "Private Trading Terminal",
        "",
        f"{account_name}",
        f"Balance   {balance}",
        f"Equity    {equity}",
        "",
        f"Open {opened}   •   Pending {pending}   •   Risk {risk:.2f}% / 2.00%",
        f"Next desk scan   {fx101.next_gdesk_scan_eat()}",
        "",
        "Use the menu below. No commands needed.",
    ])


def _open_view() -> str:
    trades = fx101.list_trades("WHERE state IN ('PLACED','OPEN') ORDER BY created_at DESC")
    if not trades:
        return "OPEN TRADES\n\nNothing active right now."
    blocks = ["OPEN TRADES"]
    for t in trades:
        state = "PENDING" if t["state"] == "PLACED" else "OPEN"
        blocks.append("\n".join([
            f"{t['symbol']}  •  {_order_label(t)}  •  {state}",
            f"Entry {t['entry']}   SL {t['stop']}   TP {t['target']}",
            f"0.01 lot   •   {t['risk_pct']}% risk",
            f"Last {t.get('last_price') if t.get('last_price') is not None else '—'}",
        ]))
    return "\n\n".join(blocks)


def _today_view() -> str:
    start = datetime.now(timezone.utc).date().isoformat()
    items = fx101.list_trades("WHERE created_at >= ? ORDER BY created_at DESC", (start,))
    closed = [t for t in items if t["state"] in {"WON", "LOST", "MANUAL_CLOSE"}]
    net = sum(float(t.get("result_r") or 0) for t in closed)
    wins = sum(1 for t in closed if float(t.get("result_r") or 0) > 0)
    losses = sum(1 for t in closed if float(t.get("result_r") or 0) < 0)
    active = sum(1 for t in items if t["state"] in {"PLACED", "OPEN"})
    return "\n".join([
        "TODAY",
        "",
        f"Trades   {len(items)}",
        f"Active   {active}",
        f"Wins     {wins}",
        f"Losses   {losses}",
        f"Net      {net:+.2f}R",
    ])


def _performance_view() -> str:
    closed = fx101.list_trades("WHERE state IN ('WON','LOST','MANUAL_CLOSE')")
    rs = [float(t["result_r"]) for t in closed if t.get("result_r") is not None]
    wins = sum(1 for r in rs if r > 0)
    losses = sum(1 for r in rs if r < 0)
    total = len(rs)
    net = sum(rs)
    wr = wins / total * 100 if total else 0
    avg = net / total if total else 0
    return "\n".join([
        "PERFORMANCE",
        "",
        f"Tracked trades   {total}",
        f"Wins / Losses    {wins} / {losses}",
        f"Win rate         {wr:.0f}%",
        f"Net R            {net:+.2f}",
        f"Average          {avg:+.2f}R",
        "",
        "Forward sample only. More trades needed before judging the edge." if total < 30 else "Forward tracked results.",
    ])


def _account_view() -> str:
    accounts = fx101.list_accounts()
    if not accounts:
        return "ACCOUNT\n\nNo tracked account configured."
    a = accounts[0]
    active = _active_risk_trades()
    risk = sum(float(t["risk_pct"]) for t in active)
    return "\n".join([
        "ACCOUNT",
        "",
        f"{a['name']}  •  {a['broker']}",
        f"Balance   {_money(a.get('tracked_balance'))}",
        f"Equity    {_money(a.get('tracked_equity'))}",
        f"Risk      {risk:.2f}% / {float(a['aggregate_risk_cap']):.2f}%",
        f"Per trade ≤ {float(a['per_trade_risk_cap']):.2f}%",
        "",
        "Manual MT5 execution • tracked account",
    ])


def _desk_view() -> str:
    return "\n".join([
        "G DESK",
        "",
        f"Markets   {len(ACTIVE_GDESK)}",
        "Orders    Market • Limit • Stop • Stop Limit",
        "Risk      0.25–0.50% per setup",
        "Portfolio ≤ 2.00% aggregate",
        f"Next scan {fx101.next_gdesk_scan_eat()}",
        "",
        "Every clean setup can be sent. Weak setups are skipped.",
    ])


def _rfbc_view() -> str:
    return "\n".join([
        "RFBC",
        "",
        "USDJPYc • AUDJPYc",
        "Frozen RFBC v1.0",
        "Manual MT5 execution",
        "",
        "Runs separately from G DESK.",
    ])


def _more_view() -> str:
    return "\n".join([
        "MORE",
        "",
        "History   /history",
        "Health    /health",
        "Why       tap WHY? on any signal",
        "Track     /trackplaced …",
        "",
        "The bottom menu stays available at all times.",
    ])


def _map_button(text: str) -> str | None:
    return {
        "⚡ Analyze": "/analyze",
        "📈 Open Trades": "/open",
        "◫ Today": "/today",
        "◎ Performance": "/stats",
        "◉ Account": "/accounts",
        "⌁ Desk": "/gdesk",
        "◆ RFBC": "/rfbc",
        "☰ More": "/more",
    }.get(text)


def _receive_update(update: dict) -> str:
    text = str(update.get("message", {}).get("text", "")).strip()
    mapped = _map_button(text)
    if mapped:
        text = mapped

    # Persistent-navigation screens.
    if text.startswith(("/start", "/menu")):
        fx101.telegram_send(_dashboard(), PERSISTENT_MENU)
        return "home"
    if text.startswith("/open"):
        fx101.telegram_send(_open_view(), PERSISTENT_MENU)
        return "open"
    if text.startswith("/today"):
        fx101.telegram_send(_today_view(), PERSISTENT_MENU)
        return "today"
    if text.startswith("/stats"):
        fx101.telegram_send(_performance_view(), PERSISTENT_MENU)
        return "stats"
    if text.startswith("/accounts"):
        fx101.telegram_send(_account_view(), PERSISTENT_MENU)
        return "accounts"
    if text.startswith("/gdesk"):
        fx101.telegram_send(_desk_view(), PERSISTENT_MENU)
        return "gdesk"
    if text.startswith("/rfbc"):
        fx101.telegram_send(_rfbc_view(), PERSISTENT_MENU)
        return "rfbc"
    if text.startswith("/more"):
        fx101.telegram_send(_more_view(), PERSISTENT_MENU)
        return "more"
    if text.startswith("/analyze"):
        fx101.queue_gdesk_analysis()
        fx101.telegram_send("G DESK\n\nAnalysis queued.\nNext scheduled scan: " + fx101.next_gdesk_scan_eat(), PERSISTENT_MENU)
        return "analyze"

    if text.startswith("/trackplaced"):
        uid = str(update.get("update_id", ""))
        c = fx101.db()
        if uid and c.execute("SELECT 1 FROM updates WHERE update_id=?", (uid,)).fetchone():
            return "duplicate"
        if uid:
            c.execute("INSERT INTO updates VALUES (?,?)", (uid, fx101.now())); c.commit()
        # Keep legacy manual tracking behavior through the original handler when available.
        clone = dict(update); clone["message"] = dict(update.get("message", {})); clone["message"]["text"] = text
        return _BASE_RECEIVE_UPDATE(clone)

    if mapped:
        clone = dict(update); clone["message"] = dict(update.get("message", {})); clone["message"]["text"] = text
        return _BASE_RECEIVE_UPDATE(clone)
    return _BASE_RECEIVE_UPDATE(update)


fx101.receive_update = _receive_update

fx101.log(
    "gdesk_runtime_policy_loaded",
    active_symbols=ACTIVE_GDESK,
    skipped_symbols=SKIPPED_GDESK,
    max_positions=99,
    max_total_risk_pct=2.0,
    currency_exposure_cap=CURRENCY_EXPOSURE_CAP,
    compact_cards=True,
    persistent_navigation=True,
    premium_terminal_ux=True,
    unlimited_decisions_subject_to_risk=True,
)
