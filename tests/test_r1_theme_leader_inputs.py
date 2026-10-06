import json
import tempfile
import unittest
from pathlib import Path

from r1.theme_leader_inputs import materialize


ROOT = Path(__file__).resolve().parents[1]


class R1ThemeLeaderInputsTest(unittest.TestCase):
    def test_missing_source_materializes_exact_universe_as_na(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "latest.json"
            payload = materialize(
                as_of_date="2026-10-02", theme_path=ROOT / "config/r1_v02_themes.json",
                source_path=Path(directory) / "missing.json", output_path=output,
                rubric_path=ROOT / "config/r1_v03_score_rubric.json",
            )
        self.assertEqual(payload["requested_ticker_count"], 54)
        self.assertEqual(payload["actual_ticker_count"], 54)
        self.assertEqual(payload["complete_ticker_count"], 0)
        self.assertTrue(all(row["status"] == "DATA_MISSING" for row in payload["rows"]))

    def test_score_without_traceable_evidence_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "source.json"
            source.write_text(json.dumps({"rows": [{
                "ticker": "2330", "bottleneck_directness": 90,
            }]}), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "missing evidence fields"):
                materialize(
                    as_of_date="2026-10-02", theme_path=ROOT / "config/r1_v02_themes.json",
                    source_path=source, output_path=Path(directory) / "latest.json",
                    rubric_path=ROOT / "config/r1_v03_score_rubric.json",
                )

    def test_future_evidence_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "source.json"
            source.write_text(json.dumps({"rows": [{
                "ticker": "2330", "bottleneck_directness": 90,
                "evidence": {"bottleneck_directness": {
                    "source_url": "https://example.test", "source_date": "2026-10-03",
                    "available_at": "2026-10-03", "source_family": "company_ir",
                    "evidence_note": "test",
                }},
            }]}), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "future evidence"):
                materialize(
                    as_of_date="2026-10-02", theme_path=ROOT / "config/r1_v02_themes.json",
                    source_path=source, output_path=Path(directory) / "latest.json",
                    rubric_path=ROOT / "config/r1_v03_score_rubric.json",
                )

    def test_qualitative_score_75_plus_requires_two_source_families(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "source.json"
            source.write_text(json.dumps({"rows": [{
                "ticker": "2330", "bottleneck_directness": 75,
                "evidence": {"bottleneck_directness": {
                    "source_url": "https://example.test", "source_date": "2026-10-01",
                    "available_at": "2026-10-01", "source_family": "company_ir",
                    "evidence_note": "one family only",
                }},
            }]}), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "independent source families"):
                materialize(
                    as_of_date="2026-10-02", theme_path=ROOT / "config/r1_v02_themes.json",
                    source_path=source, output_path=Path(directory) / "latest.json",
                    rubric_path=ROOT / "config/r1_v03_score_rubric.json",
                )

    def test_qualitative_score_75_plus_accepts_two_source_families(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "source.json"
            proof = {
                "sources": [{
                    "source_url": "https://company.test", "source_date": "2026-10-01",
                    "available_at": "2026-10-01", "source_family": "company_ir",
                    "evidence_note": "company evidence",
                }, {
                    "source_url": "https://industry.test", "source_date": "2026-10-01",
                    "available_at": "2026-10-01", "source_family": "industry_research",
                    "evidence_note": "independent evidence",
                }]
            }
            source.write_text(json.dumps({"rows": [{
                "ticker": "2330", "bottleneck_directness": 75,
                "evidence": {"bottleneck_directness": proof},
            }]}), encoding="utf-8")
            payload = materialize(
                as_of_date="2026-10-02", theme_path=ROOT / "config/r1_v02_themes.json",
                source_path=source, output_path=Path(directory) / "latest.json",
                rubric_path=ROOT / "config/r1_v03_score_rubric.json",
            )
        row = next(item for item in payload["rows"] if item["ticker"] == "2330")
        self.assertEqual(row["bottleneck_directness"], 75)


if __name__ == "__main__":
    unittest.main()
