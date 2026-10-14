import json
import unittest
import dnb_demo
import dnb_demo_execution as execution
import dnb_demo_reset as reset
import dnb_history
import test_dnb_demo_execution as fixtures
import test_dnb_history as history_fixtures
from test_mt5_bridge import NOW,snapshot,item


class DemoResetTests(unittest.TestCase):
    setUp=fixtures.DemoExecutionTests.setUp
    tearDown=fixtures.DemoExecutionTests.tearDown
    commission=fixtures.DemoExecutionTests.commission
    flags=fixtures.DemoExecutionTests.flags
    decision=fixtures.DemoExecutionTests.decision

    def observe(self, at, *, balance=2500, positions=None):
        s=snapshot();s.update(login=dnb_demo.DEMO_LOGIN,server=dnb_demo.DEMO_SERVER,
                             captured_at=at,account_margin_mode=0,balance=balance,equity=balance,free_margin=balance,margin=0,floating_pnl=0)
        s['positions']=positions or []
        dnb_demo.snapshot(s,at)

    def history(self,at,items=None):
        helper=history_fixtures.HistoryTests()
        for kind in ('orders','deals'):
            p=helper.page(kind,items or [] if kind=='deals' else [])
            p.update(login=dnb_demo.DEMO_LOGIN,server=dnb_demo.DEMO_SERVER,
                     capture_id='e'*32,captured_at=at,to_server_time=at+7200)
            dnb_history.ingest(p,at,demo=True)

    def prepare(self):
        epoch=self.commission();boundary=epoch['payload']['valid_until']
        self.observe(boundary-5);self.observe(boundary+5);self.history(boundary+5)
        return epoch,boundary

    def test_flat_boundary_advances_daily_anchor_preserves_peak_and_reservations(self):
        epoch=self.commission()
        with self.flags():
            row=execution.queue(self.decision(),NOW)
            execution.submission_intent(fixtures.DemoExecutionTests.native_intent(self,row),NOW)
        boundary=epoch['payload']['valid_until']
        self.observe(boundary-5);self.observe(boundary+5);self.history(boundary+5)
        updated=execution.epoch(boundary+5)[1]
        self.assertEqual(updated['daily_anchor'],2500)
        self.assertEqual(updated['valid_until'],boundary+86400)
        self.assertGreaterEqual(updated['historical_peak'],epoch['payload']['historical_peak'])
        self.assertEqual(self.bridge.store.db().execute('SELECT state FROM dnb_demo_strategy_commands WHERE id=?',(row['id'],)).fetchone()[0],'INTENT')
        import fx101
        fx101.close_db()
        self.assertEqual(execution.epoch(boundary+6)[1],updated)
        self.assertEqual(self.bridge.store.db().execute('SELECT COUNT(*) FROM dnb_demo_reset_proofs').fetchone()[0],1)

    def test_outage_does_not_invent_reset_from_current_balance(self):
        epoch=self.commission();boundary=epoch['payload']['valid_until']
        self.observe(boundary+5);self.history(boundary+5)
        with self.assertRaisesRegex(self.bridge.risk.Reject,'verified_boundary'):execution.epoch(boundary+5)

    def test_open_exposure_cannot_be_valued_from_neighbouring_quotes(self):
        epoch=self.commission();boundary=epoch['payload']['valid_until']
        self.observe(boundary-5,positions=[item('EURUSD.x')]);self.observe(boundary+5)
        self.history(boundary+5)
        with self.assertRaisesRegex(self.bridge.risk.Reject,'open_exposure'):execution.epoch(boundary+5)

    def test_balance_change_rejects_reset(self):
        epoch=self.commission();boundary=epoch['payload']['valid_until']
        self.observe(boundary-5);self.observe(boundary+5,balance=2499);self.history(boundary+5)
        with self.assertRaisesRegex(self.bridge.risk.Reject,'balance_changed'):execution.epoch(boundary+5)

    def test_conflicting_boundary_observations_reject_reset(self):
        _,boundary=self.prepare();self.observe(boundary+5,balance=2499)
        with self.assertRaisesRegex(self.bridge.risk.Reject,'conflicting_boundary'):execution.epoch(boundary+5)

    def test_hidden_zero_profit_roundtrip_rejects_reset(self):
        _,boundary=self.prepare()
        deal=history_fixtures.HistoryTests().deal();deal['time']=boundary+7200
        c=self.bridge.store.db();c.execute('INSERT INTO dnb_demo_broker_deals VALUES (?,?,?)',(deal['ticket'],boundary+5,json.dumps(deal)));c.commit()
        with self.assertRaisesRegex(self.bridge.risk.Reject,'boundary_activity'):execution.epoch(boundary+5)

    def test_missing_multiple_boundaries_never_skips_losses(self):
        epoch,boundary=self.prepare()
        with self.assertRaisesRegex(self.bridge.risk.Reject,'multiple_boundaries'):execution.epoch(boundary+86400)

    def test_expiry_releases_only_never_submitted_command(self):
        self.commission()
        with self.flags():
            row=execution.queue(self.decision(),NOW)
            self.assertEqual(execution.next_command(NOW+31,'f'*64),'NONE')
        self.assertEqual(self.bridge.store.db().execute('SELECT state FROM dnb_demo_strategy_commands WHERE id=?',(row['id'],)).fetchone()[0],'EXPIRED')

    def test_expiry_never_releases_committed_intent(self):
        self.commission()
        with self.flags():
            row=execution.queue(self.decision(),NOW)
            execution.submission_intent(fixtures.DemoExecutionTests.native_intent(self,row),NOW)
            self.assertEqual(execution.next_command(NOW+31,'f'*64).split('|')[24],'INTENT')

    def test_working_pending_order_reconciles_before_history_order_exists(self):
        import hashlib
        self.commission()
        with self.flags():
            row=execution.queue(self.decision(),NOW)
            execution.submission_intent(fixtures.DemoExecutionTests.native_intent(self,row),NOW)
        p=json.loads(row['payload']);s=dnb_demo.latest(NOW)['payload']
        pending=item('EURUSD.x',volume=p['quote']['volume']);pending.update(ticket='700',order_type='BUY_LIMIT',
            magic=int(hashlib.sha256(('dnb:'+row['id']).encode()).hexdigest()[:15],16),comment='dnb:'+row['id'][:24])
        s['orders']=[pending];dnb_demo.snapshot(s,NOW)
        self.assertEqual(len(execution.reconcile(NOW)),1)
        self.assertEqual(self.bridge.store.db().execute('SELECT state FROM dnb_demo_strategy_commands WHERE id=?',(row['id'],)).fetchone()[0],'PENDING')
        self.assertEqual(execution.reconcile(NOW),[])
