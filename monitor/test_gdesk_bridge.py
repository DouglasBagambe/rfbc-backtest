import importlib
import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch


class Response:
    def __init__(self, body): self.body=body
    def raise_for_status(self): pass
    def json(self): return self.body


class BridgeTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); os.environ.pop("TURSO_DATABASE_URL",None); os.environ.pop("TURSO_DB_URL",None); os.environ["FX101_DB_PATH"]=str(Path(self.tmp.name)/"bridge.db")
        import fx101, fx101_worker
        self.fx=importlib.reload(fx101); self.worker=importlib.reload(fx101_worker)
        self.fx.create_account({"name":"Synthetic","broker":"Test","account_type":"paper","base_currency":"USD","tracked_balance":100,"per_trade_risk_cap":1,"aggregate_risk_cap":1,"max_positions":1})
    def tearDown(self): self.fx.close_db(); self.tmp.cleanup()
    def body(self, result, **extra):
        return {"decision_id":"SYNTHETIC-"+result,"generated_at":datetime.now(timezone.utc).isoformat(),"result":result,"decisions":[],**extra}
    def consume(self, body):
        with patch.object(self.worker.requests,"get",return_value=Response(body)):
            self.worker._consume_gdesk_runtime_decision()
    def test_trade_and_duplicate_are_idempotent(self):
        decision={"symbol":"EURUSDc","side":"BUY","entry":1.1,"stop":1.09,"target":1.12,"volume":.01,"risk_pct":.5,"valid_until":(datetime.now(timezone.utc)+timedelta(hours=1)).isoformat(),"cancel_condition":"synthetic","confidence":"A","setup_name":"synthetic","regime":"test","session":"test","news_proximity":"unknown","exposure_note":"none","reasoning":"synthetic only","context":{}}
        body=self.body("TRADE",decisions=[decision]); self.consume(body); self.consume(body)
        self.assertEqual(len(self.fx.list_trades()),1)
        self.assertEqual(self.fx.db().execute("SELECT COUNT(*) FROM scans WHERE id=?",(body["decision_id"],)).fetchone()[0],1)
    def test_no_trade_and_system_failure_are_consumed(self):
        for result in ("NO_TRADE","SYSTEM_FAILURE"):
            body=self.body(result,message="synthetic test")
            self.consume(body)
            self.assertTrue(self.worker._bridge_marker_exists(body["decision_id"]))
    def test_stale_and_future_are_rejected_once(self):
        for result,age in (("NO_TRADE",-timedelta(hours=2)),("NO_TRADE",timedelta(minutes=10))):
            body=self.body(result); body["decision_id"]+="-"+str(age.total_seconds()); body["generated_at"]=(datetime.now(timezone.utc)+age).isoformat()
            self.consume(body); self.assertTrue(self.worker._bridge_marker_exists(body["decision_id"]))
            self.assertEqual(self.fx.db().execute("SELECT result FROM scans WHERE id=?",(body["decision_id"],)).fetchone()[0],"REJECTED")
