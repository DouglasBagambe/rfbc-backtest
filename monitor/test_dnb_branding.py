import unittest
import dnb_branding as brand

class BrandTests(unittest.TestCase):
    def test_names_and_legacy_display_text(self):
        self.assertEqual(brand.NAMES["system"],"dnb Fx")
        self.assertEqual(brand.text("G'S FX 101 • G DESK • G_DESK"),"dnb Fx • dnb Desk • dnb Desk")

    def test_menu_changes_keep_callback_protocol_intact(self):
        result=brand.markup({"inline_keyboard":[[{"text":"G DESK","callback_data":"G_DESK:why"}]],"input_field_placeholder":"G's Fx 101"})
        self.assertEqual(result["inline_keyboard"][0][0]["text"],"dnb Desk")
        self.assertEqual(result["inline_keyboard"][0][0]["callback_data"],"G_DESK:why")
        self.assertEqual(result["input_field_placeholder"],"dnb Fx")

    def test_account_and_home_never_present_old_balance_as_current(self):
        self.assertNotIn("$5,000",brand.account_view())
        self.assertIn("$2,500",brand.account_view())
        self.assertIn("fresh broker snapshot",brand.account_view())
        self.assertIn("dnb Risk",brand.home_view())

    def test_next_scan_uses_twenty_past(self):
        self.assertRegex(brand.next_scan(),r"^\d{2}:20 EAT$")
