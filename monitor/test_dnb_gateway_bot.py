import os
import unittest
from unittest.mock import patch
import test_dnb_alerts as fixtures
import dnb_telegram as bot
import dnb_market_context as context

class BotTests(unittest.TestCase):
    setUp=fixtures.AlertTests.setUp
    tearDown=fixtures.AlertTests.tearDown
    def client(self):
        self.app.register_blueprint(bot.bp)
        return self.app.test_client()
    def env(self):return patch.dict(os.environ,{"TELEGRAM_BOT_TOKEN":"fixture-key","TELEGRAM_CHAT_ID":"123"})

    def test_auth_and_owner_chat_are_required(self):
        with self.env():
            client=self.client()
            self.assertEqual(client.post("/telegram/webhook",json={"update_id":1}).status_code,403)
            headers={"X-Telegram-Bot-Api-Secret-Token":bot.secret()}
            self.assertEqual(client.post("/telegram/webhook",headers=headers,json={"update_id":1,"message":{"chat":{"id":999},"text":"/start"}}).status_code,403)

    def test_menu_is_read_only_and_duplicate_update_is_suppressed(self):
        with self.env(),patch("fx101.telegram_send",return_value=(True,"200")) as send:
            client=self.client()
            headers={"X-Telegram-Bot-Api-Secret-Token":bot.secret()}
            update={"update_id":42,"message":{"chat":{"id":123},"text":"/start"}}
            self.assertTrue(client.post("/telegram/webhook",headers=headers,json=update).json["delivered"])
            self.assertEqual(client.post("/telegram/webhook",headers=headers,json=update).json["status"],"duplicate")
            self.assertEqual(send.call_count,1)
            self.assertIn("dnb Bot",send.call_args.args[0])
            self.assertEqual(self.bridge.store.db().execute("SELECT COUNT(*) FROM mt5_v2_commands").fetchone()[0],0)

    def test_unverified_balance_and_positions_are_not_invented(self):
        with patch.object(self.bridge,"latest_snapshot",return_value=None):
            self.assertIn("fresh broker snapshot",bot.account())
            self.assertIn("unavailable",bot.open_trades())

    def test_new_desk_button_routes_to_current_desk(self):
        self.assertEqual(bot.ALIASES["🧭 dnb Desk"],"/gdesk")
        self.assertIn("18 markets",bot.respond("/gdesk"))

class ContextPublisherTests(unittest.TestCase):
    def test_all_symbols_share_one_scan_and_ready_follows(self):
        symbols=["TEST"+str(i) for i in range(18)]
        payload={"symbols":symbols,"generated_at":"2026-10-15T12:00:00Z","latest_completed_bar":{s:"2026-10-15T11:00:00Z" for s in symbols},"market_state":"MARKET_OPEN","freshness":"FRESH","source":"Dukascopy BID/ASK","timeframe":"H1","bars":{s:[] for s in symbols}}
        with patch.object(context.adapter,"context_payload",return_value=payload),patch("fx101.log") as log:
            identifier=context.emit()
        self.assertEqual(log.call_count,19)
        self.assertEqual(log.call_args.args[0],"gdesk_context_ready")
        self.assertTrue(all(c.kwargs["scan_id"]==identifier for c in log.call_args_list))

    def test_missing_universe_never_emits_ready(self):
        with patch.object(context.adapter,"context_payload",return_value={"symbols":[]}),patch("fx101.log") as log:
            with self.assertRaisesRegex(RuntimeError,"universe_incomplete"):context.emit()
            log.assert_not_called()

    def test_provider_mapping_covers_all_eighteen_symbols(self):
        with patch.object(context.adapter,"DESK_SYMBOLS",[]),patch.dict(context.adapter.PAIR_TO_DUKASCOPY,{},clear=True):
            context.configure()
            self.assertEqual(len(context.adapter.DESK_SYMBOLS),18)
            self.assertIn("XAUUSD.x",context.adapter.DESK_SYMBOLS)
