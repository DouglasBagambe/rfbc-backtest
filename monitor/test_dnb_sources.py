import copy
import json
import unittest
from datetime import datetime, timezone
from unittest.mock import patch
import dnb_sources as sources
import dnb_alerts
import test_dnb_alerts as fixtures
from test_mt5_bridge import NOW

def iso(stamp): return datetime.fromtimestamp(stamp,timezone.utc).isoformat()

class SourceTests(unittest.TestCase):
    setUp = fixtures.AlertTests.setUp
    tearDown = fixtures.AlertTests.tearDown

    def body(self, result='TRADE'):
        return {'decision_id':'GDESK-FIXTURE-1','generated_at':iso(NOW),'result':result,
                'decisions':[{**self.d,'cancel_condition':'Price below structure SL'}] if result=='TRADE' else [],
                'context':{'market_state':'MARKET_OPEN','freshness':'FRESH','symbols_received':18,
                           'symbols_reported':18,'validation_errors':[], 'source_generated_at':iso(NOW-120),
                           'latest_completed_bar':iso(((NOW-120)//3600-1)*3600)}}

    def test_cap_risk_preserve_structure_ignore_requested_volume(self):
        b=self.body(); b['decisions'][0].update(risk_pct=2.5,volume=3)
        out=sources.gdesk_decisions(b,NOW)[0]
        self.assertEqual(out['risk_pct'],.25)
        self.assertEqual(out['stop'],self.d['stop'])
        self.assertEqual(out['trade_id'],b['decision_id'])

    def test_market_closed_never_promoted_to_trade(self):
        b=self.body();b['context']['market_state']='MARKET_CLOSED'
        with self.assertRaisesRegex(self.bridge.risk.Reject,'source_context'):sources.gdesk_decisions(b,NOW)

    def test_api_quota_fallback_still_validates_publication_freshness(self):
        import requests
        from unittest.mock import Mock
        failed=Mock();failed.raise_for_status.side_effect=requests.HTTPError('quota')
        raw=Mock();raw.content=json.dumps(self.body()).encode()
        with patch.object(sources.requests,'get',side_effect=[failed,raw]) as get:
            body=sources.fetch_gdesk(NOW)
        self.assertEqual(get.call_args.args[0],sources.RAW_MAILBOX)
        self.assertEqual(len(sources.gdesk_decisions(body,NOW)),1)
        with self.assertRaisesRegex(self.bridge.risk.Reject,'source_stale'):
            sources.gdesk_decisions(body,NOW+3601)

    def test_one_stale_bar_blocks_even_when_source_claims_fresh(self):
        b=self.body();b['context']['latest_completed_bar']=iso(((NOW-120)//3600-2)*3600)
        with self.assertRaisesRegex(self.bridge.risk.Reject,'source_bar_stale'):sources.gdesk_decisions(b,NOW)

    def test_missing_context_and_expired_or_future_source_fail_closed(self):
        for mutation in (lambda b:b.pop('context'), lambda b:b.update(generated_at=iso(NOW+1)),
                         lambda b:b.update(generated_at=iso(NOW-3601))):
            b=self.body();mutation(b)
            with self.assertRaises(self.bridge.risk.Reject):sources.gdesk_decisions(b,NOW)

    def test_no_trade_and_system_issue_never_make_alerts(self):
        for result in ('NO_TRADE','SYSTEM_FAILURE'):
            b=self.body(result);b['decision_id']+=result
            self.assertEqual(sources.ingest_gdesk(b,NOW),[])
        self.assertEqual(self.bridge.store.db().execute('SELECT COUNT(*) FROM dnb_alert_intents').fetchone()[0],0)

    def test_receipt_restart_repairs_alert_without_redelivery(self):
        b=self.body();sources.ingest_gdesk(b,NOW)
        calls=[]
        sender=lambda text:(calls.append(text) or True,'200')
        self.assertEqual(dnb_alerts.dispatch(b['decision_id'],sender),'SENT')
        self.bridge.store.db().close()
        import fx101
        fx101.close_db()
        sources.ingest_gdesk(b,NOW+1)
        self.assertEqual(dnb_alerts.dispatch(b['decision_id'],sender),'SENT')
        self.assertEqual(len(calls),1)

    def test_source_id_conflict_does_not_replace_first_stop(self):
        b=self.body();sources.ingest_gdesk(b,NOW);b['decisions'][0]['stop']=1.098
        with self.assertRaisesRegex(self.bridge.risk.Reject,'source_id_conflict'):sources.ingest_gdesk(b,NOW)

    def rfbc(self):
        return [{'pair':p,'action':{'kind':'trade' if p=='USDJPY' else 'move_be','direction':'BUY',
                    'entry':150,'stop':149.8,'target':150.4,'risk_pct':.1,
                    'close_dt':iso(NOW-120),'quote_dt':iso(NOW-2)}} for p in ('USDJPY','AUDJPY')]

    def test_rfbc_only_real_entry_event_not_inferred_management(self):
        out=sources.rfbc_decisions(self.rfbc(),NOW)
        self.assertEqual(len(out),1);self.assertEqual(out[0]['symbol'],'USDJPY.x')
        self.assertEqual(out[0]['stop'],149.8)
        self.assertEqual(out[0]['risk_pct'],.25)
        self.assertEqual(out[0]['context']['reference_risk_pct'],.1)

    def test_rfbc_risk_rejection_not_promoted(self):
        rows=self.rfbc();rows[0]['action']['kind']='skip_risk'
        self.assertEqual(sources.rfbc_decisions(rows,NOW),[])

    def test_rfbc_restart_quote_change_cannot_make_second_alert(self):
        first=sources.rfbc_decisions(self.rfbc(),NOW)
        sources.ingest_rfbc(first,NOW)
        rows=self.rfbc();rows[0]['action']['entry']=150.01
        second=sources.rfbc_decisions(rows,NOW+1)
        self.assertEqual(sources.ingest_rfbc(second,NOW+1)[0]['entry'],150)
        self.assertEqual(self.bridge.store.db().execute('SELECT COUNT(*) FROM dnb_alert_intents').fetchone()[0],1)

    def test_rfbc_requires_full_frozen_universe_and_fresh_quote(self):
        rows=self.rfbc();rows[0]['action']['quote_dt']=iso(NOW-61)
        with self.assertRaises(self.bridge.risk.Reject):sources.rfbc_decisions(rows,NOW)
        with self.assertRaises(self.bridge.risk.Reject):sources.rfbc_decisions(rows[:1],NOW)
