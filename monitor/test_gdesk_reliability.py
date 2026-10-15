"""Regression coverage for real session gaps, hourly cache rollover and delivery."""
import importlib
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch
import pandas as pd
import g_desk_adapter as adapter


class FreshnessTests(unittest.TestCase):
    def bars(self, symbol, end, count=24):
        stamps = []
        stamp = pd.Timestamp(end)
        while len(stamps) < count:
            if adapter._is_trading_hour(symbol, stamp):
                stamps.append(stamp)
            stamp -= pd.Timedelta(hours=1)
        return [dict(datetime=s.isoformat(), open=100., high=102., low=98., close=100., bid_close=99.9, ask_close=100.1, spread=.2)
                for s in reversed(stamps)]

    def test_gold_summer_settlement_gap_is_expected(self):
        bars = self.bars("XAUUSD.x", "2026-10-15T11:00:00Z")
        self.assertNotIn("2026-10-14T21:00:00+00:00", [b["datetime"] for b in bars])
        adapter._validate_bars("XAUUSD.x", bars, pd.Timestamp("2026-10-15T12:00:00Z"))

    def test_gold_winter_settlement_and_dst(self):
        self.assertFalse(adapter._is_trading_hour("XAUUSD.x", pd.Timestamp("2026-12-15T22:00:00Z")))
        self.assertTrue(adapter._is_trading_hour("XAUUSD.x", pd.Timestamp("2026-12-15T21:00:00Z")))
        self.assertFalse(adapter._is_trading_hour("XAUUSD.x", pd.Timestamp("2026-03-09T21:00:00Z")))
        self.assertTrue(adapter._is_trading_hour("EURUSD.x", pd.Timestamp("2026-10-14T21:00:00Z")))

    def test_unexpected_gold_gap_and_fx_gap_still_fail(self):
        for symbol in ("XAUUSD.x", "EURUSD.x"):
            bars = self.bars(symbol, "2026-10-15T11:00:00Z")
            del bars[-4]
            with self.assertRaisesRegex(RuntimeError, "missing_trading_bar"):
                adapter._validate_bars(symbol, bars, pd.Timestamp("2026-10-15T12:00:00Z"))

    def test_stale_and_duplicate_bars_fail(self):
        bars = self.bars("EURUSD.x", "2026-10-15T10:00:00Z")
        with self.assertRaisesRegex(RuntimeError, "stale_dukascopy"):
            adapter._validate_bars("EURUSD.x", bars, pd.Timestamp("2026-10-15T12:00:00Z"))
        bars.append(bars[-1])
        with self.assertRaisesRegex(RuntimeError, "duplicate_or_unordered"):
            adapter._validate_bars("EURUSD.x", bars, pd.Timestamp("2026-10-15T12:00:00Z"))

    def test_weekend_and_gold_reopen(self):
        self.assertEqual(adapter._expected_latest("EURUSD.x", pd.Timestamp("2026-10-19T00:00:00Z")), pd.Timestamp("2026-10-18T23:00:00Z"))
        self.assertEqual(adapter._expected_latest("XAUUSD.x", pd.Timestamp("2026-10-18T22:00:00Z")), pd.Timestamp("2026-10-16T20:00:00Z"))

    def test_hour_rollover_cannot_reuse_recent_stale_cache(self):
        cutoff = pd.Timestamp.now(tz="UTC").floor("h")
        # During the trading week only; an older expected bar always invalidates cache.
        fresh = self.bars("EURUSD.x", adapter._expected_latest("EURUSD.x", cutoff))
        stale = fresh[:-1]
        adapter._DUKA_CACHE["EURUSD.x"] = (adapter.time.time(), stale)
        rows = [dict(dt=pd.Timestamp(b["datetime"]), open=b["open"], high=b["high"], low=b["low"], close=b["close"], volume=1) for b in fresh]
        frame = pd.DataFrame(rows)
        with patch.object(adapter, "_fetch_duka_side", return_value=frame) as fetch:
            result = adapter._dukascopy_context(["EURUSD.x"])
        self.assertEqual(fetch.call_count, 2)
        self.assertEqual(result["EURUSD.x"][-1]["datetime"], fresh[-1]["datetime"])
        adapter._DUKA_CACHE.clear()


class DeliveryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        os.environ.pop("TURSO_DATABASE_URL", None)
        os.environ.pop("TURSO_DB_URL", None)
        os.environ["FX101_DB_PATH"] = str(Path(self.tmp.name) / "test.db")
        import fx101, fx101_worker
        self.fx = importlib.reload(fx101)
        self.worker = importlib.reload(fx101_worker)

    def tearDown(self):
        self.fx.close_db()
        self.tmp.cleanup()

    def test_system_failure_retries_until_telegram_accepts(self):
        body = dict(decision_id="failure", result="SYSTEM_FAILURE", decisions=[], generated_at=datetime.now(timezone.utc).isoformat(), message="provider failed")
        with patch.object(self.worker, "_fetch_gdesk_runtime_decision", return_value=body), patch.object(self.fx, "telegram_send", side_effect=[(False, "503"), (True, "200")]) as send:
            self.worker._consume_gdesk_runtime_decision()
            self.assertFalse(self.worker._bridge_marker_exists("failure"))
            self.worker._consume_gdesk_runtime_decision()
            self.worker._consume_gdesk_runtime_decision()
            self.assertTrue(self.worker._bridge_marker_exists("failure"))
            self.assertEqual(send.call_count, 2)

    def test_no_trade_delivery_failure_is_retryable(self):
        body = dict(decision_id="no-trade", result="NO_TRADE", decisions=[], generated_at=datetime.now(timezone.utc).isoformat(), message="best candidate failed spread")
        with patch.object(self.worker, "_fetch_gdesk_runtime_decision", return_value=body), patch.object(self.fx, "telegram_send", side_effect=[(False, "503"), (True, "200")]) as send:
            self.worker._consume_gdesk_runtime_decision()
            self.assertFalse(self.worker._bridge_marker_exists("no-trade"))
            self.worker._consume_gdesk_runtime_decision()
            self.assertTrue(self.worker._bridge_marker_exists("no-trade"))
            self.assertIn("best candidate failed spread", send.call_args[0][0])

    def test_watchdog_retry_dedup_and_restart(self):
        instant = datetime(2026, 10, 15, 12, 40, tzinfo=timezone.utc)
        with patch.object(self.fx, "telegram_send", side_effect=[(False, "503"), (True, "200")]) as send:
            self.worker._gdesk_delivery_watchdog(instant)
            self.worker._gdesk_delivery_watchdog(instant)
            self.worker = importlib.reload(self.worker)
            self.worker._gdesk_delivery_watchdog(instant)
            self.assertEqual(send.call_count, 2)

    def test_watchdog_waits_and_suppresses_after_real_result(self):
        instant = datetime(2026, 10, 15, 12, 40, tzinfo=timezone.utc)
        with patch.object(self.fx, "telegram_send") as send:
            self.worker._gdesk_delivery_watchdog(instant.replace(minute=20))
            self.worker._gdesk_delivery_watchdog(datetime(2026, 10, 17, 12, 40, tzinfo=timezone.utc))
            with patch.object(self.fx, "now", return_value=instant.isoformat()):
                self.worker._mark_bridge_consumed("real", "NO_TRADE", {})
            self.worker._gdesk_delivery_watchdog(instant)
            send.assert_not_called()
