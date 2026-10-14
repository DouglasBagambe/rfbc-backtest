import unittest
import dnb_lifecycle as life
class LifecycleTests(unittest.TestCase):
    def order(self,state=4):return {'ticket':'700','position_id':'900','volume_initial':.02,'state':state}
    def deal(self,ticket='800',entry=0,volume=.01,reason=3,profit=0):
        return {'ticket':ticket,'order_ticket':'700' if entry==0 else '701','position_id':'900','entry':entry,'volume':volume,'reason':reason,'profit':profit,'commission':-.1,'swap':0,'fee':0}
    def test_partial_open(self):
        r=life.project(self.order(),[self.deal()],[{'ticket':'900','volume':.01}],[])
        self.assertEqual(r['state'],'PARTIAL_OPEN');self.assertEqual(r['filled_volume'],.01)
    def test_partial_pending(self):
        r=life.project(self.order(3),[self.deal()],[{'ticket':'900','volume':.01}],[{'ticket':'700'}])
        self.assertEqual(r['state'],'PARTIAL_PENDING')
    def test_full_fill(self):
        r=life.project(self.order(),[self.deal(volume=.02)],[{'ticket':'901','identifier':'900','volume':.02}],[])
        self.assertEqual(r['state'],'OPEN')
    def test_manual_close_is_linked_by_position_identity(self):
        r=life.project(self.order(),[self.deal(volume=.02),self.deal('801',1,.02,0,3)],[],[])
        self.assertEqual(r['state'],'CLOSED');self.assertTrue(r['manual_or_external_exit']);self.assertAlmostEqual(r['realised_net_usd'],2.8)
    def test_stop_out(self):
        r=life.project(self.order(),[self.deal(volume=.02),self.deal('801',1,.02,6,-3)],[],[])
        self.assertTrue(r['stop_out']);self.assertEqual(r['state'],'CLOSED')
    def test_cancel_reject_expiry(self):
        for state,name in [(2,'CANCELLED'),(5,'REJECTED'),(6,'EXPIRED')]:
            self.assertEqual(life.project(self.order(state),[],[],[])['state'],name)
    def test_missing_exit_is_not_invented(self):
        self.assertEqual(life.project(self.order(),[self.deal(volume=.02)],[],[])['state'],'FILLED_RECONCILIATION_PENDING')
