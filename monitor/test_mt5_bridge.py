import importlib
import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path


class Mt5BridgeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        os.environ.pop("TURSO_DATABASE_URL", None)
        os.environ.pop("TURSO_DB_URL", None)
        os.environ["FX101_DB_PATH"] = str(Path(self.tmp.name) / "mt5.db")
        os.environ["FX101_MT5_BRIDGE_ENABLED"] = "1"
        os.environ["FX101_MT5_LOGIN"] = "315307814"
        os.environ["FX101_MT5_SERVER"] = "GoatFunded-Server"
        import fx101
        self.fx101 = importlib.reload(fx101)
        import mt5_bridge
        self.bridge = importlib.reload(mt5_bridge)
        self.bridge._ensure_schema()

    def tearDown(self):
        self.fx101.close_db()
        self.tmp.cleanup()

    def _snapshot(self, *, balance=2476.17, equity=2476.17, floating=0.0, positions=None, orders=None):
        now = datetime.now(timezone.utc).isoformat()
        payload = {
            "login": 315307814,
            "server": "GoatFunded-Server",
            "balance": balance,
            "equity": equity,
            "free_margin": equity,
            "floating_pnl": floating,
            "day_key": "2026-10-14",
            "daily_anchor": 2476.17,
            "high_water_equity": 2500.0,
            "positions": positions or [],
            "orders": orders or [],
        }
        c = self.fx101.db()
        c.execute(
            """INSERT INTO mt5_snapshots
            (id,login,server,balance,equity,free_margin,floating_pnl,day_key,daily_anchor,
             high_water_equity,payload,received_at) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
            ("s1", 315307814, "GoatFunded-Server", balance, equity, equity, floating,
             payload["day_key"], payload["daily_anchor"], payload["high_water_equity"],
             json.dumps(payload), now),
        )
        c.commit()

    def _decision(self, risk=0.25):
        return {
            "source": "G_DESK",
            "symbol": "EURUSD.x",
            "side": "BUY",
            "entry": 1.10,
            "stop": 1.095,
            "target": 1.11,
            "volume": 0.01,
            "risk_pct": risk,
            "valid_until": (datetime.now(timezone.utc) + timedelta(minutes=30)).isoformat(),
            "cancel_condition": "structure invalidated",
            "context": {"order_type": "BUY"},
        }

    def test_fresh_clean_snapshot_passes(self):
        self._snapshot()
        self.assertEqual(self.bridge.preflight_decision(self._decision()), [])

    def test_duplicate_and_hedge_are_blocked(self):
        self._snapshot(positions=[{
            "symbol": "EURUSD.x", "side": "SELL", "risk_usd": 3.0
        }])
        errors = self.bridge.preflight_decision(self._decision())
        self.assertIn("mt5_duplicate_active_symbol", errors)
        self.assertIn("goat_hedging_prohibited", errors)

    def test_floating_loss_guard_is_stricter_than_firm_limit(self):
        self._snapshot(equity=2455.0, floating=-21.0)
        errors = self.bridge.preflight_decision(self._decision())
        self.assertIn("goat_floating_loss_guard", errors)

    def test_aggregate_risk_guard_counts_manual_positions(self):
        self._snapshot(positions=[{
            "symbol": "GBPUSD.x", "side": "BUY", "risk_usd": 13.0
        }])
        errors = self.bridge.preflight_decision(self._decision(risk=0.25))
        self.assertIn("mt5_aggregate_risk_guard", errors)

    def test_command_queue_is_idempotent(self):
        self._snapshot()
        trade = {
            "trade_id": "FX-TEST",
            "symbol": "EURUSD.x",
            "side": "BUY",
            "entry": 1.10,
            "stop": 1.095,
            "target": 1.11,
            "volume": 0.01,
            "risk_pct": 0.25,
            "valid_until": (datetime.now(timezone.utc) + timedelta(minutes=20)).isoformat(),
            "cancel_condition": "invalidated",
            "context": {"order_type": "BUY"},
        }
        self.bridge._queue_command(trade)
        self.bridge._queue_command(trade)
        count = self.fx101.db().execute("SELECT COUNT(*) FROM mt5_commands WHERE trade_id='FX-TEST'").fetchone()[0]
        self.assertEqual(count, 1)


if __name__ == "__main__":
    unittest.main()
