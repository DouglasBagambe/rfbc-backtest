import json
import unittest
from unittest.mock import patch
import dnb_manual
import dnb_alerts
import dnb_demo
import dnb_demo_execution as execution
import dnb_history
import test_dnb_demo_execution as fixtures
import test_dnb_history as history_fixtures
from test_mt5_bridge import NOW,snapshot,item


class ManualTests(unittest.TestCase):
    setUp=fixtures.DemoExecutionTests.setUp
    tearDown=fixtures.DemoExecutionTests.tearDown
    commission=fixtures.DemoExecutionTests.commission
    decision=fixtures.DemoExecutionTests.decision
    flags=fixtures.DemoExecutionTests.flags

    def evidence(self, *, closed=False, magic=0, symbol='EURUSD', mixed=False):
        self.commission();decision=self.decision()
        dnb_alerts.dispatch(decision['trade_id'],lambda _:(True,'200'))
        s=snapshot();s.update(login=dnb_demo.DEMO_LOGIN,server=dnb_demo.DEMO_SERVER,account_margin_mode=0)
        if not closed:
            pos=item('EURUSD.x');pos.update(ticket='900',identifier='900');s['positions']=[pos]
        dnb_demo.snapshot(s,NOW)
        order={'ticket':'700','position_id':'900','magic':magic,'comment':'manual','symbol':symbol,
               'type':0,'state':4,'reason':0,'volume_initial':.01,'volume_current':0,'price':1.1002,
               'sl':self.d['stop'],'tp':self.d['target'],'stop_limit':0,'created_at':NOW,'done_at':NOW,'expires_at':0}
        deal=history_fixtures.HistoryTests().deal()
        deal.update(magic=magic,reason=0,symbol=symbol,comment='manual')
        deals=[deal]
        if closed:deals.append({**deal,'ticket':'801','order_ticket':'701','entry':1,'profit':2})
        if mixed:deals.append({**deal,'ticket':'802','order_ticket':'702'})
        helper=history_fixtures.HistoryTests()
        for kind,items in [('orders',[order]),('deals',deals)]:
            page=helper.page(kind,items);page.update(login=dnb_demo.DEMO_LOGIN,server=dnb_demo.DEMO_SERVER,capture_id='e'*32)
            dnb_history.ingest(page,NOW,demo=True)
        return {'trade_id':decision['trade_id'],'account_kind':'DEMO','order_ticket':'700'},decision

    def test_explicit_manual_binding_survives_restart_and_preserves_quarantine_while_open(self):
        body,_=self.evidence()
        result=dnb_manual.bind(body,NOW)
        self.assertEqual(result['state'],'MANUAL_BOUND');self.assertFalse(result['live_auto_authorised'])
        import fx101
        fx101.close_db()
        self.assertTrue(dnb_manual.bind(body,NOW)['idempotent'])
        with self.assertRaisesRegex(self.bridge.risk.Reject,'manual_alert'):dnb_alerts.require_reconciled('EURUSD.x')

    def test_already_closed_manual_fill_is_bound_without_fabricating_open_position(self):
        body,decision=self.evidence(closed=True)
        result=dnb_manual.bind(body,NOW)
        self.assertEqual(result['state'],'MANUAL_CLOSED')
        self.assertEqual(result['proof']['broker']['remaining_volume'],0)
        dnb_alerts.require_reconciled('EURUSD.x')
        with self.flags(),self.assertRaisesRegex(self.bridge.risk.Reject,'already_manually_executed'):
            execution.queue(decision,NOW)

    def test_similar_prices_never_clear_quarantine(self):
        body,_=self.evidence()
        with self.assertRaisesRegex(self.bridge.risk.Reject,'order_history_required'):
            dnb_manual.bind({**body,'order_ticket':'999'},NOW)
        self.assertEqual(self.bridge.store.db().execute('SELECT COUNT(*) FROM dnb_manual_bindings').fetchone()[0],0)

    def test_cross_account_and_automatic_entry_cannot_be_bound(self):
        body,_=self.evidence(magic=123)
        with self.assertRaisesRegex(self.bridge.risk.Reject,'fresh_account_history'):dnb_manual.bind({**body,'account_kind':'GOAT'},NOW)
        with self.assertRaisesRegex(self.bridge.risk.Reject,'entry_identity'):dnb_manual.bind(body,NOW)

    def test_wrong_symbol_and_mixed_netting_reject_binding(self):
        body,_=self.evidence(symbol='GBPUSD',mixed=True)
        with self.assertRaisesRegex(self.bridge.risk.Reject,'proposal_conflict'):dnb_manual.bind(body,NOW)

    def test_mixed_manual_position_rejects_binding(self):
        body,_=self.evidence(mixed=True)
        with self.assertRaisesRegex(self.bridge.risk.Reject,'mixed_position'):dnb_manual.bind(body,NOW)

    def test_incomplete_or_stale_history_never_resolves_manual_uncertainty(self):
        body,_=self.evidence()
        with self.assertRaisesRegex(self.bridge.risk.Reject,'fresh_account_history'):dnb_manual.bind(body,NOW+61)

    def test_conflicting_rebind_never_replaces_order_identity(self):
        body,_=self.evidence();dnb_manual.bind(body,NOW)
        with self.assertRaisesRegex(self.bridge.risk.Reject,'binding_conflict'):dnb_manual.bind({**body,'order_ticket':'701'},NOW)

    def test_broker_confirmed_manual_exit_clears_only_bound_alert(self):
        body,_=self.evidence();dnb_manual.bind(body,NOW)
        s=dnb_demo.latest(NOW)['payload'];s['positions']=[];dnb_demo.snapshot(s,NOW)
        c=self.bridge.store.db()
        deal=json.loads(c.execute('SELECT payload FROM dnb_demo_broker_deals WHERE ticket=?',('800',)).fetchone()[0])
        deal.update(ticket='801',order_ticket='701',entry=1,profit=2)
        c.execute('INSERT INTO dnb_demo_broker_deals VALUES (?,?,?)',('801',NOW,json.dumps(deal)));c.commit()
        dnb_manual.reconcile(NOW)
        self.assertEqual(c.execute('SELECT state FROM dnb_alert_intents WHERE trade_id=?',(body['trade_id'],)).fetchone()[0],'MANUAL_CLOSED')
