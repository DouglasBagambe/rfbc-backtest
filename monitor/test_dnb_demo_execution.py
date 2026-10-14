import copy
import json
import os
import unittest
from unittest.mock import patch
import dnb_demo_execution as execution
import dnb_demo
import dnb_history
import dnb_sources
import test_dnb_sources as source_fixtures
import test_dnb_history as history_fixtures
import test_dnb_alerts as fixtures
from test_mt5_bridge import NOW,snapshot

class DemoExecutionTests(unittest.TestCase):
    setUp=fixtures.AlertTests.setUp
    tearDown=fixtures.AlertTests.tearDown

    def commission(self):
        s=snapshot();s.update(login=dnb_demo.DEMO_LOGIN,server=dnb_demo.DEMO_SERVER,account_margin_mode=0)
        dnb_demo.snapshot(s,NOW)
        helper=history_fixtures.HistoryTests()
        for kind in ('orders','deals'):
            p=helper.page(kind,[]);p.update(login=dnb_demo.DEMO_LOGIN,server=dnb_demo.DEMO_SERVER)
            dnb_history.ingest(p,NOW,demo=True)
        return execution.initialise_epoch(NOW)

    def decision(self):
        helper=source_fixtures.SourceTests();helper.d=self.d
        body=helper.body();body['decisions'][0]['context']={'order_type':'BUY','machine_cancel':{'kind':'price_below','price':1.0985}}
        return dnb_sources.ingest_gdesk(body,NOW)[0]

    def flags(self):return patch.dict(os.environ,{'DNB_DEMO_EXECUTION_ENABLED':'1','DNB_DEMO_KILL_SWITCH':'0','FX101_MT5_BRIDGE_TOKEN':'b'*64})

    def test_epoch_requires_real_fresh_demo_snapshot_and_complete_history(self):
        self.bridge._ensure_schema()
        with self.assertRaisesRegex(self.bridge.risk.Reject,'demo_fresh_history'):execution.initialise_epoch(NOW)
        value=self.commission()['payload']
        self.assertEqual(value['login'],dnb_demo.DEMO_LOGIN)
        self.assertEqual(value['purpose'],'DEMO_PROSPECTIVE_VALIDATION')
        self.assertIsNone(self.bridge.latest_snapshot())

    def test_epoch_cannot_be_reset_from_current_balance(self):
        self.commission()
        s=snapshot();s.update(login=dnb_demo.DEMO_LOGIN,server=dnb_demo.DEMO_SERVER,captured_at=NOW+86401,account_margin_mode=0)
        dnb_demo.snapshot(s,NOW+86401)
        helper=history_fixtures.HistoryTests()
        for kind in ('orders','deals'):
            p=helper.page(kind,[]);p.update(login=dnb_demo.DEMO_LOGIN,server=dnb_demo.DEMO_SERVER,capture_id='e'*32,captured_at=NOW+86401)
            dnb_history.ingest(p,NOW+86401,demo=True)
        with self.assertRaisesRegex(self.bridge.risk.Reject,'reset_requires_verified_boundary'):execution.initialise_epoch(NOW+86401)

    def test_genuine_signal_reservation_survives_restart_and_is_not_funded(self):
        self.commission();decision=self.decision()
        with self.flags():
            first=execution.queue(decision,NOW)
            import fx101
            fx101.close_db()
            again=execution.queue(decision,NOW+1)
        self.assertEqual(first['id'],again['id'])
        self.assertEqual(json.loads(first['payload'])['login'],dnb_demo.DEMO_LOGIN)
        self.assertFalse(json.loads(first['payload'])['synthetic'])
        self.assertEqual(self.bridge.store.db().execute('SELECT COUNT(*) FROM mt5_v2_commands').fetchone()[0],0)

    def test_kill_switch_blocks_even_eligible_demo_signal(self):
        self.commission();decision=self.decision()
        with self.assertRaisesRegex(self.bridge.risk.Reject,'demo_execution_killed'):execution.queue(decision,NOW)

    def test_fake_source_and_changed_structure_are_rejected(self):
        self.commission();decision=self.decision()
        with self.flags():
            with self.assertRaisesRegex(self.bridge.risk.Reject,'genuine_source_receipt'):
                execution.queue({**decision,'source_receipt_id':'missing'},NOW)
            with self.assertRaisesRegex(self.bridge.risk.Reject,'source_proposal_conflict'):
                execution.queue({**decision,'stop':1.098},NOW)

    def test_unresolved_submission_blocks_other_signal(self):
        self.commission();decision=self.decision()
        with self.flags():
            execution.queue(decision,NOW)
            with self.assertRaisesRegex(self.bridge.risk.Reject,'unresolved'):
                execution.queue({**decision,'trade_id':'another'},NOW)

    def native_intent(self,row):
        p=json.loads(row['payload'])
        return {'command_id':row['id'],'login':dnb_demo.DEMO_LOGIN,'server':dnb_demo.DEMO_SERVER,
                'fingerprint':'a'*64,'symbol':p['symbol'],'order_type':p['order_type'],
                'volume':p['quote']['volume'],'entry':p['quote']['entry'],'sl':p['sl'],'tp':p['tp']}

    def test_remote_intent_commit_lost_response_restart_is_idempotent(self):
        self.commission();decision=self.decision()
        with self.flags():
            row=execution.queue(decision,NOW);body=self.native_intent(row)
            self.assertEqual(execution.submission_intent(body,NOW)['state'],'INTENT')
            import fx101
            fx101.close_db()
            self.assertTrue(execution.submission_intent(body,NOW+1)['idempotent'])
            wire=execution.next_command(NOW+1,'f'*64).split('|')
            self.assertEqual(wire[0],'DNBdemo1');self.assertEqual(wire[24],'INTENT')
            self.assertEqual(wire[3],str(dnb_demo.DEMO_LOGIN))

    def test_changed_native_intent_never_replaces_committed_request(self):
        self.commission();decision=self.decision()
        with self.flags():
            row=execution.queue(decision,NOW);body=self.native_intent(row)
            execution.submission_intent(body,NOW)
            with self.assertRaisesRegex(self.bridge.risk.Reject,'intent_conflict'):
                execution.submission_intent({**body,'fingerprint':'b'*64},NOW+1)

    def test_native_ack_without_intent_cannot_claim_a_broker_execution(self):
        self.commission();decision=self.decision()
        with self.flags():row=execution.queue(decision,NOW)
        ack={'command_id':row['id'],'login':dnb_demo.DEMO_LOGIN,'server':dnb_demo.DEMO_SERVER,
             'status':'ACCEPTED','order_ticket':'700','deal_ticket':'800','volume':.01,'risk_usd':1,'detail':'accepted'}
        with self.assertRaisesRegex(self.bridge.risk.Reject,'demo_intent_required'):execution.acknowledge(ack,NOW)

    def test_lost_ack_recovery_does_not_erase_intent_or_requeue_signal(self):
        self.commission();decision=self.decision()
        with self.flags():
            row=execution.queue(decision,NOW);execution.submission_intent(self.native_intent(row),NOW)
        ack={'command_id':row['id'],'login':dnb_demo.DEMO_LOGIN,'server':dnb_demo.DEMO_SERVER,
             'status':'UNRESOLVED','order_ticket':'0','deal_ticket':'0','volume':.01,'risk_usd':1,'detail':'response_lost'}
        execution.acknowledge(ack,NOW)
        recovered={**ack,'status':'RECOVERED','order_ticket':'700','deal_ticket':'800','detail':'broker_identity_recovered'}
        execution.acknowledge(recovered,NOW+1)
        self.assertTrue(execution.acknowledge(recovered,NOW+2)['idempotent'])
        with self.flags():self.assertEqual(execution.queue(decision,NOW+2)['id'],row['id'])
        self.assertEqual(self.bridge.store.db().execute('SELECT COUNT(*) FROM dnb_demo_submission_intents').fetchone()[0],1)

    def test_server_kill_hides_commands_but_allows_durable_late_receipt(self):
        self.commission();decision=self.decision()
        with self.flags():
            row=execution.queue(decision,NOW);execution.submission_intent(self.native_intent(row),NOW)
        self.assertEqual(execution.next_command(NOW,'f'*64),'NONE')
        ack={'command_id':row['id'],'login':dnb_demo.DEMO_LOGIN,'server':dnb_demo.DEMO_SERVER,
             'status':'UNRESOLVED','order_ticket':'0','deal_ticket':'0','volume':.01,'risk_usd':1,'detail':'response_lost'}
        self.assertTrue(execution.acknowledge(ack,NOW)['ok'])

    def test_no_scale_in_bypass_by_boolean_or_addon_count(self):
        self.commission();decision=self.decision()
        with self.flags(),self.assertRaisesRegex(self.bridge.risk.Reject,'source_proposal_conflict'):
            execution.queue({**decision,'scale_in_number':1},NOW)

    def test_planned_news_window_profit_cap_reduces_volume_never_structure(self):
        self.commission();helper=source_fixtures.SourceTests();helper.d=self.d
        body=helper.body();body['decisions'][0].update(target=1.12,context={'order_type':'BUY','machine_cancel':{'kind':'price_below','price':1.0985}})
        decision=dnb_sources.ingest_gdesk(body,NOW)[0]
        with self.flags():row=execution.queue(decision,NOW)
        p=json.loads(row['payload']);self.assertEqual(p['tp'],1.12);self.assertEqual(p['sl'],self.d['stop'])
        spec=dnb_demo.latest(NOW)['payload']['symbols']['EURUSD.x']
        tp_risk=abs(p['tp']-p['quote']['entry'])/spec['tick_size']*spec['tick_value_profit']*p['quote']['volume']
        self.assertLessEqual(tp_risk,25)
