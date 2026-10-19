import csv
import tempfile
import unittest
from pathlib import Path

from r1.provider_target_price_import import FIELDS, import_provider_target_prices
from r1.target_price_consensus import build_snapshot, load_records


ROOT = Path(__file__).resolve().parents[1]


class R1ProviderTargetPriceImportTest(unittest.TestCase):
    def _write(self, path: Path, rows: list[dict[str, str]]) -> None:
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=FIELDS)
            writer.writeheader()
            writer.writerows(rows)

    def _row(self, **overrides: str) -> dict[str, str]:
        row = {
            "ticker": "2330", "institution": "Provider Bank A", "target_price": "2100",
            "horizon": "12M", "published_at": "2026-10-15", "available_at": "2026-10-16",
            "retrieved_at": "2026-10-19", "source_url": "https://example.test/2330/a",
            "source_family": "vendor_pit", "source_tier": "1", "quality": "HIGH", "status": "READY",
        }
        row.update(overrides)
        return row

    def test_valid_rows_are_compatible_with_existing_consensus(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "provider.csv"
            self._write(source, [
                self._row(),
                self._row(institution="Provider Bank B", target_price="2200", source_url="https://example.test/2330/b"),
                self._row(institution="Provider Bank C", target_price="2300", source_url="https://example.test/2330/c"),
            ])
            evidence = root / "evidence.csv"
            result = import_provider_target_prices(
                input_path=source, as_of_date="2026-10-16", config_path=ROOT / "config/r1.json",
                output_evidence=evidence,
            )
            self.assertEqual(result["accepted_rows"], 3)
            payload = build_snapshot(
                date="2026-10-16", market={"rows": [{"ticker": "2330", "raw_close": 1800}]},
                tickers=["2330"], evidence_path=evidence,
            )
            self.assertEqual(payload["ready_ticker_count"], 1)
            self.assertEqual(payload["rows"][0]["consensus_target_price"], 2200)
            self.assertEqual(len(load_records(evidence)), 3)

    def test_future_non_12m_and_out_of_universe_rows_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "provider.csv"
            self._write(source, [
                self._row(available_at="2026-10-17"), self._row(horizon="6M"), self._row(ticker="9999"),
            ])
            result = import_provider_target_prices(
                input_path=source, as_of_date="2026-10-16", config_path=ROOT / "config/r1.json",
                output_evidence=root / "evidence.csv",
            )
            self.assertEqual(result["accepted_rows"], 0)
            self.assertEqual(result["rejected_rows"], 3)
            self.assertEqual(result["future_data_violation_count"], 1)


if __name__ == "__main__":
    unittest.main()
