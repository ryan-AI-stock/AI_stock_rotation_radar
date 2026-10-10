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
            "R1績效每日比較": [list(TAB_SCHEMAS["R1績效每日比較"])],
            "R1每日換倉建議": [list(TAB_SCHEMAS["R1每日換倉建議"])],
            "R1每日訊號資料庫": [
                list(TAB_SCHEMAS["R1每日訊號資料庫"]),
                ["2026-10-01", "2330"],
                ["2026-10-02", "9999"],
            ],
            "R1實際交易紀錄": [list(TAB_SCHEMAS["R1實際交易紀錄"])],
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
    def test_dashboard_section_formatting_is_derived_from_content(self):
        rows = [["Ryan｜R1實際帳戶總覽與換倉顧問"], ["資料"], ["01｜排名"], ["順位", "股票"],
                ["Top1"], ["05｜模型完整說明"], ["說明"]]
        self.assertEqual(dashboard_publish._section_rows(rows), ([2, 5], [3], 6))

    def test_actual_holding_rows_are_detected_for_highlight(self):
        rows = [["標題"], ["題材", "股票", "分數", "實際持有"],
                ["記憶體 Top1", "2408 南亞科", 90, ""],
                ["載板 Top1", "3037 欣興", 88, "實際持有"]]
        self.assertEqual(dashboard_publish._holding_rows(rows), [3])

    def test_publishes_current_date_preserves_signal_history_and_keeps_transactions_empty(self):
        date = "2026-10-02"
        dashboard = [["Ryan｜R1實際帳戶總覽與換倉顧問"], ["最新資料日期", date, "模型定位", "研究挑戰版", "尚未啟用交易"]]
        dashboard.extend([[f"section-{i}"] for i in range(18)])
        signals = [list(TAB_SCHEMAS["R1每日訊號資料庫"])]
        for index in range(14):
            signals.append([date, f"{2300 + index:04d}", "測試", *([None] * 20), "DATA_MISSING", "blocked"])
        payload = {
            "date": date,
            "tabs": {
                "R1 Dashboard": dashboard,
                "R1績效每日比較": [list(TAB_SCHEMAS["R1績效每日比較"]),
                    [date, "ACTUAL", None, None, None, None, None, "SEED_RECONCILIATION_REQUIRED", "待對帳"]],
                "R1每日換倉建議": [list(TAB_SCHEMAS["R1每日換倉建議"]),
                    [date, "NO_ACTION", "HOLD", "", "", "", None, None, "LOW", "資料不足", "資料不足", "不執行"]],
                "R1每日訊號資料庫": signals,
                "R1實際交易紀錄": [list(TAB_SCHEMAS["R1實際交易紀錄"])],
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
        self.assertEqual(result["performance_rows"], 1)
        self.assertEqual(result["recommendation_rows"], 1)
        self.assertEqual(len(fake.values["R1每日訊號資料庫"]), 16)


if __name__ == "__main__":
    unittest.main()
