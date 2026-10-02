import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from r1 import dashboard_publish
from r1.dashboard_schema import TAB_SCHEMAS


class FakeSheetsClient:
    def __init__(self, _spreadsheet_id: str):
        self.values = {
            "R1 Dashboard": [],
            "R1每日訊號資料庫": [list(TAB_SCHEMAS["R1每日訊號資料庫"]), ["2026-10-01", "2330"]],
            "R1模擬交易紀錄": [list(TAB_SCHEMAS["R1模擬交易紀錄"])],
        }

    @staticmethod
    def _title(a1_range: str) -> str:
        return a1_range.split("'!", 1)[0].lstrip("'")

    def get(self, a1_range: str):
        return self.values[self._title(a1_range)]

    def clear(self, a1_range: str):
        self.values[self._title(a1_range)] = []

    def update(self, a1_range: str, values):
        self.values[self._title(a1_range)] = values


class R1DashboardPublishTest(unittest.TestCase):
    def test_publishes_current_date_preserves_signal_history_and_keeps_transactions_empty(self):
        date = "2026-10-02"
        dashboard = [["R1研究版｜AI瓶頸預期差輪動"], ["最新資料日期", date, "模型定位", "研究挑戰版", "尚未啟用交易"]]
        dashboard.extend([[f"section-{i}"] for i in range(18)])
        signals = [list(TAB_SCHEMAS["R1每日訊號資料庫"])]
        for index in range(14):
            signals.append([date, f"{2300 + index:04d}", "測試", *([None] * 20), "DATA_MISSING", "blocked"])
        payload = {
            "date": date,
            "tabs": {
                "R1 Dashboard": dashboard,
                "R1每日訊號資料庫": signals,
                "R1模擬交易紀錄": [list(TAB_SCHEMAS["R1模擬交易紀錄"])],
            },
        }
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "payload.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            fake = FakeSheetsClient("sheet")
            with patch.object(dashboard_publish, "SheetsClient", return_value=fake):
                with patch.object(dashboard_publish, "_format_workbook"):
                    result = dashboard_publish.publish_payload("sheet", path)
        self.assertEqual(result["signal_rows_for_date"], 14)
        self.assertEqual(result["transaction_rows"], 0)
        self.assertEqual(len(fake.values["R1每日訊號資料庫"]), 16)


if __name__ == "__main__":
    unittest.main()
