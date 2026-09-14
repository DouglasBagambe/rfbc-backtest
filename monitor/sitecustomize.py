"""Runtime hardening for Turso serverless connections on Render.

Loaded automatically by Python when ``monitor`` is on PYTHONPATH.  It wraps
`turso_serverless.connect` so a stale remote stream is detected before the
application executes the real statement.  This avoids intermittent
`404 stream not found` failures after long-lived Render processes sit idle.
"""
from __future__ import annotations

import logging
from typing import Any

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
