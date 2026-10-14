import copy
import unittest
import dnb_demo
import dnb_history
import test_dnb_alerts as fixtures
import test_dnb_history as history_fixtures
from test_mt5_bridge import NOW,snapshot

class DemoObservationTests(unittest.TestCase):
    setUp=fixtures.AlertTests.setUp
    tearDown=fixtures.AlertTests.tearDown

    def demo(self):
        body=snapshot();body.update(login=dnb_demo.DEMO_LOGIN,server=dnb_demo.DEMO_SERVER)
        return body

    def test_demo_snapshot_cannot_replace_funded_snapshot(self):
        dnb_demo.snapshot(self.demo(),NOW)
        self.assertEqual(dnb_demo.latest(NOW)['payload']['login'],dnb_demo.DEMO_LOGIN)
        self.assertIsNone(self.bridge.latest_snapshot())

    def test_funded_account_rejected_by_demo_route(self):
        with self.assertRaises(self.bridge.risk.Reject):dnb_demo.snapshot(snapshot(),NOW)

    def test_demo_account_rejected_by_default_funded_validator(self):
        with self.assertRaises(self.bridge.risk.Reject):self.bridge.risk.validate_snapshot(self.demo(),NOW)

    def test_history_same_ticket_is_isolated_per_account(self):
        helper=history_fixtures.HistoryTests()
        order=helper.page('orders',[]);deal=helper.page('deals',[helper.deal()])
        dnb_history.ingest(order,NOW);dnb_history.ingest(deal,NOW)
        for p in (order,deal):
            p.update(login=dnb_demo.DEMO_LOGIN,server=dnb_demo.DEMO_SERVER)
            if p['kind']=='deals':p['items'][0]['profit']=7
            dnb_history.ingest(p,NOW,demo=True)
        c=self.bridge.store.db()
        self.assertIn('"profit":0',c.execute('SELECT payload FROM dnb_broker_deals WHERE ticket=?',('800',)).fetchone()['payload'])
        self.assertIn('"profit":7',c.execute('SELECT payload FROM dnb_demo_broker_deals WHERE ticket=?',('800',)).fetchone()['payload'])
        self.assertIsNotNone(dnb_history.latest(demo=True))

    def test_history_cannot_use_demo_flag_with_funded_binding(self):
        helper=history_fixtures.HistoryTests()
        with self.assertRaisesRegex(self.bridge.risk.Reject,'account_binding'):
            dnb_history.ingest(helper.page('orders',[]),NOW,demo=True)
