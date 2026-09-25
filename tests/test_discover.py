import unittest

from arbitrage.discover import find_candidates, similarity


class DiscoveryTest(unittest.TestCase):
    def test_scores_same_event_title_highly(self):
        self.assertGreater(similarity("Will Atlanta Braves win the 2026 National League pennant?",
                                      "Atlanta Braves to win the National League in 2026"), 0.65)

    def test_returns_candidate_with_market_identifiers(self):
        results = find_candidates(
            [{"ticker": "KXTEST", "title": "Will Atlanta Braves win the 2026 National League pennant?"}],
            [{"slug": "mlb-nl-2026-atl", "question": "Atlanta Braves to win the National League in 2026"}],
            0.6,
        )
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].kalshi_ticker, "KXTEST")
        self.assertEqual(results[0].polymarket_us_slug, "mlb-nl-2026-atl")
