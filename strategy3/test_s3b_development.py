import math
import unittest

from strategy3.s3b_development import CURRENCIES, candidate_pair, currency_strength, pair_orientation


class FeatureTests(unittest.TestCase):
    def test_base_quote_orientation(self):
        self.assertEqual(pair_orientation("EURUSD", "EUR"), 1)
        self.assertEqual(pair_orientation("EURUSD", "USD"), -1)

    def test_currency_strength_aggregates_oriented_pairs(self):
        scores = currency_strength({"EURUSD": 2.0, "GBPUSD": -1.0, "EURGBP": 3.0})
        self.assertAlmostEqual(scores["EUR"], 2.5)
        self.assertAlmostEqual(scores["USD"], -0.5)
        self.assertAlmostEqual(scores["GBP"], -2.0)
        self.assertTrue(math.isnan(scores["JPY"]))

    def test_candidate_uses_fixed_pair_and_direction(self):
        strength = {c: 0.0 for c in CURRENCIES}; strength.update({"EUR": 3.0, "USD": -2.0})
        self.assertEqual(candidate_pair(strength), ("EURUSD", 1))


if __name__ == "__main__": unittest.main()
