import json
import inspect
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from r1 import dashboard_payload, dashboard_publish
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
    def test_dashboard_uses_v05_seven_component_rotation_weights(self):
        source = inspect.getsource(dashboard_payload._build_v03_dashboard)
        self.assertIn("每日換倉優先序", source)
        self.assertIn("20%／20%／20%／10%／10%／10%／10%", source)
        self.assertNotIn("30%／25%／20%／15%／10%", source)

    def test_dashboard_section_formatting_is_derived_from_content(self):
        rows = [["Ryan｜R1實際帳戶總覽與換倉顧問"], ["資料"], ["01｜排名"], ["順位", "股票"],
                ["Top1"], ["05｜模型完整說明"], ["說明"]]
        self.assertEqual(dashboard_publish._section_rows(rows), ([2, 5], [3], 6))

    def test_actual_holding_rows_are_detected_for_highlight(self):
        rows = [["標題"], ["題材", "股票", "分數", "實際持有"],
                ["記憶體 Top1", "2408 南亞科", 90, ""],
                ["載板 Top1", "3037 欣興", 88, "實際持有"]]
        self.assertEqual(dashboard_publish._holding_rows(rows), [3])

    def test_performance_rows_receive_readable_height(self):
        rows = [["Ryan｜R1實際帳戶總覽與換倉顧問"], ["02｜兩條績效線"],
                ["比較線", "當日NAV", "本金", "報酬", "狀態", "差額"],
                ["Ryan實際操作帳戶", 1200, 1000, .2, "READY", ""],
                ["8/5全部轉0050正二後長抱", 1100, 1000, .1, "READY", "=B21-B20"]]
        client = unittest.mock.Mock()
        client.base = "https://sheets.googleapis.com/v4/spreadsheets/x"
        client.headers = {}
        metadata = {"sheets": [{"properties": {"sheetId": index + 1, "title": title}}
                               for index, title in enumerate(("R1 Dashboard", "R1績效每日比較",
                                                              "R1每日換倉建議", "R1每日訊號資料庫",
                                                              "R1實際交易紀錄"))]}
        with patch.object(dashboard_publish, "retry_request") as request:
            request.return_value.json.return_value = metadata
            dashboard_publish._format_workbook(client, rows)
        body = request.call_args_list[-1].kwargs["json"]["requests"]
        heights = [item["updateDimensionProperties"] for item in body
                   if "updateDimensionProperties" in item
                   and item["updateDimensionProperties"]["range"]["dimension"] == "ROWS"]
        self.assertTrue(any(item["range"].get("startIndex") == 3
                            and item["properties"]["pixelSize"] >= 60 for item in heights))

    def test_dashboard_numeric_formats_use_one_decimal(self):
        rows = [
            ["Ryan｜R1實際帳戶總覽與換倉顧問"],
            ["01｜實際持股與未來半年目標持股"],
            ["所屬題材", "股票", "優先持有參考值", "實際持有", "當日收盤", "持股市值", "持股占比", "半年目標"],
            ["記憶體", "2408 南亞科", "評分資料未齊", "實際持有｜1,147股", 532, 610204, .041, "目標"],
            ["02｜兩條績效線"],
            ["比較線", "當日NAV", "累計投入本金", "累積報酬", "狀態", "相較實際操作差額"],
            ["Ryan實際操作帳戶", 14823234, 8105075, "不發布", "待對帳", ""],
            ["8/5全部轉0050正二後長抱", 9515305.6, 8105075, .174, "READY", "=B21-B20"],
            ["04｜無差別殺盤過渡層（研究觀察）"],
            ["狀態", "NOT_TRIGGERED", "候選池下跌比例", .698],
            ["加權指數單日報酬", -.01],
        ]
        client = unittest.mock.Mock()
        client.base = "https://sheets.googleapis.com/v4/spreadsheets/x"
        client.headers = {}
        metadata = {"sheets": [{"properties": {"sheetId": index + 1, "title": title}}
                               for index, title in enumerate(("R1 Dashboard", "R1績效每日比較",
                                                              "R1每日換倉建議", "R1每日訊號資料庫",
                                                              "R1實際交易紀錄"))]}
        with patch.object(dashboard_publish, "retry_request") as request:
            request.return_value.json.return_value = metadata
            dashboard_publish._format_workbook(client, rows)
        body = request.call_args_list[-1].kwargs["json"]["requests"]
        patterns = [item["repeatCell"]["cell"]["userEnteredFormat"]["numberFormat"]["pattern"]
                    for item in body if "repeatCell" in item
                    and "numberFormat" in item["repeatCell"]["cell"].get("userEnteredFormat", {})]
        self.assertIn("#,##0.0", patterns)
        self.assertIn("0.0%", patterns)

    def test_readback_treats_empty_cells_and_omitted_trailing_cells_as_blank(self):
        self.assertTrue(dashboard_publish._equivalent_sheet_rows(
            [["date", "value", "note"], ["2026-10-08", "", "ok"], ["x"]],
            [["date", "value", "note"], ["2026-10-08", None, "ok"], ["x", None, None]],
        ))

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
