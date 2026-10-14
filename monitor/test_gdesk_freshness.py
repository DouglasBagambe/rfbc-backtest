import unittest
from datetime import datetime,timezone
from unittest.mock import patch
import g_desk_adapter as adapter

class FreshnessTests(unittest.TestCase):
    def test_sunday_reopen_is_not_weekend_closed(self):
        self.assertFalse(adapter.fx_weekend_closed(datetime(2026,10,11,22,tzinfo=timezone.utc)))
        self.assertTrue(adapter.fx_weekend_closed(datetime(2026,10,11,19,tzinfo=timezone.utc)))

    def test_friday_close_and_saturday(self):
        self.assertTrue(adapter.fx_weekend_closed(datetime(2026,10,10,12,tzinfo=timezone.utc)))
        self.assertTrue(adapter.fx_weekend_closed(datetime(2026,10,9,22,tzinfo=timezone.utc)))
        self.assertFalse(adapter.fx_weekend_closed(datetime(2026,10,9,19,tzinfo=timezone.utc)))

    def test_one_lagging_bar_prevents_fresh_claim(self):
        now=datetime(2026,10,14,14,3,tzinfo=timezone.utc)
        with patch.object(adapter,'datetime') as dt,patch.object(adapter,'_dukascopy_context',return_value={
            'EURUSD.x':[{'datetime':'2026-10-14T12:00:00+00:00'}],
            'USDJPY.x':[{'datetime':'2026-10-14T13:00:00+00:00'}]}):
            dt.now.return_value=now
            result=adapter.context_payload(['EURUSD.x','USDJPY.x'])
        self.assertEqual(result['freshness'],'INCOMPLETE')
        self.assertEqual(result['stale_symbols'],['EURUSD.x'])

    def test_new_hour_invalidates_previous_hour_cache(self):
        import pandas as pd
        # Cache age is short but its completed-bar cutoff belongs to the previous hour.
        now=pd.Timestamp.now(tz='UTC').floor('h')
        old=dict(adapter._DUKA_CACHE)
        try:
            adapter._DUKA_CACHE['EURUSD.x']=(adapter.time.time(),now-pd.Timedelta(hours=1),[{'datetime':'old'}])
            with patch.object(adapter,'_fetch_duka_side',side_effect=RuntimeError('fresh_fetch_required')):
                with self.assertRaisesRegex(RuntimeError,'fresh_fetch_required'):adapter._dukascopy_context(['EURUSD.x'])
        finally:
            adapter._DUKA_CACHE.clear();adapter._DUKA_CACHE.update(old)
