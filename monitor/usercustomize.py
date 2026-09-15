"""Runtime product/risk policy for G's Fx 101.

Broadens the free G_DESK opportunity set without changing frozen RFBC logic.
Position count is not the limiting factor: aggregate risk and directional
currency exposure are. Telegram cards stay intentionally compact.
"""
from __future__ import annotations

import hashlib
import json
import os
import time
import uuid
from datetime import datetime, timedelta, timezone

from dukascopy_python import instruments

# Effectively remove the arbitrary position-count ceiling. Risk remains capped.
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

# Patch the authoritative validation universe; RFBC remains untouched.
fx101.DESK_SYMBOLS = set(ACTIVE_GDESK)
fx101.ALL_SYMBOLS = fx101.DESK_SYMBOLS | fx101.RFBC_SYMBOLS


def _legs(symbol: str, side: str, risk: float) -> dict[str, float]:
    pair = symbol[:6]
    base, quote = pair[:3], pair[3:6]
    sign = 1.0 if side == "BUY" else -1.0
    return {base: sign * risk, quote: -sign * risk}


def _active_risk_trades() -> list[dict]:
    """Reserve risk for open positions and still-valid pending signals."""
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
    # Automated desk should not keep stacking the exact same market while active.
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

# Upgrade the persistent tracked account for the broader desk.
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


def _compact_card(trade: dict) -> str:
    zone = f"{trade['entry']}-{trade['entry_high']}" if trade.get("entry_high") else str(trade["entry"])
    account = trade.get("account_name") or "Exness Cent"
    reasoning = " ".join(str(trade.get("reasoning") or "").split())
    if reasoning:
        reasoning = reasoning.split(". ", 1)[0].rstrip(".") + "."
        if len(reasoning) > 140:
            reasoning = reasoning[:137].rstrip() + "..."
    lines = [
        f"G DESK • {trade['symbol']} • {trade['side']}",
        "",
        f"Entry: {zone}",
        f"SL: {trade['stop']}",
        f"TP: {trade['target']}",
        f"Volume: {trade['volume']}",
        f"Risk: {trade['risk_pct']}%",
        f"Account: {account}",
        f"Valid until: {fx101.eat(trade['valid_until'])}",
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

# Patch provider/worker maps before their first production loop.
import fx101_worker
import g_desk_adapter

fx101_worker.PAIR_TO_INSTRUMENT.update(PROVIDER_MAP)
g_desk_adapter.PAIR_TO_DUKASCOPY.clear()
g_desk_adapter.PAIR_TO_DUKASCOPY.update(PROVIDER_MAP)
g_desk_adapter.DESK_SYMBOLS[:] = ACTIVE_GDESK


def _consume_multi_gdesk_runtime_decision() -> None:
    """Consume any number of proposed trades; accept only those passing live risk gates."""
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
        fx101.telegram_send("G DESK SYSTEM FAILURE\n" + str(body.get("message") or "Analysis bridge failure.")[:700])
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

# Signal validity is for entry, not an automatic expiry after the user has placed it.
def _manage_prices(prices: dict[str, float]) -> list[dict]:
    changed = []
    for trade in fx101.list_trades("WHERE state IN ('PLACED','OPEN')"):
        price = prices.get(trade["symbol"])
        if price is None:
            continue
        price = float(price)
        if trade["state"] == "PLACED":
            trade = fx101.transition(trade["id"], "OPEN", price, "price_snapshot_open")
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

# Manual backfill for trades placed from ChatGPT before Telegram tracking existed.
_base_receive_update = fx101.receive_update


def _manual_track(parts: list[str]) -> str:
    if len(parts) < 6:
        return "Usage: /trackplaced SYMBOL BUY|SELL ENTRY SL TP [VOLUME] [RISK]"
    symbol, side = parts[1], parts[2].upper()
    try:
        entry, stop, target = map(float, parts[3:6])
        volume = float(parts[6]) if len(parts) > 6 else 0.01
        risk = float(parts[7]) if len(parts) > 7 else 0.5
    except ValueError:
        return "Invalid numbers."
    if symbol not in fx101.ALL_SYMBOLS or side not in {"BUY", "SELL"}:
        return "Unsupported symbol or side."
    if (side == "BUY" and not stop < entry < target) or (side == "SELL" and not target < entry < stop):
        return "Invalid SL/TP geometry."
    c = fx101.db()
    existing = c.execute(
        "SELECT id,state FROM trades WHERE symbol=? AND side=? AND ABS(entry-?)<1e-9 AND ABS(stop-?)<1e-9 AND ABS(target-?)<1e-9 ORDER BY created_at DESC LIMIT 1",
        (symbol, side, entry, stop, target),
    ).fetchone()
    if existing:
        tid, state = existing[0], existing[1]
        try:
            if state == "SIGNALLED":
                fx101.transition(tid, "PLACED", entry, "manual_backfill")
                fx101.transition(tid, "OPEN", entry, "manual_backfill")
            elif state == "PLACED":
                fx101.transition(tid, "OPEN", entry, "manual_backfill")
        except ValueError:
            pass
        return f"Tracking {tid}."
    account = next((a for a in fx101.list_accounts() if a["status"] == "active"), None)
    if not account:
        return "No active tracked account."
    stamp = fx101.now()
    tid = "MANUAL-" + hashlib.sha256(f"{symbol}|{side}|{entry}|{stop}|{target}|{stamp}".encode()).hexdigest()[:12].upper()
    valid_until = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()
    context = json.dumps({"manual_backfill": True})
    c.execute("""INSERT INTO trades VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",(
        tid,"G_DESK",symbol,side,"OPEN",stamp,stamp,stamp,None,entry,None,stop,target,volume,risk,valid_until,
        "Manual backfill; broker position already placed.","MANUAL",None,None,None,None,"Manual position backfill",context,entry,None,None,None
    ))
    c.execute("INSERT INTO trade_accounts VALUES (?,?,?)",(tid,account["id"],"manual_backfill"))
    c.execute("INSERT INTO transition_events VALUES (?,?,?,?,?,?,?)",(str(uuid.uuid4()),tid,None,"OPEN",entry,"manual_backfill",stamp))
    c.commit()
    return f"Tracking {tid}."


def _receive_update(update: dict) -> str:
    text = str(update.get("message", {}).get("text", "")).strip()
    if text.startswith("/trackplaced"):
        uid = str(update.get("update_id", ""))
        c = fx101.db()
        if uid and c.execute("SELECT 1 FROM updates WHERE update_id=?", (uid,)).fetchone():
            return "duplicate"
        if uid:
            c.execute("INSERT INTO updates VALUES (?,?)", (uid, fx101.now())); c.commit()
        reply = _manual_track(text.split())
        fx101.telegram_send(reply)
        return "trackplaced"
    return _base_receive_update(update)


fx101.receive_update = _receive_update

fx101.log(
    "gdesk_runtime_policy_loaded",
    active_symbols=ACTIVE_GDESK,
    skipped_symbols=SKIPPED_GDESK,
    max_positions=99,
    max_total_risk_pct=2.0,
    currency_exposure_cap=CURRENCY_EXPOSURE_CAP,
    compact_cards=True,
    unlimited_decisions_subject_to_risk=True,
)
