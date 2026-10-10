import unittest
from pathlib import Path

from r1.dashboard_payload import build_dashboard_payload
from r1.dashboard_schema import TAB_SCHEMAS, validate_tabs


ROOT = Path(__file__).resolve().parents[1]


class R1DashboardPayloadTest(unittest.TestCase):
    def test_exact_five_tabs_exist_and_validate(self):
        payload = build_dashboard_payload(config_path=ROOT / "config/r1.json",
                                          market_path=ROOT / "data/r1/theme_daily_market_latest.json")
        self.assertEqual(set(payload["tabs"]), set(TAB_SCHEMAS))
        validate_tabs(payload["tabs"])
        self.assertEqual(set(payload["tabs"]), {"R1 Dashboard", "R1績效每日比較", "R1每日換倉建議", "R1每日訊號資料庫", "R1實際交易紀錄"})
        self.assertEqual(len(payload["tabs"]["R1每日訊號資料庫"]), 55)
        self.assertEqual(len(payload["tabs"]["R1實際交易紀錄"]), 5)
        dashboard = payload["tabs"]["R1 Dashboard"]
        sections = [row[0] for row in dashboard]
        self.assertIn("01｜實際持股與未來半年目標持股", sections)
        self.assertIn("02｜三條績效線", sections)
        self.assertIn("03｜今日換倉建議", sections)
        self.assertIn("04｜無差別殺盤過渡層（研究觀察）", sections)
        self.assertIn("05｜分數規則", sections)
        self.assertIn("06｜更新排程", sections)
        self.assertIn("07｜模型完整說明", sections)
        self.assertNotIn("06｜下一個動態觸發條件", sections)
        self.assertNotIn("07｜Shadow換倉候選（非交易指令）", sections)
        shown = {str(row[1]).split()[0] for row in dashboard if len(row) >= 5 and str(row[0]) not in ("所屬題材",)}
        self.assertTrue({"2454", "2408", "3081", "2308", "3037"} <= shown)
        self.assertIn("2303", shown)
        self.assertNotIn("2327", shown)

    def test_dashboard_cannot_claim_trade_ready(self):
        payload = build_dashboard_payload(config_path=ROOT / "config/r1.json",
                                          market_path=ROOT / "data/r1/theme_daily_market_latest.json")
        actions = payload["tabs"]["R1 Dashboard"]
        self.assertIn("不自動成交", [cell for row in actions for cell in row])
        signals = payload["tabs"]["R1每日訊號資料庫"]
        self.assertEqual(next(row for row in signals if row[1] == "2330")[23], "CORE")

    def test_complete_theme_review_materializes_top3_and_priority_score(self):
        import json
        import tempfile
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            review = root / "theme_review.json"
            review.write_text(json.dumps({"themes": [{
                "theme_id": "memory_storage", "status": "READY", "top3": [
                    {"ticker": "2408", "company": "南亞科", "leader_score": 90, "priority_score": 81.5},
                    {"ticker": "2344", "company": "華邦電", "leader_score": 85, "priority_score": 75},
                    {"ticker": "2337", "company": "旺宏", "leader_score": 80, "priority_score": 70},
                ]
            }]}), encoding="utf-8")
            payload = build_dashboard_payload(
                config_path=ROOT / "config/r1.json", market_path=ROOT / "data/r1/theme_daily_market_latest.json",
                theme_review_path=review,
            )
        dashboard = payload["tabs"]["R1 Dashboard"]
        self.assertIn("2408 南亞科", [cell for row in dashboard for cell in row])
        row = next(row for row in dashboard if len(row) > 1 and row[1] == "2408 南亞科")
        self.assertEqual(row[2], 81.5)

    def test_header_mismatch_is_rejected(self):
        tabs = {title: [list(headers)] for title, headers in TAB_SCHEMAS.items()}
        tabs["R1 Dashboard"] = [["Ryan｜R1實際帳戶總覽與換倉顧問"]]
        tabs["R1每日訊號資料庫"][0][0] = "wrong"
        with self.assertRaisesRegex(ValueError, "header mismatch"):
            validate_tabs(tabs)

    def test_legacy_revision_data_is_not_exposed_in_v03_dashboard(self):
        import tempfile
        with tempfile.TemporaryDirectory() as folder:
            history = Path(folder) / "revision.csv"
            history.write_text(
                "ticker,fiscal_year,source_data_date,eps_90d,eps_60d,eps_30d,eps_current,"
                "revision_30d,revision_90d,source_url,available_at,retrieved_at,basis,status\n"
                "2330,2026,2026-10-01,90,95,100,110,.1,.222,x,2026-10-01,2026-10-02,"
                "SOURCE_REPORTED_OFFSETS,SUPPLEMENTAL_NOT_TOTAL_SCORE\n",
                encoding="utf-8",
            )
            payload = build_dashboard_payload(
                config_path=ROOT / "config/r1.json",
                market_path=ROOT / "data/r1/theme_daily_market_latest.json",
                supplemental_revision_path=history,
            )
        self.assertNotIn("30D +10.0%／90D +22.2%（不計分）",
                         [cell for row in payload["tabs"]["R1 Dashboard"] for cell in row])
        self.assertFalse(payload["active_in_trade_decision"])


if __name__ == "__main__":
    unittest.main()
