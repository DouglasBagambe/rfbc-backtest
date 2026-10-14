import json
import unittest
from unittest.mock import patch
import dnb_notifications as notices
import dnb_demo_execution as execution
import test_dnb_demo_scale as scale_fixtures
from test_mt5_bridge import NOW

class NotificationTests(unittest.TestCase):
    setUp=scale_fixtures.DemoScaleTests.setUp
    tearDown=scale_fixtures.DemoScaleTests.tearDown
    commission=scale_fixtures.DemoScaleTests.commission
    flags=scale_fixtures.DemoScaleTests.flags
    setup_winner=scale_fixtures.DemoScaleTests.setup_winner

    def test_broker_confirmed_fill_has_all_details_and_separate_demo_label(self):
        row,p,_,_=self.setup_winner();ids=execution.reconcile(NOW)
        self.assertEqual(len(ids),1)
        messages=[]
        self.assertEqual(notices.dispatch(ids[0],lambda text:(messages.append(text) or True,'200')),'SENT')
        text=messages[0]
        for expected in ('DEMO AUTO','G_DESK','EURUSD.x','BUY','Entry','SL','TP','Lots planned','risk $','risk input','Thesis','Thesis exposure','Command','order 700','deals 800'):
            self.assertIn(expected,text)
        self.assertIn('not a GOAT entry instruction',text)
        self.assertEqual(execution.reconcile(NOW+1),[])

    def test_delivery_ambiguity_survives_restart_without_duplicate_message(self):
        self.setup_winner();identifier=execution.reconcile(NOW)[0]
        self.assertEqual(notices.dispatch(identifier,lambda _:(_ for _ in ()).throw(TimeoutError())),'DELIVERY_UNKNOWN')
        import fx101
        fx101.close_db();calls=[]
        self.assertEqual(notices.dispatch(identifier,lambda text:calls.append(text)),'DELIVERY_UNKNOWN')
        self.assertEqual(calls,[])

    def test_notification_failure_rolls_back_broker_event_in_same_transaction(self):
        row,_,_,_=self.setup_winner()
        with patch.object(notices,'prepare',side_effect=RuntimeError('fixture_failure')):
            with self.assertRaises(RuntimeError):execution.reconcile(NOW)
        c=self.bridge.store.db();c.rollback()
        self.assertEqual(c.execute('SELECT COUNT(*) FROM dnb_demo_execution_events').fetchone()[0],0)
        self.assertEqual(len(execution.reconcile(NOW)),1)

    def test_actual_sl_change_has_a_new_broker_revision_notification(self):
        _,_,s,_=self.setup_winner();first=execution.reconcile(NOW)
        s['positions'][0]['sl']=1.0992
        import dnb_demo
        dnb_demo.snapshot(s,NOW)
        second=execution.reconcile(NOW)
        self.assertEqual(len(first),1);self.assertEqual(len(second),1);self.assertNotEqual(first,second)

    def test_deal_scan_order_does_not_fabricate_new_lifecycle_event(self):
        self.setup_winner();execution.reconcile(NOW)
        self.assertEqual(execution.reconcile(NOW),[])
