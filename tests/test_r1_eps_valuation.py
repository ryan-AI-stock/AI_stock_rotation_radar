import csv
import tempfile
import unittest
from pathlib import Path

from r1.eps_revision import revision_features
from r1.providers import CsvConsensusProvider
from r1.valuation import valuation_scenarios


FIELDS = ["ticker", "fiscal_year", "mean_eps", "median_eps", "high_eps", "low_eps", "analyst_count",
          "source", "published_at", "available_at", "retrieved_at", "quality", "status"]


class R1EpsValuationTest(unittest.TestCase):
    def test_provider_respects_available_at_and_revision(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "eps.csv"
            with path.open("w", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=FIELDS); writer.writeheader()
                writer.writerow({"ticker": "2408", "fiscal_year": 2027, "mean_eps": 10, "analyst_count": 3,
                                 "source": "two_sources", "available_at": "2026-09-01T18:00:00+08:00",
                                 "retrieved_at": "2026-09-01T18:05:00+08:00", "quality": "MEDIUM", "status": "AVAILABLE"})
                writer.writerow({"ticker": "2408", "fiscal_year": 2027, "mean_eps": 12, "analyst_count": 3,
                                 "source": "two_sources", "available_at": "2026-09-29T18:00:00+08:00",
                                 "retrieved_at": "2026-09-29T18:05:00+08:00", "quality": "MEDIUM", "status": "AVAILABLE"})
                writer.writerow({"ticker": "2408", "fiscal_year": 2027, "mean_eps": 99, "analyst_count": 3,
                                 "source": "future", "available_at": "2026-10-02T18:00:00+08:00",
                                 "retrieved_at": "2026-10-02T18:05:00+08:00", "quality": "HIGH", "status": "AVAILABLE"})
            result = revision_features(CsvConsensusProvider(path), ticker="2408", fiscal_year=2027, as_of_date="2026-10-01")
            self.assertEqual(result["mean_eps"], 12)
            self.assertAlmostEqual(result["revision_4w"], 0.20)

    def test_valuation_keeps_missing_scenario_missing(self):
        result = valuation_scenarios(price=100, bear_eps=None, base_eps=10, bull_eps=12,
                                     bear_pe=None, base_pe=15, bull_pe=20)
        self.assertIsNone(result["bear_fair_value"])
        self.assertEqual(result["base_fair_value"], 150)
        self.assertEqual(result["forward_pe"], 10)


if __name__ == "__main__":
    unittest.main()
