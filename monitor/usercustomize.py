"""Runtime product policy for G's Fx 101.

Keeps the free ChatGPT bridge intact while applying the current production
preferences: up to three independent positions, 0.5% per trade / 1.5% total,
compact Telegram cards, and multi-decision runtime mailbox consumption.
"""
from __future__ import annotations

import json
import os
import time
from datetime import datetime, timedelta, timezone

# Production portfolio policy. Render env mirrors these values, but setting
# them here also keeps a fresh free-tier instance deterministic.
os.environ["FX101_MAX_POSITIONS"] = "3"
os.environ["FX101_MAX_TOTAL_RISK_PCT"] = "1.5"

import fx101


def _currencies(symbol: str) -> set[str]:
    base = symbol[:6]
    return {base[:3], base[3:6]}


def _correlated(a: str, b: str) -> bool:
    """Treat two FX positions as correlated only when they share a currency."""
    return bool(_currencies(a) & _currencies(b))


fx101.correlated = _correlated


def _active_risk_trades() -> list[dict]:
    """Reserve risk for open positions plus still-valid pending signals."""
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


def _portfolio_gate(decision: dict) -> list[str]:
    cfg = fx101.risk_config()
    active = _active_risk_trades()
    errors: list[str] = []
    if len(active) >= int(cfg["max_positions"]):
        errors.append("position_limit")
    total = sum(float(x["risk_pct"]) for x in active) + float(decision["risk_pct"])
    if total > float(cfg["max_total_risk_pct"]):
        errors.append("portfolio_risk_limit")
    if any(_correlated(decision["symbol"], x["symbol"]) for x in active):
        errors.append("correlated_exposure")
    return errors


fx101.portfolio_gate = _portfolio_gate


def _select_account(decision: dict):
    accounts = [
        a for a in fx101.list_accounts()
        if a["status"] == "active"
        and (not a["allowed_symbols"] or decision["symbol"] in a["allowed_symbols"])
    ]
    active = _active_risk_trades()
    c = fx101.db()
    for account in accounts:
        account_active = 0
        for trade in active:
            linked = c.execute(
                "SELECT 1 FROM trade_accounts WHERE account_id=? AND trade_id=?",
                (account["id"], trade["id"]),
            ).fetchone()
            if linked:
                account_active += 1
        if account_active < int(account["max_positions"]) and float(decision["risk_pct"]) <= float(account["per_trade_risk_cap"]):
            return account, "default_or_first_eligible"
    return None, "no_eligible_account"


fx101.select_account = _select_account

# Upgrade the existing default tracked account as well as future restarts.
try:
    c = fx101.db()
    c.execute(
        "UPDATE accounts SET max_positions=?, aggregate_risk_cap=?, per_trade_risk_cap=?, updated_at=? WHERE id=? OR name=?",
        (3, 1.5, 0.5, fx101.now(), "exness-cent-default", "Exness Cent"),
    )
    c.commit()
except Exception as exc:
    fx101.log("fx101_account_policy_update_failed", error=type(exc).__name__)


def _compact_card(trade: dict) -> str:
    zone = f"{trade['entry']}-{trade['entry_high']}" if trade.get("entry_high") else str(trade["entry"])
    account = trade.get("account_name") or "Exness Cent"
    reasoning = " ".join(str(trade.get("reasoning") or "").split())
    if reasoning:
        reasoning = reasoning.split(". ", 1)[0].rstrip(".") + "."
        if len(reasoning) > 150:
            reasoning = reasoning[:147].rstrip() + "..."
    lines = [
        f"{trade['source'].replace('_', ' ')} • {trade['symbol']} • {trade['side']}",
        "",
        f"Entry: {zone}",
        f"SL: {trade['stop']}",
        f"TP: {trade['target']}",
        f"Volume: {trade['volume']}",
        f"Risk: max {trade['risk_pct']}%",
        f"Account: {account}",
        f"Valid until: {fx101.eat(trade['valid_until'])}",
        f"Cancel: {trade['cancel_condition']}",
        f"Chart: {fx101.chart_link(trade['symbol'])}",
    ]
    if reasoning:
        lines += ["", f"Summary: {reasoning}"]
    return "\n".join(lines)


fx101.card = _compact_card


def _next_scan_eat() -> str:
    eat_now = datetime.now(timezone.utc).astimezone(fx101.EAT)
    candidate = eat_now.replace(minute=15, second=0, microsecond=0)
    if candidate <= eat_now:
        candidate += timedelta(hours=1)
    return candidate.strftime("%H:%M EAT")


fx101.next_gdesk_scan_eat = _next_scan_eat

# Import after fx101 is fully patched. webapp.py will later receive this same
# already-imported module instance.
import fx101_worker


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
    if not decision_id or decision_id == "INIT" or result == "NONE":
        return
    if fx101_worker._bridge_marker_exists(decision_id):
        return

    generated_at = str(body.get("generated_at") or "")
    try:
        generated = datetime.fromisoformat(generated_at.replace("Z", "+00:00"))
        age = datetime.now(timezone.utc) - generated.astimezone(timezone.utc)
    except Exception:
        fx101_worker._reject_bridge(decision_id, "invalid_generated_at", body)
        return
    if age.total_seconds() < -300 or age.total_seconds() > 3600:
        fx101_worker._reject_bridge(decision_id, "future_or_stale_decision", body)
        return

    if result == "SYSTEM_FAILURE":
        message = str(body.get("message") or "G_DESK analysis bridge reported a system failure.")[:700]
        fx101.telegram_send(f"G DESK SYSTEM FAILURE\n{message}")
        fx101_worker._mark_bridge_consumed(decision_id, result, body)
        fx101.log("gdesk_bridge_consumed", decision_id=decision_id, result=result)
        return

    if result == "NO_TRADE":
        ok, status, _ = fx101.ingest_desk_response({"decisions": []})
    elif result == "TRADE":
        decisions = body.get("decisions")
        if not isinstance(decisions, list) or not 1 <= len(decisions) <= 3:
            fx101_worker._reject_bridge(decision_id, "trade_requires_one_to_three_decisions", body)
            return
        symbols = [str(d.get("symbol") or "") for d in decisions]
        for i, symbol in enumerate(symbols):
            if any(_correlated(symbol, other) for other in symbols[:i]):
                fx101_worker._reject_bridge(decision_id, "correlated_decisions_in_same_scan", body)
                return
        ok, status, _ = fx101.ingest_desk_response({"decisions": decisions})
    else:
        fx101_worker._reject_bridge(decision_id, "invalid_result", body)
        return

    if ok:
        fx101_worker._mark_bridge_consumed(decision_id, result, body)
        fx101.log("gdesk_bridge_consumed", decision_id=decision_id, result=result, ingest_status=status)
    else:
        fx101_worker._reject_bridge(decision_id, f"ingest_failed:{status}", body)


fx101_worker._consume_gdesk_runtime_decision = _consume_multi_gdesk_runtime_decision
fx101.log("gdesk_runtime_policy_loaded", max_positions=3, max_total_risk_pct=1.5, multi_decision=True, compact_cards=True)
