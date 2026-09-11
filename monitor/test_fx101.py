import importlib, os, tempfile, unittest
from pathlib import Path

class Fx101Tests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); os.environ["FX101_DB_PATH"]=str(Path(self.tmp.name)/"x.db")
        import fx101; self.m=importlib.reload(fx101)
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
        d={**self.decision(),"trade_id":"OTHER","symbol":"GBPUSDc"}; ok,status,_=self.m.persist_decision(d); self.assertFalse(ok); self.assertIn("position_limit",status)
    def test_price_manager_marks_target(self):
        ok,_,t=self.m.persist_decision(self.decision()); self.m.transition(t["trade_id"],"PLACED")
        changed=self.m.manage_prices({"EURUSDc":1.12}); self.assertEqual(changed[0]["state"],"WON")
