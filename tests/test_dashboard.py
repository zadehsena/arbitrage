import unittest
from unittest.mock import patch

from arbitrage.dashboard import ACCOUNT_SUMMARY_TIMEOUT_SECONDS, SPORT_PAGE_SIZE, _pagination, account_summary


class DashboardAccountSummaryTest(unittest.TestCase):
    def test_pagination_bounds_requested_page_size_and_offset(self):
        self.assertEqual(_pagination("offset=25&limit=25"), (25, 25))
        self.assertEqual(_pagination("offset=-1&limit=1000"), (0, SPORT_PAGE_SIZE))
        self.assertEqual(_pagination("offset=invalid&limit=invalid"), (0, SPORT_PAGE_SIZE))

    @patch("arbitrage.dashboard.polymarket_us_balances")
    @patch("arbitrage.dashboard.kalshi_balance")
    def test_account_summary_uses_short_dashboard_timeouts(self, kalshi_balance, polymarket_balances):
        kalshi_balance.return_value = {"balance": 1250, "portfolio_value": 3000}
        polymarket_balances.return_value = {"balances": [{"currency": "USD", "displayedCash": "7.50"}]}

        summary = account_summary()

        kalshi_balance.assert_called_once_with(timeout=ACCOUNT_SUMMARY_TIMEOUT_SECONDS)
        polymarket_balances.assert_called_once_with(timeout=ACCOUNT_SUMMARY_TIMEOUT_SECONDS)
        self.assertEqual([wallet["venue"] for wallet in summary["wallets"]],
                         ["Kalshi", "Polymarket US", "Novig", "ProphetX"])
