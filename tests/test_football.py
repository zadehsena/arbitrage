import unittest

from arbitrage.football import KALSHI_SERIES_BY_LEAGUE, match_events


class FootballTest(unittest.TestCase):
    def test_has_kalshi_series_for_supported_leagues(self):
        self.assertEqual(KALSHI_SERIES_BY_LEAGUE["cfb"], "KXNCAAFGAME")
        self.assertEqual(KALSHI_SERIES_BY_LEAGUE["nfl"], "KXNFLGAME")

    def test_matches_reordered_team_title(self):
        kalshi = [{"event_ticker": "KX", "title": "Army vs Temple"}]
        poly = [{"slug": "game", "title": "Temple vs. Army"}]
        result = match_events(kalshi, poly, 0.7)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0][2], 1.0)
