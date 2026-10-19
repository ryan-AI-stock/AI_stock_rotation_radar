import csv
import tempfile
import unittest
from pathlib import Path

from r1.provider_consensus_import import FIELDS, import_provider_consensus


ROOT = Path(__file__).resolve().parents[1]


class R1ProviderConsensusImportTest(unittest.TestCase):
    def _write(self, path: Path, rows: list[dict[str, str]]) -> None:
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=FIELDS)
            writer.writeheader()
            writer.writerows(rows)

    def _row(self, **overrides: str) -> dict[str, str]:
        row = {
            "ticker": "2330", "fiscal_year": "2027", "mean_eps": "88", "median_eps": "87",
            "high_eps": "95", "low_eps": "80", "analyst_count": "12", "source_name": "Vendor PIT",
            "source_url": "https://example.test/2330", "source_family": "vendor_pit", "source_tier": "1",
            "published_at": "2026-10-15", "available_at": "2026-10-16", "retrieved_at": "2026-10-19",
            "quality": "HIGH", "status": "READY",
        }
        row.update(overrides)
        return row

    def test_valid_export_materializes_consensus_and_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "provider.csv"
            self._write(source, [self._row()])
            result = import_provider_consensus(
                input_path=source, as_of_date="2026-10-16", config_path=ROOT / "config/r1.json",
                output_consensus=root / "consensus.csv", output_evidence=root / "evidence.csv",
            )
            self.assertEqual(result["accepted_rows"], 1)
            self.assertEqual(result["future_data_violation_count"], 0)
            self.assertIn("Vendor PIT", (root / "consensus.csv").read_text(encoding="utf-8"))
            self.assertIn("vendor_pit", (root / "evidence.csv").read_text(encoding="utf-8"))

    def test_future_and_out_of_universe_rows_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "provider.csv"
            self._write(source, [self._row(available_at="2026-10-17"), self._row(ticker="9999")])
            result = import_provider_consensus(
                input_path=source, as_of_date="2026-10-16", config_path=ROOT / "config/r1.json",
                output_consensus=root / "consensus.csv", output_evidence=root / "evidence.csv",
            )
            self.assertEqual(result["accepted_rows"], 0)
            self.assertEqual(result["rejected_rows"], 2)
            self.assertEqual(result["future_data_violation_count"], 1)


if __name__ == "__main__":
    unittest.main()
