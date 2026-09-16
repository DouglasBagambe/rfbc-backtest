"""Runtime hardening for Turso serverless connections on Render.

Loaded automatically by Python when ``monitor`` is on PYTHONPATH. It wraps
`turso_serverless.connect` so a stale remote stream is detected before the
application executes the real statement. This avoids intermittent
`404 stream not found` failures after long-lived Render processes sit idle.
"""
from __future__ import annotations

import base64
import json
import logging
import os
import time
from datetime import datetime, timezone
from typing import Any

import requests

try:
    import turso_serverless as _turso
except Exception:  # Local/dev environments may not install Turso.
    _turso = None

_LOG = logging.getLogger("fx101.turso")


def _looks_like_stale_stream(exc: BaseException) -> bool:
    text = str(exc).lower()
    return "stream not found" in text or ("404" in text and "stream" in text)


if _turso is not None and not getattr(_turso, "_fx101_resilience_installed", False):
    _real_connect = _turso.connect

    class _ResilientConnection:
        def __init__(self, url: str, *, auth_token: str | None = None, **kwargs: Any):
            self._url = url
            self._auth_token = auth_token
            self._kwargs = kwargs
            self._row_factory = None
            self._conn = self._open()

        def _open(self):
            conn = _real_connect(self._url, auth_token=self._auth_token, **self._kwargs)
            if self._row_factory is not None:
                conn.row_factory = self._row_factory
            return conn

        def _reconnect(self) -> None:
            old = self._conn
            try:
                old.close()
            except Exception:
                pass
            self._conn = self._open()
            _LOG.warning("turso_stream_reconnected")

        @property
        def row_factory(self):
            return self._row_factory

        @row_factory.setter
        def row_factory(self, value):
            self._row_factory = value
            self._conn.row_factory = value

        def _ensure_live(self) -> None:
            try:
                self._conn.execute("SELECT 1")
            except Exception as exc:
                if not _looks_like_stale_stream(exc):
                    raise
                self._reconnect()
                self._conn.execute("SELECT 1")

        def execute(self, sql: str, parameters: Any = ()):
            self._ensure_live()
            return self._conn.execute(sql, parameters)

        def executemany(self, sql: str, seq_of_parameters: Any):
            self._ensure_live()
            return self._conn.executemany(sql, seq_of_parameters)

        def executescript(self, sql_script: str):
            self._ensure_live()
            return self._conn.executescript(sql_script)

        def commit(self):
            return self._conn.commit()

        def rollback(self):
            return self._conn.rollback()

        def close(self):
            return self._conn.close()

        def cursor(self, *args: Any, **kwargs: Any):
            self._ensure_live()
            return self._conn.cursor(*args, **kwargs)

        def __enter__(self):
            self._ensure_live()
            return self

        def __exit__(self, exc_type, exc, tb):
            if exc_type is None:
                self.commit()
            else:
                self.rollback()
            return False

        def __getattr__(self, name: str):
            return getattr(self._conn, name)

    def _resilient_connect(url: str, *, auth_token: str | None = None, **kwargs: Any):
        return _ResilientConnection(url, auth_token=auth_token, **kwargs)

    _turso.connect = _resilient_connect
    _turso._fx101_resilience_installed = True


# Production safety bootstrap: create one explicit tracked account only when the
# persistent account table is empty. This is tracking state, not broker-live
# equity, and never places an order.
if os.getenv("G_DESK_RUNTIME_MODE", "").strip() == "chatgpt_subscription":
    try:
        import fx101 as _fx101

        if not _fx101.list_accounts():
            tracked = float(os.getenv("RFBC_EQUITY_USD", "10.03"))
            _fx101.create_account(
                {
                    "id": "exness-cent-default",
                    "name": "Exness Cent",
                    "broker": "Exness",
                    "account_type": "cent",
                    "base_currency": "USD",
                    "tracked_balance": tracked,
                    "tracked_equity": tracked,
                    "min_lot": 0.01,
                    "volume_step": 0.01,
                    "per_trade_risk_cap": 0.5,
                    "aggregate_risk_cap": 1.5,
                    "max_positions": 3,
                    "allowed_symbols": [
                        "EURUSDc",
                        "GBPUSDc",
                        "GBPJPYc",
                        "USDCADc",
                        "EURJPYc",
                        "USDJPYc",
                        "AUDJPYc",
                    ],
                    "notes": "Tracked Exness Standard Cent account; manual MT5 execution only.",
                }
            )
            _LOG.warning("fx101_default_tracked_account_created")
    except Exception as exc:
        _LOG.exception("fx101_default_account_bootstrap_failed: %s", exc)

# Load current product/risk presentation policy after the safety bootstrap.
try:
    import usercustomize as _fx101_runtime_policy  # noqa: F401
except Exception as exc:
    _LOG.exception("fx101_runtime_policy_load_failed: %s", exc)

# Repair pre-Telegram manual positions and keep lifecycle polling lightweight.
try:
    import production_hotfix as _fx101_production_hotfix  # noqa: F401
except Exception as exc:
    _LOG.exception("fx101_production_hotfix_load_failed: %s", exc)

# Final presentation overlay. Loaded last so it can safely reshape Telegram UX
# without altering trading/data/risk behavior.
try:
    import premium_ux as _fx101_premium_ux  # noqa: F401
except Exception as exc:
    _LOG.exception("fx101_premium_ux_load_failed: %s", exc)

# Temporary live-mode overlay: pause RFBC execution and move USDJPY/AUDJPY into
# G DESK. Frozen RFBC implementation remains in the repo for later re-enable.
try:
    import gdesk_only_mode as _fx101_gdesk_only_mode  # noqa: F401
except Exception as exc:
    _LOG.exception("fx101_gdesk_only_mode_load_failed: %s", exc)

# Harden the ChatGPT-subscription decision mailbox. The prior raw-content fetch
# could block the worker indefinitely. Use GitHub's Contents API with strict
# connect/read timeouts and keep duplicate suppression in-process; persistent
# trade/scan state still remains in Fx101/Turso.
if os.getenv("G_DESK_RUNTIME_MODE", "").strip() == "chatgpt_subscription":
    try:
        import fx101 as _bridge_fx101
        import fx101_worker as _bridge_worker

        _GDESK_API_URL = "https://api.github.com/repos/DouglasBagambe/rfbc-backtest/contents/runtime/gdesk_decision.json"
        _GDESK_CONSUMED: set[str] = set()

        def _consume_gdesk_runtime_decision_hardened() -> None:
            response = requests.get(
                _GDESK_API_URL,
                params={"ref": "gdesk-runtime", "cache_bust": int(time.time())},
                headers={
                    "Accept": "application/vnd.github+json",
                    "Cache-Control": "no-cache",
                    "User-Agent": "fx101-gdesk-bridge",
                },
                timeout=(5, 10),
            )
            response.raise_for_status()
            envelope = response.json()
            encoded = str(envelope.get("content") or "").replace("\n", "")
            if not encoded:
                raise RuntimeError("gdesk_runtime_content_missing")
            body = json.loads(base64.b64decode(encoded).decode("utf-8"))

            decision_id = str(body.get("decision_id") or "").strip()
            result = str(body.get("result") or "").upper().strip()
            if not decision_id or decision_id == "INIT" or result == "NONE" or decision_id in _GDESK_CONSUMED:
                return

            generated_at = str(body.get("generated_at") or "")
            try:
                generated = datetime.fromisoformat(generated_at.replace("Z", "+00:00"))
                age = datetime.now(timezone.utc) - generated.astimezone(timezone.utc)
            except Exception as exc:
                raise RuntimeError("gdesk_runtime_invalid_generated_at") from exc
            if age.total_seconds() < -300 or age.total_seconds() > 3600:
                _bridge_fx101.log("gdesk_bridge_rejected", reason="future_or_stale_decision", decision_id=decision_id)
                _GDESK_CONSUMED.add(decision_id)
                return

            if result == "SYSTEM_FAILURE":
                message = str(body.get("message") or "G_DESK analysis bridge reported a system failure.")[:700]
                ok, status = _bridge_fx101.telegram_send(f"G DESK SYSTEM FAILURE\n{message}")
                if not ok:
                    raise RuntimeError(f"telegram_send_failed:{status}")
                _GDESK_CONSUMED.add(decision_id)
                _bridge_fx101.log("gdesk_bridge_consumed", decision_id=decision_id, result=result, telegram_status=status)
                return

            if result == "NO_TRADE":
                ok, status, _ = _bridge_fx101.ingest_desk_response({"decisions": []})
            elif result == "TRADE":
                decisions = body.get("decisions")
                if not isinstance(decisions, list) or not decisions:
                    _bridge_fx101.log("gdesk_bridge_rejected", reason="trade_requires_decisions", decision_id=decision_id)
                    _GDESK_CONSUMED.add(decision_id)
                    return
                ok, status, _ = _bridge_fx101.ingest_desk_response({"decisions": decisions})
            else:
                _bridge_fx101.log("gdesk_bridge_rejected", reason="invalid_result", decision_id=decision_id)
                _GDESK_CONSUMED.add(decision_id)
                return

            if not ok:
                raise RuntimeError(f"gdesk_ingest_failed:{status}")
            _GDESK_CONSUMED.add(decision_id)
            _bridge_fx101.log("gdesk_bridge_consumed", decision_id=decision_id, result=result, ingest_status=status)

        _bridge_worker._consume_gdesk_runtime_decision = _consume_gdesk_runtime_decision_hardened
        _bridge_fx101.log("gdesk_bridge_hardening_loaded", transport="github_contents_api", timeout_seconds=10)
    except Exception as exc:
        _LOG.exception("gdesk_bridge_hardening_load_failed: %s", exc)
