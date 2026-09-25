import unittest

from arbitrage.discover import similarity
from arbitrage.sports import SPORT_LEAGUE_MAPPINGS, normalize_mlb_title, supported_sports


class SportMappingsTest(unittest.TestCase):
    def test_dashboard_sports_have_public_venue_mappings(self):
        self.assertEqual(
            set(supported_sports()),
            {"football", "soccer", "hockey", "basketball", "baseball", "tennis"},
        )
        self.assertIn(("nhl", "KXNHLGAME"), SPORT_LEAGUE_MAPPINGS["hockey"])
        self.assertIn(("mlb", "KXMLBGAME"), SPORT_LEAGUE_MAPPINGS["baseball"])
        self.assertIn(("nba", "KXNBAGAME"), SPORT_LEAGUE_MAPPINGS["basketball"])
        self.assertIn(("atp", "KXATPMATCH"), SPORT_LEAGUE_MAPPINGS["tennis"])

    def test_normalizes_kalshi_mlb_abbreviations_without_merging_clubs(self):
        kalshi = normalize_mlb_title("New York Y vs Chicago C")
        self.assertEqual(kalshi, "New York Yankees vs Chicago Cubs")
        self.assertEqual(similarity(kalshi, "Chicago Cubs vs. New York Yankees"), 1.0)
