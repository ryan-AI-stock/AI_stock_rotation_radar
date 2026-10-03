import unittest

from r1.daily_sources import _chip_ready, _price_market_closed, _price_ready, publication_exit_code


class R1DailySourcesTest(unittest.TestCase):
    def test_chip_ready_requires_both_markets_and_core_families(self):
        rows = [{"family": family, "market": market, "status": "accepted"}
                for family in ("institutional", "margin_short") for market in ("TWSE", "TPEx")]
        self.assertTrue(_chip_ready({"sources": rows}))
        rows[-1]["status"] = "no_rows"
        self.assertFalse(_chip_ready({"sources": rows}))

    def test_price_ready_requires_exact_universe(self):
        wanted = {"2330", "6488", "3363"}
        self.assertTrue(_price_ready({"price_rows": [{"ticker": ticker} for ticker in wanted]}, wanted))
        self.assertFalse(_price_ready({"price_rows": [{"ticker": "2330"}, {"ticker": "6488"}]}, wanted))

    def test_market_closed_requires_both_official_markets_and_no_rows(self):
        sources = [{"family": "official_raw_execution_ohlcv", "market": market, "status": "no_rows"}
                   for market in ("TWSE", "TPEx")]
        self.assertTrue(_price_market_closed({"price_rows": [], "sources": sources}))
        sources[-1]["status"] = "accepted"
        self.assertFalse(_price_market_closed({"price_rows": [], "sources": sources}))

    def test_daily_can_publish_prices_while_weekly_remains_blocked_on_chip_gap(self):
        manifest = {"blocked": [], "chip_data_ready": False}
        self.assertEqual(publication_exit_code(manifest, allow_chip_gaps=True), 0)
        self.assertEqual(publication_exit_code(manifest, allow_chip_gaps=False), 75)

    def test_price_gap_always_blocks(self):
        manifest = {"blocked": [{"reason": "incomplete_price_universe"}], "chip_data_ready": True}
        self.assertEqual(publication_exit_code(manifest, allow_chip_gaps=True), 75)


if __name__ == "__main__":
    unittest.main()
