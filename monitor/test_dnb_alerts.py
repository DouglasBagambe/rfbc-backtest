import importlib
import json
import os
import tempfile
import unittest
from datetime import datetime, timezone
from unittest.mock import patch
from flask import Flask
import dnb_alerts
from test_mt5_bridge import snapshot,NOW

class AlertTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.env=patch.dict(os.environ,{'FX101_DB_PATH':self.temp.name+'/test.db',
            'DNB_DATABASE_URL':'','DNB_REQUIRE_DURABLE':'0','FX101_MT5_BRIDGE_ENABLED':'1',
            'FX101_MT5_EXECUTION_MODE':'SHADOW','FX101_MT5_KILL_SWITCH':'0'})
        self.env.start()
        import fx101,mt5_bridge
        fx101.close_db();importlib.reload(fx101)
        self.bridge=mt5_bridge;self.clock=patch.object(mt5_bridge,'clock',return_value=NOW);self.clock.start()
        self.app=Flask(__name__);self.ctx=self.app.app_context();self.ctx.push()
        self.d={'trade_id':'ALERT-1','source':'G_DESK','symbol':'EURUSD.x','side':'BUY',
                'entry':1.1002,'stop':1.099,'target':1.1022,'risk_pct':.25,
                'valid_until':datetime.fromtimestamp(NOW+30,timezone.utc).isoformat()}
    def tearDown(self):
        import fx101
        fx101.close_db();self.ctx.pop();self.clock.stop();self.env.stop();self.temp.cleanup()
    def test_offline_analysis_alert_does_not_authorise_volume(self):
        row=dnb_alerts.prepare(self.d,NOW);messages=[]
        def sender(text):messages.append(text);return True,'200'
        self.assertEqual(dnb_alerts.dispatch('ALERT-1',sender),'SENT')
        self.assertIn('No lot size is authorised',messages[0]);self.assertIn('Thesis: ALERT-1',messages[0])
        self.assertFalse(json.loads(row['payload'])['broker_risk_authorised'])
    def test_conflicting_duplicate_alert(self):
        dnb_alerts.prepare(self.d,NOW)
        with self.assertRaisesRegex(self.bridge.risk.Reject,'duplicate_alert_conflict'):
            dnb_alerts.prepare({**self.d,'stop':1.0989},NOW)
    def test_lost_telegram_response_blocks_automated_reentry(self):
        dnb_alerts.prepare(self.d,NOW)
        def timeout(_):raise TimeoutError('private_transport_detail')
        self.assertEqual(dnb_alerts.dispatch('ALERT-1',timeout),'DELIVERY_UNKNOWN')
        with self.assertRaisesRegex(self.bridge.risk.Reject,'manual_alert_requires_broker_history'):
            self.bridge._queue_command(self.d,synthetic=True)
    def test_restart_does_not_redeliver_ambiguous_alert(self):
        dnb_alerts.prepare(self.d,NOW);dnb_alerts.dispatch('ALERT-1',lambda _:(False,'500'))
        import fx101
        fx101.close_db();calls=[]
        self.assertEqual(dnb_alerts.dispatch('ALERT-1',lambda x:calls.append(x)),'DELIVERY_UNKNOWN')
        self.assertEqual(calls,[])
    def test_manual_position_candidate_does_not_guess_fill_identity(self):
        dnb_alerts.prepare(self.d,NOW);dnb_alerts.dispatch('ALERT-1',lambda _:(True,'200'))
        from test_mt5_bridge import item
        s=snapshot();s['positions']=[item('EURUSD.x')]
        out=dnb_alerts.reconnect_candidates(s)
        self.assertEqual(out[0]['candidate_tickets'],['12345']);self.assertTrue(out[0]['history_reconciliation_required'])
    def test_empty_snapshot_does_not_clear_manual_execution_uncertainty(self):
        dnb_alerts.prepare(self.d,NOW);dnb_alerts.dispatch('ALERT-1',lambda _:(True,'200'))
        self.assertTrue(dnb_alerts.reconnect_candidates(snapshot())[0]['history_reconciliation_required'])
    def test_expired_alert_is_not_sent(self):
        dnb_alerts.prepare(self.d,NOW)
        with patch.object(self.bridge,'clock',return_value=NOW+31):
            self.assertEqual(dnb_alerts.dispatch('ALERT-1',lambda _:self.fail('expired alert sent')),'EXPIRED')
    def test_scale_reservation_survives_restart_and_lost_ack(self):
        from test_dnb_thesis import ThesisTests
        import dnb_thesis,fx101
        fixture=ThesisTests();fixture.setUp()
        first=dnb_thesis.reserve_scale_in(fixture.s,fixture.c,fixture.proof,NOW)
        fx101.close_db()
        second=dnb_thesis.reserve_scale_in(fixture.s,fixture.c,fixture.proof,NOW)
        self.assertEqual(first,second)
        count=fx101.db().execute('SELECT COUNT(*) FROM dnb_thesis_legs').fetchone()[0]
        self.assertEqual(count,2)
    def test_ambiguous_scale_submission_blocks_another_add_on(self):
        from test_dnb_thesis import ThesisTests
        import dnb_thesis
        fixture=ThesisTests();fixture.setUp()
        dnb_thesis.reserve_scale_in(fixture.s,fixture.c,fixture.proof,NOW)
        fixture.c['command_id']='c'*32;fixture.proof['confirmation_id']='SECOND-CONFIRMATION'
        with self.assertRaisesRegex(self.bridge.risk.Reject,'unresolved_thesis_submission'):
            dnb_thesis.reserve_scale_in(fixture.s,fixture.c,fixture.proof,NOW)
