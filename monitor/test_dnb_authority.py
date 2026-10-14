import copy
import unittest
import dnb_authority as a
from test_mt5_bridge import NOW
class AuthorityTests(unittest.TestCase):
    def record(self):
        return {'login':315307814,'server':'GoatFunded-Server','daily_anchor':2500,'historical_peak':2500,
                'payout_cycle':'INITIAL','daily_reset_utc':NOW-1,'valid_until':NOW+86399,'payout_eligible_utc':NOW+86400,
                'payout_pending':False,'gates':{k:False for k in a.GATES},'evidence':{k:'a'*64 for k in a.GATES|{'anchors','reset_timezone','payout_reset'}}}
    def test_verified_evidence_schema_not_readiness(self):
        r=a.validate(self.record(),NOW);self.assertFalse(any(r['gates'].values()))
    def test_unknown_anchor_not_backfilled(self):
        r=self.record();r['daily_anchor']=0
        with self.assertRaises(a.risk.Reject):a.validate(r,NOW)
    def test_expired_reset_rejected(self):
        r=self.record();r['valid_until']=NOW
        with self.assertRaisesRegex(a.risk.Reject,'expired_daily_anchor'):a.validate(r,NOW)
    def test_evidence_missing_rejected(self):
        r=self.record();r['evidence'].pop('payout_reset')
        with self.assertRaisesRegex(a.risk.Reject,'authority_evidence_required'):a.validate(r,NOW)
    def test_string_true_does_not_certify_gate(self):
        r=self.record();r['gates']['compliance']='true'
        with self.assertRaises(a.risk.Reject):a.validate(r,NOW)
