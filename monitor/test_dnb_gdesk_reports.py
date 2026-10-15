import unittest
from unittest.mock import patch
import dnb_gdesk_reports as reports
import test_dnb_alerts as fixtures
from test_mt5_bridge import NOW
from datetime import datetime, timezone

class ReportTests(unittest.TestCase):
    setUp = fixtures.AlertTests.setUp
    tearDown = fixtures.AlertTests.tearDown

    def test_failed_send_retries_then_survives_restart(self):
        reports.prepare("hourly-test","NO_TRADE","No objective setup",NOW)
        with patch("fx101.telegram_send", side_effect=[(False,"503"),(True,"200")]) as send:
            reports.dispatch(send)
            reports.dispatch(send)
            import fx101
            fx101.close_db()
            reports.dispatch(send)
            self.assertEqual(send.call_count,2)

    def test_status_report_never_prepares_a_trade(self):
        reports.prepare("failure","SYSTEM_FAILURE","Feed missing",NOW)
        self.assertEqual(self.bridge.store.db().execute("SELECT COUNT(*) FROM dnb_alert_intents").fetchone()[0],0)

    def test_watchdog_waits_reports_once_and_deduplicates(self):
        instant=int(datetime(2026,10,15,12,40,tzinfo=timezone.utc).timestamp())
        self.bridge._ensure_schema()
        reports.watchdog(instant-21*60)
        self.assertEqual(self.bridge.store.db().execute("SELECT COUNT(*) FROM dnb_gdesk_reports").fetchone()[0],0)
        with patch("fx101.telegram_send",return_value=(True,"200")) as send:
            reports.watchdog(instant);reports.dispatch(send)
            reports.watchdog(instant+1);reports.dispatch(send)
            self.assertEqual(send.call_count,1)
