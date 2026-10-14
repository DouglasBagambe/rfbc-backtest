import unittest
from dnb_policy import payout_plan, trailing_floor, conservative_trailing_floor
from test_mt5_bridge import snapshot, command, item, NOW
import mt5_risk as risk

class PolicyTests(unittest.TestCase):
    def test_fixed_dollar_trailing_and_cap(self):
        self.assertEqual(trailing_floor(2500),2375)
        self.assertEqual(trailing_floor(2600),2475)
        self.assertEqual(trailing_floor(2650),2500)
        self.assertEqual(conservative_trailing_floor(2700),2512.5)
    def test_oct_seven_payout_plan(self):
        p=payout_plan(2476.17,{},history_verified=False,purchase_date='2026-10-07')
        self.assertEqual(p['additional_to_target_usd'],173.83)
        self.assertEqual(p['estimated_received_usd'],130.95)
        self.assertNotIn('best_worst_trade_unknown',p['eligibility_blockers'])
        self.assertFalse(p['execution_authorised'])
    def test_target_pauses_even_when_eligibility_incomplete(self):
        p=payout_plan(2650,{},history_verified=False,purchase_date='2026-10-07')
        self.assertTrue(p['pause_new_risk']);self.assertIn('profitable_days',p['eligibility_blockers'])
    def test_consistency_equality_and_six_days(self):
        days={f'2026-10-{i:02}':20 for i in range(8,15)}
        days['2026-10-15']=10
        p=payout_plan(2650,days,history_verified=True,purchase_date='2026-10-07',cycle_elapsed=True)
        self.assertEqual(p['eligibility_blockers'],[])
    def test_new_purchase_requires_best_worst_trade(self):
        p=payout_plan(2650,{},history_verified=True,purchase_date='2026-10-08')
        self.assertIn('best_worst_trade_unknown',p['eligibility_blockers'])
    def test_correlated_manual_currency_risk(self):
        s=snapshot();s['positions']=[item(volume=.1)]
        with self.assertRaisesRegex(risk.Reject,'directional_currency_risk'): risk.plan(s,command(),NOW)
    def test_stale_manual_quote(self):
        s=snapshot();s['positions']=[item()];s['symbols']['GBPUSD.x']['quote_at']=NOW-11
        with self.assertRaisesRegex(risk.Reject,'stale_exposure_quote'):risk.plan(s,command(),NOW)
    def test_stop_breached_is_not_zero_risk(self):
        s=snapshot();s['positions']=[item(sl=1.101)]
        with self.assertRaisesRegex(risk.Reject,'exposure_stop_breached'):risk.plan(s,command(),NOW)
    def test_zero_stop_limit_is_rejected(self):
        s=snapshot();pending=item();pending['order_type']='BUY_STOP_LIMIT';s['orders']=[pending]
        with self.assertRaisesRegex(risk.Reject,'invalid_exposure_entry'):risk.plan(s,command(),NOW)
