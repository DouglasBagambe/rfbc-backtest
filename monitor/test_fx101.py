import importlib, os, tempfile, unittest
from pathlib import Path

class Fx101Tests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); os.environ["FX101_DB_PATH"]=str(Path(self.tmp.name)/"x.db")
        import fx101; self.m=importlib.reload(fx101)
        self.m.create_account({"name":"Test account","broker":"Test","account_type":"paper","base_currency":"USD","tracked_balance":100,"per_trade_risk_cap":1,"aggregate_risk_cap":1,"max_positions":1})
    def tearDown(self): self.tmp.cleanup()
    def decision(self): return {"source":"G_DESK","symbol":"EURUSDc","side":"BUY","entry":1.1,"stop":1.09,"target":1.12,"volume":0.01,"risk_pct":0.5,"valid_until":"2026-12-01T00:00:00Z","cancel_condition":"close below level","confidence":"A","setup_name":"test"}
    def test_persist_idempotent_and_lifecycle(self):
        ok,status,t=self.m.persist_decision(self.decision()); self.assertTrue(ok); self.assertEqual(status,"signalled")
        ok,status,_=self.m.persist_decision(self.decision()); self.assertEqual(status,"idempotent_existing")
        self.assertEqual(self.m.transition(t["trade_id"],"PLACED")["state"],"PLACED")
        self.assertEqual(self.m.transition(t["trade_id"],"OPEN")["state"],"OPEN")
        self.assertEqual(self.m.transition(t["trade_id"],"WON",1.12)["state"],"WON")
    def test_geometry_and_correlation_gate(self):
        d=self.decision(); d["stop"]=1.11; ok,status,_=self.m.persist_decision(d); self.assertFalse(ok); self.assertIn("invalid_sltp_geometry",status)
        ok,_,t=self.m.persist_decision(self.decision()); self.m.transition(t["trade_id"],"PLACED")
        d={**self.decision(),"trade_id":"OTHER","symbol":"GBPUSDc"}; ok,status,_=self.m.persist_decision(d); self.assertFalse(ok); self.assertIn("no_eligible_account",status)
    def test_price_manager_marks_target(self):
        ok,_,t=self.m.persist_decision(self.decision()); self.m.transition(t["trade_id"],"PLACED")
        changed=self.m.manage_prices({"EURUSDc":1.12}); self.assertEqual(changed[0]["state"],"WON")
    def test_empty_adapter_response_is_no_trade(self):
        ok,status,accepted=self.m.ingest_desk_response({"decisions":[]}); self.assertTrue(ok); self.assertEqual(status,"NO_TRADE"); self.assertEqual(accepted,[])
    def test_reconciliation_preserves_tracked_balance(self):
        account=self.m.list_accounts()[0]; result=self.m.reconcile_account(account["id"], 103, "manual check")
        self.assertEqual(result["tracked_balance"], 100); self.assertEqual(result["drift"], 3)
