import json
import tempfile
import unittest
from pathlib import Path

from rotation_radar.c6_research_payload_materializer import build_payload


class C6ResearchPayloadMaterializerTests(unittest.TestCase):
    def test_materializes_only_existing_pit_dates_and_keeps_replay_blocked(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            score = root / "score.csv.gz"
            recent = root / "recent.csv"
            output = root / "payload.json"
            import pandas as pd
            pd.DataFrame([
                {"signal_date": "2026-08-06", "rank": 1, "ticker": "3653", "name": "健策"},
                {"signal_date": "2026-08-06", "rank": 4, "ticker": "9999", "name": "排除"},
            ]).to_csv(score, index=False, compression="gzip")
            pd.DataFrame([
                {"signal_date": "2026-08-28", "rank": 1, "ticker": "2301", "name": "光寶科"},
            ]).to_csv(recent, index=False)
            payload = build_payload(score_ranking=score, recent_top3=recent, output=output)
            self.assertEqual(payload["coverage"]["snapshot_rows"], 2)
            self.assertEqual(payload["ledger_rows"], [])
            self.assertEqual(payload["data_status"], "partial_rankings_only_no_whole_share_replay")
            self.assertEqual(json.loads(output.read_text(encoding="utf-8"))["coverage"]["missing_signal_dates"][0], "2026-08-05")
            self.assertNotIn("2026-08-06", payload["coverage"]["missing_signal_dates"])

    def test_keeps_version_and_source_lineage_configurable(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            score = root / "score.csv.gz"
            extension = root / "extension.csv"
            output = root / "payload.json"
            import pandas as pd
            pd.DataFrame([
                {"signal_date": "2026-08-06", "rank": 1, "ticker": "3653", "name": "健策"},
            ]).to_csv(score, index=False, compression="gzip")
            pd.DataFrame([
                {"signal_date": "2026-08-13", "rank": 1, "ticker": "2301", "name": "光寶科"},
            ]).to_csv(extension, index=False)
            payload = build_payload(
                score_ranking=score,
                recent_top3=extension,
                output=output,
                model_version="c6-research-score0-pit-v2",
                recent_source_label="persisted_snapshot_extension_stale_layer1_diagnostic",
            )
            self.assertEqual(payload["model_version"], "c6-research-score0-pit-v2")
            extension_row = next(row for row in payload["snapshot_rows"] if row["signal_date"] == "2026-08-13")
            self.assertEqual(extension_row["candidate_status"], "persisted_snapshot_extension_stale_layer1_diagnostic")


if __name__ == "__main__":
    unittest.main()
