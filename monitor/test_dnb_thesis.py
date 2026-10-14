import copy
import unittest
import dnb_thesis as thesis
import mt5_risk as risk
from test_mt5_bridge import snapshot,command,item,NOW

class ThesisTests(unittest.TestCase):
    def setUp(self):
        self.s=snapshot();self.c=command()
        p=item('EURUSD.x',volume=.01,sl=1.099);p.update(entry=1.098,profit=2.1)
        self.s['positions']=[p]
        self.proof={'thesis_id':'THESIS-1','initial_risk_pct':.25,'confirmation_at':NOW,
            'confirmation_id':'NEW-CONFIRMATION','structure_valid':True,'broker_history_verified':True,
            'legs':[{'ticket':p['ticket'],'command_id':'b'*32,'thesis_id':'THESIS-1',
                     'entry':p['entry'],'side':'BUY','commission':-.1,'created_at':NOW-60,
                     'confirmation_id':'INITIAL-CONFIRMATION','risk_pct':.25}]}
    def reject(self,reason):
        with self.assertRaisesRegex(risk.Reject,reason):thesis.plan_scale_in(self.s,self.c,self.proof,NOW)
    def test_profitable_add_on_preserves_stops(self):
        before=copy.deepcopy(self.s);p=thesis.plan_scale_in(self.s,self.c,self.proof,NOW)
        self.assertEqual(self.s,before);self.assertEqual(p['thesis_id'],'THESIS-1')
        self.assertEqual(p['scale_in_number'],1);self.assertFalse(p['auto_authorised'])
    def test_loss_or_zero_net_profit_blocks_add_on(self):self.s['positions'][0]['profit']=.1;self.reject('no_adding_to_losing_leg')
    def test_no_risk_increase(self):self.proof['initial_risk_pct']=.2;self.reject('scale_in_risk_increase')
    def test_unmapped_manual_position(self):
        p=copy.deepcopy(self.s['positions'][0]);p['ticket']='456';self.s['positions'].append(p);self.reject('manual_or_unmapped')
    def test_pending_leg_is_not_profitable_position(self):self.s['orders']=[item('EURUSD.x')];self.reject('unresolved_same_symbol_pending')
    def test_fresh_confirmation_required(self):self.proof['confirmation_at']=NOW-31;self.reject('stale_scale_confirmation')
    def test_reused_confirmation(self):self.proof['confirmation_id']='INITIAL-CONFIRMATION';self.reject('duplicate_scale_confirmation')
    def test_third_add_on_blocked(self):self.proof['legs']*=3;self.reject('scale_in_limit')
    def test_averaging_down(self):self.s['positions'][0]['entry']=1.101;self.proof['legs'][0]['entry']=1.101;self.reject('no_averaging_down')
    def test_thesis_unknown(self):self.proof['broker_history_verified']=False;self.reject('thesis_or_broker_history_unverified')
    def test_original_duplicate_still_rejected(self):
        with self.assertRaisesRegex(risk.Reject,'duplicate_symbol'):risk.plan(self.s,self.c,NOW)
    def test_restarted_planner_cannot_ignore_existing_risk(self):
        p=thesis.plan_scale_in(copy.deepcopy(self.s),copy.deepcopy(self.c),copy.deepcopy(self.proof),NOW)
        self.assertGreater(p['existing_risk_usd'],0);self.assertGreater(p['total_thesis_risk_usd'],p['risk_usd'])
