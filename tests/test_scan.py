from decimal import Decimal
import unittest

from arbitrage.client import Quote
from arbitrage.scan import paired_opportunity


class ScannerTest(unittest.TestCase):
    def test_detects_executable_complementary_pair(self):
        result = paired_opportunity("same contract", Quote(Decimal(".42"), Decimal("10")),
                                    Quote(Decimal(".51"), Decimal("3")), "test",
                                    Decimal(".02"), Decimal(".02"))
        self.assertIsNotNone(result)
        self.assertEqual(result.edge, Decimal(".05"))
        self.assertEqual(result.maximum_contracts, Decimal("3"))


    def test_rejects_cost_after_buffer_at_or_above_one(self):
        result = paired_opportunity("same contract", Quote(Decimal(".49"), Decimal("10")),
                                    Quote(Decimal(".50"), Decimal("3")), "test",
                                    Decimal(".02"), Decimal(".01"))
        self.assertIsNone(result)
