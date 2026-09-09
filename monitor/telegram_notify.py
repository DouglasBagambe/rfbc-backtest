#!/usr/bin/env python3
from __future__ import annotations

import os
from typing import Any

import requests

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "").strip()


def configured() -> bool:
    return bool(BOT_TOKEN and CHAT_ID)


def _fmt_value(v: Any) -> str:
    if isinstance(v, float):
        return f"{v:.6f}".rstrip("0").rstrip(".")
    return str(v)


def format_action(payload: dict[str, Any]) -> str:
    action = str(payload.get("action", "UNKNOWN")).upper()
    symbol = payload.get("symbol", "USDJPYc")
    lines = [f"RFBC {action}", f"Symbol: {symbol}"]

    preferred = [
        ("direction", "Direction"),
        ("volume", "Volume"),
        ("entry", "Entry"),
        ("stop", "SL"),
        ("target", "TP"),
        ("be_stop", "BE stop"),
        ("atr", "ATR"),
        ("risk_pct", "Estimated risk %"),
        ("risk_cap_pct", "Risk cap %"),
        ("signal_dt", "Signal UTC"),
        ("entry_dt", "Entry UTC"),
        ("last_h4_close", "Last H4 close"),
        ("reason", "Reason"),
        ("error", "Error"),
    ]
    used = {"action", "symbol", "ok", "checked_at"}
    for key, label in preferred:
        if key in payload and payload[key] is not None:
            lines.append(f"{label}: {_fmt_value(payload[key])}")
            used.add(key)

    for key, value in payload.items():
        if key in used or value is None:
            continue
        lines.append(f"{key}: {_fmt_value(value)}")

    if payload.get("checked_at"):
        lines.append(f"Checked UTC: {payload['checked_at']}")
    return "\n".join(lines)


def send_message(text: str, timeout: int = 12) -> tuple[bool, str]:
    if not configured():
        return False, "telegram_not_configured"

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    try:
        resp = requests.post(
            url,
            json={
                "chat_id": CHAT_ID,
                "text": text,
                "disable_web_page_preview": True,
            },
            timeout=timeout,
        )
        if resp.ok:
            return True, "sent"
        return False, f"telegram_http_{resp.status_code}: {resp.text[:240]}"
    except Exception as exc:
        return False, f"telegram_exception: {type(exc).__name__}: {exc}"


def send_action(payload: dict[str, Any]) -> tuple[bool, str]:
    return send_message(format_action(payload))
