import copy
import unittest
import dnb_history
import test_dnb_alerts as fixtures
from test_mt5_bridge import NOW

class HistoryTests(unittest.TestCase):
    setUp=fixtures.AlertTests.setUp
    tearDown=fixtures.AlertTests.tearDown
    def page(self,kind,items):
        return {'capture_id':'d'*32,'login':315307814,'server':'GoatFunded-Server','captured_at':NOW,
                'from_server_time':0,'to_server_time':NOW,'kind':kind,'page':0,'pages':1,'total':len(items),'items':items}
    def deal(self):
        return {'ticket':'800','order_ticket':'700','position_id':'900','magic':123,'comment':'dnb:fixture','symbol':'EURUSD.x',
                'type':0,'entry':0,'reason':3,'volume':.01,'price':1.1,'profit':0,'commission':-.07,'swap':0,'fee':0,'time':NOW}
    def test_complete_history_requires_both_kinds(self):
        self.assertFalse(dnb_history.ingest(self.page('orders',[]),NOW)['complete'])
        self.assertTrue(dnb_history.ingest(self.page('deals',[self.deal()]),NOW)['complete'])
        self.assertEqual(dnb_history.latest()['payload']['deals'],1)
    def test_partial_page_never_becomes_authoritative(self):
        p=self.page('deals',[self.deal()]);p.update(pages=2,total=2)
        self.assertFalse(dnb_history.ingest(p,NOW)['complete']);self.assertIsNone(dnb_history.latest())
    def test_duplicate_page_is_idempotent(self):
        p=self.page('deals',[self.deal()]);dnb_history.ingest(p,NOW);dnb_history.ingest(p,NOW)
        self.assertFalse(dnb_history.ingest(p,NOW)['complete'])
    def test_conflicting_duplicate_page_rejected(self):
        p=self.page('deals',[self.deal()]);dnb_history.ingest(p,NOW);p['items'][0]['volume']=.02
        with self.assertRaisesRegex(dnb_history.risk.Reject,'history_page_conflict'):dnb_history.ingest(p,NOW)
    def test_total_mismatch_rejected(self):
        p=self.page('deals',[self.deal()]);p['total']=2
        with self.assertRaisesRegex(dnb_history.risk.Reject,'history_total_conflict'):dnb_history.ingest(p,NOW)
    def test_commission_swap_fee_preserved(self):
        d=self.deal();d.update(profit=5,commission=-.1,swap=-.2,fee=-.3)
        dnb_history.ingest(self.page('orders',[]),NOW);dnb_history.ingest(self.page('deals',[d]),NOW)
        import json,mt5_store
        actual=json.loads(mt5_store.db().execute('SELECT payload FROM dnb_broker_deals WHERE ticket=?',('800',)).fetchone()['payload'])
        self.assertEqual(actual,d)
    def test_unknown_fields_rejected(self):
        p=self.page('deals',[self.deal()]);p['items'][0]['unknown']=True
        with self.assertRaises(dnb_history.risk.Reject):dnb_history.ingest(p,NOW)
