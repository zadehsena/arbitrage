import unittest
from datetime import UTC, datetime
from unittest.mock import patch

from arbitrage.discover import similarity
from arbitrage.sports import (
    SPORT_LEAGUE_MAPPINGS,
    SPORT_MATCHING_VERSION,
    build_sport_report,
    is_current_sport_record,
    normalize_cfb_title,
    normalize_mlb_title,
    supported_leagues,
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

    def test_sidebar_league_categories_are_supported(self):
        self.assertEqual(supported_leagues("football"), ("cfb", "nfl"))
        self.assertEqual(supported_leagues("basketball"), ("nba", "wnba", "cbb"))

    @patch("arbitrage.sports.report_record")
    @patch("arbitrage.sports.match_events")
    @patch("arbitrage.sports.polymarket_us_league_events")
    @patch("arbitrage.sports.kalshi_open_events_for_series")
    def test_college_football_report_never_fetches_or_returns_nfl(self, kalshi_events, poly_events,
                                                                   match_events, report_record):
        kalshi_events.return_value = [{"event_ticker": "college-game"}]
        poly_events.return_value = [{"id": "college-game", "active": True, "closed": False,
                                     "startDate": "2030-01-01T00:00:00Z"}]
        match_events.side_effect = lambda kalshi, poly, *_: [(kalshi[0], poly[0], 1.0)]
        report_record.return_value = {"start_time": "2030-01-01T00:00:00Z"}

        records, _, _ = build_sport_report("football", ("cfb",))

        self.assertEqual(records, [{"start_time": "2030-01-01T00:00:00Z", "league": "cfb",
                                    "matching_version": SPORT_MATCHING_VERSION}])
        kalshi_events.assert_called_once_with("KXNCAAFGAME", 500)
        poly_events.assert_called_once_with("cfb", 500)

    def test_normalizes_kalshi_mlb_abbreviations_without_merging_clubs(self):
        kalshi = normalize_mlb_title("New York Y vs Chicago C")
        self.assertEqual(kalshi, "New York Yankees vs Chicago Cubs")
        self.assertEqual(similarity(kalshi, "Chicago Cubs vs. New York Yankees"), 1.0)

    def test_normalizes_common_college_football_team_abbreviations(self):
        kalshi = normalize_cfb_title("Appalachian St. vs NC St.")
        self.assertEqual(kalshi, "Appalachian State vs NC State")
        self.assertEqual(similarity(kalshi, "Appalachian State vs. NC State"), 1.0)
        self.assertEqual(
            normalize_cfb_title("Delaware St. vs UAlbany"),
            "Delaware State vs University at Albany",
        )

    def test_filters_completed_events_but_keeps_live_and_upcoming_events(self):
        now = datetime(2026, 9, 26, 18, tzinfo=UTC)
        self.assertFalse(is_current_sport_record({"start_time": "2026-09-26T11:00:00Z"}, "football", now))
        self.assertTrue(is_current_sport_record({"start_time": "2026-09-26T15:00:00Z"}, "football", now))
        self.assertTrue(is_current_sport_record({"start_time": "2026-09-26T20:00:00Z"}, "football", now))

    def test_uses_kalshi_expected_expiration_before_generic_live_window(self):
        now = datetime(2026, 9, 26, 19, 26, tzinfo=UTC)
        self.assertFalse(is_current_sport_record({
            "start_time": "2026-09-26T16:00:00Z",
            "kalshi_expected_expiration_time": "2026-09-26T19:00:00Z",
        }, "football", now))
        self.assertTrue(is_current_sport_record({
            "start_time": "2026-09-26T16:00:00Z",
            "kalshi_expected_expiration_time": "2026-09-26T20:00:00Z",
        }, "football", now))

    def test_uses_three_hour_fallback_for_older_college_football_records(self):
        now = datetime(2026, 9, 26, 19, 26, tzinfo=UTC)
        self.assertFalse(is_current_sport_record({
            "start_time": "2026-09-26T16:00:00Z", "league": "cfb",
        }, "football", now))
