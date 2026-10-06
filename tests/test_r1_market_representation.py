import unittest
from unittest.mock import patch

from r1.market_representation import _fetch_twse_average_turnover, _score_by_theme


class R1MarketRepresentationTest(unittest.TestCase):
    def test_theme_percentiles_and_weights(self):
        rows = [
            {"ticker": "A", "theme_id": "x", "market_cap_twd": 300,
             "average_turnover_20td_twd": 100, "foreign_ownership_pct": 30},
            {"ticker": "B", "theme_id": "x", "market_cap_twd": 100,
             "average_turnover_20td_twd": 300, "foreign_ownership_pct": 10},
            {"ticker": "C", "theme_id": "x", "market_cap_twd": 200,
             "average_turnover_20td_twd": 200, "foreign_ownership_pct": 20},
        ]
        _score_by_theme(rows)
        self.assertEqual(rows[0]["subscores"]["market_cap"], 100)
        self.assertEqual(rows[1]["subscores"]["average_turnover_20td"], 100)
        self.assertEqual(rows[2]["market_representation"], 50)

    def test_missing_value_does_not_reweight(self):
        rows = [{"ticker": "A", "theme_id": "x", "market_cap_twd": 300,
                 "average_turnover_20td_twd": 100, "foreign_ownership_pct": None}]
        _score_by_theme(rows)
        self.assertIsNone(rows[0]["market_representation"])

    def test_twse_turnover_uses_latest_20_dates(self):
        october = {"data": [[f"115/10/{day:02d}", "1", f"{day * 100:,}"] for day in range(1, 6)]}
        september = {"data": [[f"115/09/{day:02d}", "1", f"{day * 100:,}"] for day in range(1, 31)]}

        class Response:
            def __init__(self, payload): self.payload = payload
            def __enter__(self): return self
            def __exit__(self, *args): return False
            def read(self): return __import__("json").dumps(self.payload).encode()

        with patch("r1.market_representation.urlopen", side_effect=[Response(october), Response(september)]):
            average, urls = _fetch_twse_average_turnover("6230", "2026-10-05")
        expected = [day * 100 for day in range(16, 31)] + [day * 100 for day in range(1, 6)]
        self.assertEqual(average, sum(expected) / 20)
        self.assertEqual(len(urls), 2)


if __name__ == "__main__":
    unittest.main()
