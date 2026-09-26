import unittest
from datetime import UTC, datetime

from arbitrage.discover import similarity
from arbitrage.sports import (
    SPORT_LEAGUE_MAPPINGS,
    is_current_sport_record,
    normalize_mlb_title,
    supported_sports,
)


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

    def test_filters_completed_events_but_keeps_live_and_upcoming_events(self):
        now = datetime(2026, 9, 26, 18, tzinfo=UTC)
        self.assertFalse(is_current_sport_record({"start_time": "2026-09-26T11:00:00Z"}, "football", now))
        self.assertTrue(is_current_sport_record({"start_time": "2026-09-26T15:00:00Z"}, "football", now))
        self.assertTrue(is_current_sport_record({"start_time": "2026-09-26T20:00:00Z"}, "football", now))
