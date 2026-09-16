"""Verify G DESK Telegram delivery before a decision is considered consumed."""
from __future__ import annotations

from typing import Any

import fx101

_REAL_TELEGRAM_SEND = fx101.telegram_send
_REAL_INGEST = fx101.ingest_desk_response
_DELIVERY_EVENTS: list[tuple[bool, str]] = []

_OLD_NO_TRADE = "G_DESK NO TRADE — no qualified setup across EURUSDc, GBPUSDc, GBPJPYc, USDCADc, EURJPYc."
_NEW_NO_TRADE = "G_DESK NO TRADE — no qualified setup across the current 18-symbol desk universe."


def _verified_telegram_send(text: str, keyboard: list[list[dict[str, str]]] | None = None) -> tuple[bool, str]:
    if text == _OLD_NO_TRADE:
        text = _NEW_NO_TRADE
    ok, status = _REAL_TELEGRAM_SEND(text, keyboard)
    _DELIVERY_EVENTS.append((ok, status))
    fx101.log(
        "telegram_delivery",
        ok=ok,
        status=status,
        message_kind=("NO_TRADE" if text.startswith("G_DESK NO TRADE") else "TRADE_OR_SYSTEM"),
    )
    return ok, status


def _verified_ingest(body: dict[str, Any]):
    _DELIVERY_EVENTS.clear()
    ok, status, accepted = _REAL_INGEST(body)

    # If this is a retry of a trade already persisted as SIGNALLED, the legacy
    # idempotency path does not re-send it. Re-send only that still-unacknowledged
    # signal so a transient Telegram failure remains retryable.
    if accepted and not _DELIVERY_EVENTS:
        for trade in accepted:
            if str(trade.get("state") or "").upper() == "SIGNALLED":
                fx101.send_signal(trade)

    if _DELIVERY_EVENTS and any(not delivered for delivered, _ in _DELIVERY_EVENTS):
        failures = ",".join(status_code for delivered, status_code in _DELIVERY_EVENTS if not delivered)
        return False, f"telegram_send_failed:{failures}", accepted

    # A successful desk result must have attempted a Telegram delivery. This
    # catches regressions where persistence succeeds but notification is skipped.
    if ok and not _DELIVERY_EVENTS:
        return False, "telegram_delivery_not_attempted", accepted

    return ok, status, accepted


fx101.telegram_send = _verified_telegram_send
fx101.ingest_desk_response = _verified_ingest
fx101.log("telegram_delivery_hardening_loaded", retry_on_failure=True)
