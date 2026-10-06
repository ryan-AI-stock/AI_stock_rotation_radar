import json
import tempfile
import unittest
from pathlib import Path

from r1.official_financial_snapshot import build_snapshot, parse_operating_cash_flow


ROOT = Path(__file__).resolve().parents[1]


class R1OfficialFinancialSnapshotTest(unittest.TestCase):
    def test_parses_current_cumulative_xbrl_cash_flow_with_scale_and_sign(self):
        page = """
        <ix:nonFraction name="ifrs-full:CashFlowsFromUsedInOperatingActivities"
          contextRef="From20260101To20260630" scale="3">1,234</ix:nonFraction>
        <ix:nonFraction name="ifrs-full:CashFlowsFromUsedInOperatingActivities"
          contextRef="From20250101To20250630" scale="3" sign="-">999</ix:nonFraction>
        """
        value, context = parse_operating_cash_flow(page, report_year=2026, quarter=2)
        self.assertEqual(value, 1_234_000)
        self.assertEqual(context, "From20260101To20260630")

    def test_exact_universe_and_missing_are_explicit(self):
        sample_income = [{"公司代號": "2330", "年度": "115", "季別": "2", "出表日期": "1151005",
                          "營業收入": "100", "本期淨利（淨損）": "20", "基本每股盈餘（元）": "2"}]
        sample_balance = [{"公司代號": "2330", "年度": "115", "季別": "2", "出表日期": "1151005",
                           "資產總計": "200", "負債總計": "80", "權益總計": "120"}]
        with tempfile.TemporaryDirectory() as directory:
            payload = build_snapshot(
                as_of_date="2026-10-05", theme_path=ROOT / "config/r1_v02_themes.json",
                output_path=Path(directory) / "out.json",
                payloads={"TWSE_income": sample_income, "TWSE_balance": sample_balance,
                          "TPEx_income": [], "TPEx_balance": []},
            )
        self.assertEqual(payload["requested_ticker_count"], 54)
        self.assertEqual(payload["actual_ticker_count"], 0)
        self.assertEqual(next(row for row in payload["rows"] if row["ticker"] == "2330")["eps"], 2)
        self.assertTrue(payload["gaps"])

    def test_cash_flow_completes_ready_row(self):
        sample_income = [{"公司代號": "2330", "年度": "115", "季別": "2", "出表日期": "1151005",
                          "營業收入": "100", "本期淨利（淨損）": "20", "基本每股盈餘（元）": "2"}]
        sample_balance = [{"公司代號": "2330", "年度": "115", "季別": "2", "出表日期": "1151005",
                           "資產總計": "200", "負債總計": "80", "權益總計": "120"}]
        page = ('<ix:nonFraction name="ifrs-full:CashFlowsFromUsedInOperatingActivities" '
                'contextRef="From20260101To20260630" scale="3" sign="-">12</ix:nonFraction>')
        with tempfile.TemporaryDirectory() as directory:
            payload = build_snapshot(
                as_of_date="2026-10-05", theme_path=ROOT / "config/r1_v02_themes.json",
                output_path=Path(directory) / "out.json",
                payloads={"TWSE_income": sample_income, "TWSE_balance": sample_balance,
                          "TPEx_income": [], "TPEx_balance": []},
                cash_flow_pages={"2330": page},
            )
        row = next(row for row in payload["rows"] if row["ticker"] == "2330")
        self.assertEqual(row["operating_cash_flow"], -12_000)
        self.assertEqual(row["status"], "READY")

    def test_exact_period_cache_is_reused(self):
        sample_income = [{"公司代號": "2330", "年度": "115", "季別": "2", "出表日期": "1151005"}]
        sample_balance = [{"公司代號": "2330", "年度": "115", "季別": "2", "出表日期": "1151005"}]
        with tempfile.TemporaryDirectory() as directory:
            cache = Path(directory) / "cache.json"
            cache.write_text(json.dumps({"facts": {"2330:2026:Q2": {
                "ticker": "2330", "report_year": 2026, "quarter": 2,
                "operating_cash_flow": 123.0, "context": "From20260101To20260630",
                "source_url": "https://mops.example/2330",
            }}}), encoding="utf-8")
            payload = build_snapshot(
                as_of_date="2026-10-05", theme_path=ROOT / "config/r1_v02_themes.json",
                output_path=Path(directory) / "out.json",
                payloads={"TWSE_income": sample_income, "TWSE_balance": sample_balance,
                          "TPEx_income": [], "TPEx_balance": []},
                cash_flow_cache_path=cache,
            )
        row = next(row for row in payload["rows"] if row["ticker"] == "2330")
        self.assertEqual(row["operating_cash_flow"], 123.0)
        self.assertEqual(row["status"], "READY")


if __name__ == "__main__":
    unittest.main()
