import csv
import tempfile
import unittest
from pathlib import Path

from r1.eps_revision import revision_features
from r1.providers import CsvConsensusProvider
from r1.valuation import load_valuation_reference, valuation_position, valuation_scenarios


FIELDS = ["ticker", "fiscal_year", "mean_eps", "median_eps", "high_eps", "low_eps", "analyst_count",
          "source", "published_at", "available_at", "retrieved_at", "quality", "status"]


class R1EpsValuationTest(unittest.TestCase):
    def test_repository_valuation_reference_normalizes_median_column(self):
        reference = load_valuation_reference(
            Path(__file__).resolve().parents[1] / "data/r1/valuation_reference.csv",
            as_of_date="2026-10-02",
        )
        self.assertEqual(len(reference), 14)
        self.assertEqual(reference["2330"]["five_year_median_forward_pe"], 16.0)
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

    def test_reference_is_pit_bounded_and_position_is_raw_not_a_score(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "valuation.csv"
            path.write_text(
                "ticker,data_date,five_year_percentile,five_year_median_forward_pe\n"
                "2408,2026-10-01,0.29,10\n"
                "2330,2026-10-03,0.77,16\n",
                encoding="utf-8",
            )
            rows = load_valuation_reference(path, as_of_date="2026-10-02")
            self.assertEqual(set(rows), {"2408"})
            result = valuation_position(forward_pe=5.6, reference=rows["2408"])
            self.assertEqual(result["forward_pe_percentile_5y"], 0.29)
            self.assertAlmostEqual(result["forward_pe_vs_median"], -0.44)


if __name__ == "__main__":
    unittest.main()
