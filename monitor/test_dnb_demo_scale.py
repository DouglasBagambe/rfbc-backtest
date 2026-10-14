import copy
import hashlib
import json
import unittest
import dnb_demo
import dnb_history
import dnb_sources
import dnb_demo_execution as execution
import test_dnb_demo_execution as fixtures
import test_dnb_sources as source_fixtures
from test_mt5_bridge import NOW,snapshot,item

class DemoScaleTests(unittest.TestCase):
    setUp=fixtures.DemoExecutionTests.setUp
    tearDown=fixtures.DemoExecutionTests.tearDown
    commission=fixtures.DemoExecutionTests.commission
    flags=fixtures.DemoExecutionTests.flags

    def setup_winner(self):
        self.commission()
        h=source_fixtures.SourceTests();h.d=self.d
        b=h.body();b['decision_id']='GDESK-SCALE-INITIAL'
        b['decisions'][0].update(target=1.104,context={'order_type':'BUY','machine_cancel':{'kind':'price_below','price':1.0985}})
        d=dnb_sources.ingest_gdesk(b,NOW)[0]
        with self.flags():row=execution.queue(d,NOW)
        p=json.loads(row['payload']);magic=int(hashlib.sha256(('dnb:'+row['id']).encode()).hexdigest()[:15],16)
        c=self.bridge.store.db()
        c.execute("UPDATE dnb_demo_strategy_commands SET state='OPEN',created_at=? WHERE id=?",(NOW-3700,row['id']))
        order={'ticket':'700','position_id':'900','magic':magic,'comment':'dnb:'+row['id'][:24],'symbol':'EURUSD',
               'type':0,'state':4,'reason':3,'volume_initial':p['quote']['volume'],'volume_current':0,'price':1.1002,
               'sl':self.d['stop'],'tp':1.104,'stop_limit':0,'created_at':NOW-3700,'done_at':NOW-3700,'expires_at':0}
        deal={'ticket':'800','order_ticket':'700','position_id':'900','magic':magic,'comment':order['comment'],'symbol':'EURUSD',
              'type':0,'entry':0,'reason':3,'volume':p['quote']['volume'],'price':1.1002,'profit':0,'commission':0,'swap':0,'fee':0,'time':NOW-3700}
        c.execute('INSERT INTO dnb_demo_broker_orders VALUES (?,?,?)',('700',NOW,json.dumps(order)))
        c.execute('INSERT INTO dnb_demo_broker_deals VALUES (?,?,?)',('800',NOW,json.dumps(deal)));c.commit()
        s=snapshot();s.update(login=dnb_demo.DEMO_LOGIN,server=dnb_demo.DEMO_SERVER,account_margin_mode=0)
        pos=item('EURUSD.x',volume=p['quote']['volume']);pos.update(ticket='900',identifier='900',entry=1.1002,sl=self.d['stop'],tp=1.104,profit=2,magic=magic)
        s['positions']=[pos];s['symbols']['EURUSD.x'].update(bid=1.1007,ask=1.1008)
        s.update(equity=s['balance']+2,free_margin=s['balance']+2,floating_pnl=2)
        dnb_demo.snapshot(s,NOW)
        return row,p,s,b

    def scale_signal(self,initial):
        h=source_fixtures.SourceTests();h.d=self.d
        b=h.body();b['decision_id']='GDESK-SCALE-ADD1'
        b['decisions'][0].update(entry=1.1008,target=1.104,thesis_id=initial['thesis_id'],scale_in_number=1,
           context={'order_type':'BUY','machine_cancel':{'kind':'price_below','price':1.0985},'thesis_valid':True,'fresh_structure_confirmed':True})
        return b

    def test_profitable_netting_scale_preserves_old_protection_and_bounded_money(self):
        row,p,s,_=self.setup_winner();d=dnb_sources.ingest_gdesk(self.scale_signal(p),NOW)[0]
        with self.flags():addition=execution.queue(d,NOW)
        q=json.loads(addition['payload'])
        self.assertEqual(q['thesis_id'],p['thesis_id']);self.assertNotEqual(addition['id'],row['id'])
        self.assertEqual(q['scale_in_number'],1);self.assertEqual(q['sl'],p['sl']);self.assertEqual(q['tp'],p['tp'])
        self.assertLessEqual(q['quote']['risk_usd'],p['quote']['risk_usd'])
        self.assertEqual(q['scale_proof']['legs'][0]['command_id'],row['id'])
        with self.flags():
            self.assertEqual(execution.queue(d,NOW+1)['id'],addition['id'])
            native=fixtures.DemoExecutionTests.native_intent(self,addition)
            self.assertTrue(execution.submission_intent(native,NOW)['ok'])

    def test_losing_position_and_unmapped_manual_entry_are_rejected(self):
        _,p,s,_=self.setup_winner();d=dnb_sources.ingest_gdesk(self.scale_signal(p),NOW)[0]
        s['positions'][0]['profit']=-.1
        dnb_demo.snapshot(s,NOW)
        with self.flags(),self.assertRaisesRegex(self.bridge.risk.Reject,'losing_leg'):execution.queue(d,NOW)
        self.bridge.store.db().rollback()
        s['positions'][0]['profit']=2;s['positions'].append({**s['positions'][0],'ticket':'901','identifier':'901','magic':0})
        dnb_demo.snapshot(s,NOW)
        with self.flags(),self.assertRaisesRegex(self.bridge.risk.Reject,'manual_or_unmapped'):execution.queue(d,NOW)

    def test_netting_add_cannot_rewrite_old_sl_or_tp(self):
        _,p,_,_=self.setup_winner();b=self.scale_signal(p);b['decisions'][0]['stop']=1.0992
        d=dnb_sources.ingest_gdesk(b,NOW)[0]
        with self.flags(),self.assertRaisesRegex(self.bridge.risk.Reject,'netting_leg_protection_change'):execution.queue(d,NOW)

    def test_stale_confirmation_cannot_be_refreshed_by_polling(self):
        _,p,_,_=self.setup_winner();b=self.scale_signal(p);b['generated_at']=source_fixtures.iso(NOW-31)
        d=dnb_sources.ingest_gdesk(b,NOW)[0]
        with self.flags(),self.assertRaisesRegex(self.bridge.risk.Reject,'stale_scale_confirmation'):execution.queue(d,NOW)

    def test_fresh_publication_of_same_old_candle_is_not_new_confirmation(self):
        row,p,_,_=self.setup_winner()
        c=self.bridge.store.db();c.execute('UPDATE dnb_demo_strategy_commands SET created_at=? WHERE id=?',(NOW-60,row['id']));c.commit()
        d=dnb_sources.ingest_gdesk(self.scale_signal(p),NOW)[0]
        with self.flags(),self.assertRaisesRegex(self.bridge.risk.Reject,'confirmation_not_new_bar'):execution.queue(d,NOW)

    def test_no_recovery_sizing_increase(self):
        row,p,_,_=self.setup_winner()
        p['risk_pct']=.1;c=self.bridge.store.db();c.execute('UPDATE dnb_demo_strategy_commands SET payload=? WHERE id=?',(json.dumps(p),row['id']));c.commit()
        d=dnb_sources.ingest_gdesk(self.scale_signal(p),NOW)[0]
        with self.flags(),self.assertRaisesRegex(self.bridge.risk.Reject,'scale_in_risk_increase'):execution.queue(d,NOW)

    def test_lifetime_limit_includes_closed_legs(self):
        row,p,_,_=self.setup_winner();c=self.bridge.store.db()
        for i in range(2):
            c.execute('INSERT INTO dnb_demo_strategy_commands VALUES (?,?,?,?,?,?,?)',(str(i)*32,'CLOSED-'+str(i),'CLOSED',json.dumps(p),NOW-50+i,NOW-20,None))
        c.commit();d=dnb_sources.ingest_gdesk(self.scale_signal(p),NOW)[0]
        with self.flags(),self.assertRaisesRegex(self.bridge.risk.Reject,'scale_in_limit'):execution.queue(d,NOW)
