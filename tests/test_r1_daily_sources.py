import unittest

from r1.daily_sources import _chip_ready


class R1DailySourcesTest(unittest.TestCase):
    def test_chip_ready_requires_both_markets_and_core_families(self):
        rows = [{"family": family, "market": market, "status": "accepted"}
                for family in ("institutional", "margin_short") for market in ("TWSE", "TPEx")]
        self.assertTrue(_chip_ready({"sources": rows}))
        rows[-1]["status"] = "no_rows"
        self.assertFalse(_chip_ready({"sources": rows}))


if __name__ == "__main__":
    unittest.main()
