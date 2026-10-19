import csv
import json
import tempfile
import unittest
from pathlib import Path

from r1.provider_bundle_promote import (
    CONSENSUS_EVIDENCE_FIELDS, CONSENSUS_FIELDS, TARGET_FIELDS, audit_and_promote,
)


class R1ProviderBundlePromoteTest(unittest.TestCase):
    def _write(self, path: Path, fields: tuple[str, ...], rows: list[dict[str, str]]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)

    def _fixture(self, root: Path) -> dict[str, Path]:
        paths = {
            "consensus": root / "consensus.csv", "consensus_evidence": root / "consensus_evidence.csv",
            "target": root / "target.csv", "provider_consensus": root / "provider_consensus.csv",
            "provider_consensus_evidence": root / "provider_consensus_evidence.csv",
            "provider_target": root / "provider_target.csv", "market": root / "market.json",
        }
        self._write(paths["consensus"], CONSENSUS_FIELDS, [])
        self._write(paths["consensus_evidence"], CONSENSUS_EVIDENCE_FIELDS, [])
        self._write(paths["target"], TARGET_FIELDS, [])
        self._write(paths["provider_consensus"], CONSENSUS_FIELDS, [{
            "ticker": "2330", "fiscal_year": "2027", "mean_eps": "88", "median_eps": "87",
            "high_eps": "95", "low_eps": "80", "analyst_count": "12", "source": "Vendor PIT",
            "published_at": "2026-10-15", "available_at": "2026-10-16", "retrieved_at": "2026-10-19",
            "quality": "HIGH", "status": "READY",
        }])
        self._write(paths["provider_consensus_evidence"], CONSENSUS_EVIDENCE_FIELDS, [{
            "ticker": "2330", "fiscal_year": "2027", "source_url": "https://example.test/eps",
            "source_family": "vendor_pit", "source_tier": "1", "available_at": "2026-10-16", "note": "test",
        }])
        self._write(paths["provider_target"], TARGET_FIELDS, [{
            "ticker": "2330", "institution": f"Bank {letter}", "target_price": str(price), "horizon": "12M",
            "available_at": "2026-10-16", "source_url": f"https://example.test/{letter}",
            "retrieved_at": "2026-10-19", "note": "test",
        } for letter, price in (("A", 2100), ("B", 2200), ("C", 2300))])
        paths["market"].write_text(json.dumps({"rows": [{"ticker": "2330", "raw_close": 1800}]}), encoding="utf-8")
        return paths

    def test_preview_does_not_mutate_production(self):
        with tempfile.TemporaryDirectory() as directory:
            paths = self._fixture(Path(directory))
            result = audit_and_promote(
                as_of_date="2026-10-16", market_path=paths["market"], consensus_path=paths["consensus"],
                consensus_evidence_path=paths["consensus_evidence"], target_evidence_path=paths["target"],
                provider_consensus_path=paths["provider_consensus"],
                provider_consensus_evidence_path=paths["provider_consensus_evidence"],
                provider_target_evidence_path=paths["provider_target"], apply=False,
            )
            self.assertEqual(result["status"], "READY")
            self.assertEqual(result["target_ready_ticker_count_after"], 1)
            self.assertEqual(paths["target"].read_text(encoding="utf-8").count("\n"), 1)

    def test_apply_is_idempotent(self):
        with tempfile.TemporaryDirectory() as directory:
            paths = self._fixture(Path(directory))
            kwargs = dict(
                as_of_date="2026-10-16", market_path=paths["market"], consensus_path=paths["consensus"],
                consensus_evidence_path=paths["consensus_evidence"], target_evidence_path=paths["target"],
                provider_consensus_path=paths["provider_consensus"],
                provider_consensus_evidence_path=paths["provider_consensus_evidence"],
                provider_target_evidence_path=paths["provider_target"], apply=True,
            )
            first = audit_and_promote(**kwargs)
            second = audit_and_promote(**kwargs)
            self.assertEqual((first["consensus_rows_added"], first["target_rows_added"]), (1, 3))
            self.assertEqual((second["consensus_rows_added"], second["target_rows_added"]), (0, 0))


if __name__ == "__main__":
    unittest.main()
