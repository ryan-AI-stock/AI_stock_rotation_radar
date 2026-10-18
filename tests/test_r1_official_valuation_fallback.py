from __future__ import annotations

import unittest

from r1.official_valuation_fallback import _month_keys, _number, _percentile


class OfficialValuationFallbackTest(unittest.TestCase):
    def test_month_keys_cover_five_year_window(self) -> None:
        keys = _month_keys("2026-10-16")
        self.assertEqual(keys[0], "202110")
        self.assertEqual(keys[-1], "202610")
        self.assertEqual(len(keys), 61)

    def test_invalid_and_nonpositive_values_remain_missing(self) -> None:
        self.assertIsNone(_number("-"))
        self.assertIsNone(_number("0"))
        self.assertEqual(_number("1,234.5"), 1234.5)

    def test_midrank_percentile(self) -> None:
        self.assertAlmostEqual(_percentile([1.0, 2.0, 2.0, 4.0], 2.0), .5)


if __name__ == "__main__":
    unittest.main()
