import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from rotation_radar import c6_dashboard_publish


class C6DashboardPublishCliTests(unittest.TestCase):
    def test_cli_keeps_coverage_metadata_out_of_publish_arguments(self):
        with tempfile.TemporaryDirectory() as tmp:
            payload_path = Path(tmp) / "payload.json"
            payload_path.write_text(json.dumps({
                "model_version": "v2",
                "snapshot_as_of": "2026-08-28",
                "data_status": "partial",
                "source_manifest_hash": "hash",
                "snapshot_rows": [],
                "ledger_rows": [],
                "slots": [],
                "cash": 0.0,
                "notes": "test",
                "coverage": {"snapshot_rows": 0},
                "formal_model_changed": False,
                "future_data_violation_count": 0,
            }), encoding="utf-8")
            with patch.object(c6_dashboard_publish, "publish_snapshot", return_value={"ok": True}) as publish:
                with patch.object(sys, "argv", [
                    "c6_dashboard_publish", "--spreadsheet-id", "sheet", "--payload", str(payload_path),
                ]):
                    c6_dashboard_publish.main()
            self.assertNotIn("coverage", publish.call_args.kwargs)
            self.assertNotIn("formal_model_changed", publish.call_args.kwargs)
            self.assertNotIn("future_data_violation_count", publish.call_args.kwargs)


if __name__ == "__main__":
    unittest.main()
