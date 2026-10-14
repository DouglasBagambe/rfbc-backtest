"""Secure MT5 bridge for G's Fx101.

This module is intentionally transport/risk focused. It does not alter RFBC or
G_DESK signal-generation logic. GitHub remains the G_DESK analysis mailbox;
live broker execution uses this authenticated Render <-> MT5 channel.
"""
from __future__ import annotations

import hmac
import json
import os
import uuid
from datetime import datetime, timezone
from typing import Any

from flask import Blueprint, jsonify, request

import fx101

bp = Blueprint("mt5_bridge", __name__)

ACCOUNT_ID = "goat-stride-2500-instant-hero"
EXPECTED_LOGIN = int(os.getenv("FX101_MT5_LOGIN", "315307814"))
EXPECTED_SERVER = os.getenv("FX101_MT5_SERVER", "GoatFunded-Server").strip()
INITIAL_BALANCE = float(os.getenv("FX101_GOAT_INITIAL_BALANCE", "2500"))
SNAPSHOT_MAX_AGE = int(os.getenv("FX101_MT5_SNAPSHOT_MAX_AGE_SECONDS", "30"))
BRIDGE_ENABLED = os.getenv("FX101_MT5_BRIDGE_ENABLED", "0").strip() == "1"
EXECUTION_MODE = os.getenv("FX101_MT5_EXECUTION_MODE", "SHADOW").strip().upper()
PER_TRADE_RISK_CAP = float(os.getenv("FX101_MT5_PER_TRADE_RISK_CAP_PCT", "0.50"))
AGGREGATE_RISK_GUARD = float(os.getenv("FX101_MT5_AGGREGATE_RISK_GUARD_PCT", "0.75"))
FLOATING_LOSS_GUARD = float(os.getenv("FX101_MT5_FLOATING_LOSS_GUARD_PCT", "0.80"))
DAILY_DD_GUARD = float(os.getenv("FX101_MT5_DAILY_DD_GUARD_PCT", "2.50"))
TRAILING_DD_GUARD = float(os.getenv("FX101_MT5_TRAILING_DD_GUARD_PCT", "4.50"))
COMMAND_TTL_SECONDS = int(os.getenv("FX101_MT5_COMMAND_TTL_SECONDS", "180"))


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _iso() -> str:
    return _utcnow().isoformat()


def _authorised() -> bool:
    expected = os.getenv("FX101_MT5_BRIDGE_TOKEN", "")
    supplied = request.headers.get("X-FX101-MT5-Token", "")
    return bool(expected) and hmac.compare_digest(expected, supplied)


def _ensure_schema() -> None:
    c = fx101.db()
    statements = [
        """CREATE TABLE IF NOT EXISTS mt5_snapshots (
            id TEXT PRIMARY KEY, login INTEGER NOT NULL, server TEXT NOT NULL,
            balance REAL NOT NULL, equity REAL NOT NULL, free_margin REAL NOT NULL,
            floating_pnl REAL NOT NULL, day_key TEXT, daily_anchor REAL,
            high_water_equity REAL, payload TEXT NOT NULL, received_at TEXT NOT NULL
        )""",
        """CREATE TABLE IF NOT EXISTS mt5_commands (
            id TEXT PRIMARY KEY, trade_id TEXT NOT NULL UNIQUE, login INTEGER NOT NULL,
            mode TEXT NOT NULL, state TEXT NOT NULL, payload TEXT NOT NULL,
            created_at TEXT NOT NULL, expires_at TEXT NOT NULL,
            broker_ticket TEXT, ack_status TEXT, ack_payload TEXT, acked_at TEXT
        )""",
        "CREATE INDEX IF NOT EXISTS mt5_snapshots_received_idx ON mt5_snapshots(received_at)",
        "CREATE INDEX IF NOT EXISTS mt5_commands_state_idx ON mt5_commands(state, created_at)",
    ]
    for s in statements:
        c.execute(s)
    c.commit()


def _parse_iso(value: str) -> datetime:
    return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(timezone.utc)


def latest_snapshot() -> dict[str, Any] | None:
    _ensure_schema()
    row = fx101.db().execute(
        "SELECT * FROM mt5_snapshots ORDER BY received_at DESC LIMIT 1"
    ).fetchone()
    if not row:
        return None
    out = dict(row)
    out["payload"] = json.loads(out["payload"])
    out["age_seconds"] = (_utcnow() - _parse_iso(out["received_at"])).total_seconds()
    out["fresh"] = out["age_seconds"] <= SNAPSHOT_MAX_AGE
    return out


def _active_broker_items(snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    p = snapshot.get("payload") or {}
    return list(p.get("positions") or []) + list(p.get("orders") or [])


def _same_symbol(a: str, b: str) -> bool:
    return str(a).upper() == str(b).upper()


def _position_risk_pct(snapshot: dict[str, Any]) -> float:
    balance = max(float(snapshot.get("balance") or 0), 1e-9)
    total = 0.0
    for item in _active_broker_items(snapshot):
        try:
            total += max(0.0, float(item.get("risk_usd") or 0.0))
        except Exception:
            pass
    return total / balance * 100.0


def preflight_decision(decision: dict[str, Any]) -> list[str]:
    """Fail-closed broker-aware guard. Active only once bridge is enabled."""
    if not BRIDGE_ENABLED:
        return []
    snap = latest_snapshot()
    if not snap:
        return ["mt5_snapshot_missing"]
    errors: list[str] = []
    if not snap["fresh"]:
        errors.append("mt5_snapshot_stale")
    if int(snap["login"]) != EXPECTED_LOGIN:
        errors.append("mt5_wrong_account")
    if str(snap["server"]).strip() != EXPECTED_SERVER:
        errors.append("mt5_wrong_server")

    balance = float(snap["balance"])
    equity = float(snap["equity"])
    floating = float(snap["floating_pnl"])
    daily_anchor = float(snap.get("daily_anchor") or max(balance, equity))
    high_water = float(snap.get("high_water_equity") or max(INITIAL_BALANCE, equity))

    if balance <= 0 or equity <= 0:
        errors.append("mt5_invalid_equity")
    if floating < -(balance * FLOATING_LOSS_GUARD / 100.0):
        errors.append("goat_floating_loss_guard")
    if equity < daily_anchor * (1.0 - DAILY_DD_GUARD / 100.0):
        errors.append("goat_daily_drawdown_guard")
    # Instant HERO trailing loss is a fixed 5% of initial balance trailing upward
    # and capped at initial balance. We use a stricter 4.5% guard.
    guard_floor = min(INITIAL_BALANCE, high_water - INITIAL_BALANCE * TRAILING_DD_GUARD / 100.0)
    if equity <= guard_floor:
        errors.append("goat_trailing_drawdown_guard")

    risk_pct = float(decision.get("risk_pct") or 0)
    if risk_pct <= 0 or risk_pct > PER_TRADE_RISK_CAP + 1e-9:
        errors.append("mt5_per_trade_risk_cap")
    if _position_risk_pct(snap) + risk_pct > AGGREGATE_RISK_GUARD + 1e-9:
        errors.append("mt5_aggregate_risk_guard")

    symbol = str(decision.get("symbol") or "")
    side = str(decision.get("side") or "").upper()
    for item in _active_broker_items(snap):
        if not _same_symbol(symbol, item.get("symbol", "")):
            continue
        errors.append("mt5_duplicate_active_symbol")
        existing_side = str(item.get("side") or "").upper()
        if existing_side and side and existing_side != side:
            errors.append("goat_hedging_prohibited")
        break
    return list(dict.fromkeys(errors))


def _queue_command(trade: dict[str, Any]) -> None:
    if not BRIDGE_ENABLED:
        return
    _ensure_schema()
    c = fx101.db()
    existing = c.execute("SELECT id FROM mt5_commands WHERE trade_id=?", (trade["trade_id"],)).fetchone()
    if existing:
        return
    context = dict(trade.get("context") or {})
    order_type = str(context.get("order_type") or trade.get("side") or "").upper()
    command_id = "MT5-" + uuid.uuid4().hex[:20].upper()
    now = _utcnow()
    expires = min(
        _parse_iso(trade["valid_until"]),
        datetime.fromtimestamp(now.timestamp() + COMMAND_TTL_SECONDS, tz=timezone.utc),
    )
    payload = {
        "command_id": command_id,
        "trade_id": trade["trade_id"],
        "mode": EXECUTION_MODE if EXECUTION_MODE in {"OBSERVE", "SHADOW", "AUTO"} else "SHADOW",
        "symbol": trade["symbol"],
        "side": trade["side"],
        "order_type": order_type,
        "entry": float(trade["entry"]),
        "stop": float(trade["stop"]),
        "target": float(trade["target"]),
        "requested_volume": float(trade["volume"]),
        "risk_pct": float(trade["risk_pct"]),
        "valid_until": trade["valid_until"],
        "stop_trigger": context.get("stop_trigger"),
        "cancel_condition": trade.get("cancel_condition"),
    }
    c.execute(
        "INSERT INTO mt5_commands (id,trade_id,login,mode,state,payload,created_at,expires_at) VALUES (?,?,?,?,?,?,?,?)",
        (command_id, trade["trade_id"], EXPECTED_LOGIN, payload["mode"], "QUEUED",
         json.dumps(payload, separators=(",", ":")), now.isoformat(), expires.isoformat()),
    )
    c.commit()
    fx101.log("mt5_command_queued", command_id=command_id, trade_id=trade["trade_id"], mode=payload["mode"])


def _activate_stride_profile() -> dict[str, Any]:
    stamp = fx101.now()
    c = fx101.db()
    c.execute("UPDATE accounts SET status='inactive', is_default=0, updated_at=? WHERE id<>?", (stamp, ACCOUNT_ID))
    exists = c.execute("SELECT 1 FROM accounts WHERE id=?", (ACCOUNT_ID,)).fetchone()
    rules = {
        "model": "Goat Stride / Instant HERO",
        "firm_daily_drawdown_pct": 3.0,
        "firm_trailing_max_loss_pct": 5.0,
        "firm_floating_loss_pct": 1.0,
        "ea_first_party_only": True,
        "hedging_allowed": False,
        "hosting_vps_vpn_allowed": False,
        "valid_day_profit_pct": 0.5,
        "valid_days_required": 6,
        "consistency_pct": 15.0,
    }
    allowed = json.dumps(sorted(getattr(fx101, "DESK_SYMBOLS", set())))
    values = (
        "GOAT Stride • $2.5K Instant HERO", "GOAT Funded Trader", "prop", "USD",
        INITIAL_BALANCE, INITIAL_BALANCE, INITIAL_BALANCE, INITIAL_BALANCE,
        PER_TRADE_RISK_CAP, AGGREGATE_RISK_GUARD, DAILY_DD_GUARD, TRAILING_DD_GUARD,
        2, allowed, json.dumps(rules),
        "Authoritative balance/equity comes from local MT5 EA. AUTO remains disabled until shadow validation passes.",
        stamp,
    )
    if exists:
        c.execute(
            """UPDATE accounts SET name=?,broker=?,account_type=?,base_currency=?,
            tracked_balance=?,tracked_equity=?,initial_balance=?,high_water_mark=?,
            status='active',is_default=1,min_lot=NULL,max_lot=NULL,volume_step=NULL,
            per_trade_risk_cap=?,aggregate_risk_cap=?,daily_loss_limit=?,
            weekly_loss_limit=NULL,max_drawdown=?,max_positions=?,allowed_symbols=?,
            prop_rules=?,notes=?,updated_at=? WHERE id=?""",
            values + (ACCOUNT_ID,),
        )
    else:
        c.execute(
            """INSERT INTO accounts
            (id,name,broker,account_type,base_currency,tracked_balance,tracked_equity,
            initial_balance,high_water_mark,status,is_default,min_lot,max_lot,volume_step,
            per_trade_risk_cap,aggregate_risk_cap,daily_loss_limit,weekly_loss_limit,
            max_drawdown,max_positions,allowed_symbols,prop_rules,notes,created_at,updated_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (ACCOUNT_ID,) + values[:8] + ("active", 1, None, None, None) +
            values[8:11] + (None,) + values[11:16] + (stamp,),
        )
    c.commit()
    return fx101.get_account(ACCOUNT_ID)


def install_fx101_hooks() -> None:
    """Patch only execution/account routing; signal-generation remains untouched."""
    fx101.activate_goat_challenge_profile = _activate_stride_profile
    original = fx101.persist_decision

    def wrapped(decision: dict[str, Any]):
        errors = preflight_decision(decision)
        if errors:
            tid = fx101.trade_id(decision)
            return False, ",".join(errors), {"trade_id": tid, "errors": errors}
        ok, status, trade = original(decision)
        if ok and status == "signalled":
            _queue_command(trade)
        return ok, status, trade

    fx101.persist_decision = wrapped


@bp.post("/fx101/mt5/snapshot")
def ingest_snapshot():
    if not _authorised():
        return jsonify({"ok": False, "error": "unauthorized"}), 401
    body = request.get_json(silent=True) or {}
    try:
        login = int(body["login"])
        server = str(body["server"]).strip()
        balance = float(body["balance"])
        equity = float(body["equity"])
        free_margin = float(body["free_margin"])
        floating = float(body["floating_pnl"])
    except (KeyError, TypeError, ValueError):
        return jsonify({"ok": False, "error": "invalid_snapshot"}), 400
    if login != EXPECTED_LOGIN or server != EXPECTED_SERVER:
        return jsonify({"ok": False, "error": "account_or_server_mismatch"}), 403

    _ensure_schema()
    received = _iso()
    high_water = max(float(body.get("high_water_equity") or equity), equity, INITIAL_BALANCE)
    c = fx101.db()
    c.execute(
        """INSERT INTO mt5_snapshots
        (id,login,server,balance,equity,free_margin,floating_pnl,day_key,daily_anchor,
         high_water_equity,payload,received_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
        (uuid.uuid4().hex, login, server, balance, equity, free_margin, floating,
         str(body.get("day_key") or ""), body.get("daily_anchor"), high_water,
         json.dumps(body, separators=(",", ":")), received),
    )
    # Keep account presentation synchronized with broker truth.
    try:
        account = _activate_stride_profile()
        high = max(float(account.get("high_water_mark") or INITIAL_BALANCE), high_water)
        c.execute(
            "UPDATE accounts SET tracked_balance=?,tracked_equity=?,high_water_mark=?,updated_at=? WHERE id=?",
            (balance, equity, high, received, ACCOUNT_ID),
        )
    except Exception as exc:
        fx101.log("mt5_account_sync_failed", error=type(exc).__name__)
    c.commit()
    return jsonify({"ok": True, "received_at": received, "mode": EXECUTION_MODE})


@bp.get("/fx101/mt5/command")
def next_command():
    if not _authorised():
        return jsonify({"ok": False, "error": "unauthorized"}), 401
    try:
        login = int(request.args.get("login", "0"))
    except ValueError:
        login = 0
    if login != EXPECTED_LOGIN:
        return jsonify({"ok": False, "error": "wrong_account"}), 403
    _ensure_schema()
    now = _iso()
    c = fx101.db()
    # Expire old commands before selection.
    c.execute("UPDATE mt5_commands SET state='EXPIRED' WHERE state='QUEUED' AND expires_at<=?", (now,))
    row = c.execute(
        "SELECT * FROM mt5_commands WHERE login=? AND state='QUEUED' ORDER BY created_at ASC LIMIT 1",
        (login,),
    ).fetchone()
    c.commit()
    if not row:
        return jsonify({"ok": True, "command": None})
    payload = json.loads(dict(row)["payload"])
    return jsonify({"ok": True, "command": payload})


@bp.post("/fx101/mt5/ack")
def ack_command():
    if not _authorised():
        return jsonify({"ok": False, "error": "unauthorized"}), 401
    body = request.get_json(silent=True) or {}
    command_id = str(body.get("command_id") or "")
    status = str(body.get("status") or "").upper()
    if not command_id or status not in {
        "SHADOW_OK", "EXECUTED", "REJECTED", "ERROR", "CANCELLED", "EXPIRED"
    }:
        return jsonify({"ok": False, "error": "invalid_ack"}), 400
    _ensure_schema()
    c = fx101.db()
    row = c.execute("SELECT * FROM mt5_commands WHERE id=?", (command_id,)).fetchone()
    if not row:
        return jsonify({"ok": False, "error": "unknown_command"}), 404
    record = dict(row)
    if record["state"] in {"ACKED", "REJECTED", "EXPIRED"}:
        return jsonify({"ok": True, "idempotent": True})
    new_state = "ACKED" if status in {"SHADOW_OK", "EXECUTED"} else ("EXPIRED" if status == "EXPIRED" else "REJECTED")
    c.execute(
        "UPDATE mt5_commands SET state=?,broker_ticket=?,ack_status=?,ack_payload=?,acked_at=? WHERE id=?",
        (new_state, str(body.get("broker_ticket") or ""), status,
         json.dumps(body, separators=(",", ":")), _iso(), command_id),
    )
    c.commit()
    fx101.log("mt5_command_ack", command_id=command_id, status=status, broker_ticket=body.get("broker_ticket"))
    return jsonify({"ok": True, "state": new_state})


@bp.get("/fx101/mt5/status")
def mt5_status():
    snap = latest_snapshot()
    if not snap:
        return jsonify({"ok": True, "bridge_enabled": BRIDGE_ENABLED, "connected": False, "mode": EXECUTION_MODE})
    return jsonify({
        "ok": True,
        "bridge_enabled": BRIDGE_ENABLED,
        "connected": bool(snap["fresh"]),
        "mode": EXECUTION_MODE,
        "login": snap["login"],
        "server": snap["server"],
        "balance": snap["balance"],
        "equity": snap["equity"],
        "floating_pnl": snap["floating_pnl"],
        "age_seconds": snap["age_seconds"],
        "open_risk_pct": _position_risk_pct(snap),
    })
