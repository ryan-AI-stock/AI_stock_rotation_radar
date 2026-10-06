import json
import tempfile
import unittest
from pathlib import Path

from r1.financial_quality import _absolute_scores, parse_financial_facts
from r1.theme_leader_inputs import _load_financial_quality


class R1FinancialQualityTest(unittest.TestCase):
    def test_parses_exact_current_prior_and_balance_contexts(self):
        page = """
        <ix:nonFraction name="ifrs-full:Revenue" contextRef="From20260101To20260630" scale="3">120</ix:nonFraction>
        <ix:nonFraction name="ifrs-full:Revenue" contextRef="From20250101To20250630" scale="3">100</ix:nonFraction>
        <ix:nonFraction name="ifrs-full:CurrentAssets" contextRef="AsOf20260630" scale="3">80</ix:nonFraction>
        <ix:nonFraction name="ifrs-full:CurrentAssets" contextRef="AsOf20251231" scale="3">70</ix:nonFraction>
        """
        facts = parse_financial_facts(page, report_year=2026, quarter=2)
        self.assertEqual(facts["current_revenue"], 120000)
        self.assertEqual(facts["prior_revenue"], 100000)
        self.assertEqual(facts["current_assets"], 80000)

    def test_negative_ocf_is_capped(self):
        rubric = {
            "anchors": {"revenue_yoy_pct": [-20, 30], "margin_change_pp": [-5, 5],
                        "eps_yoy_pct": [-30, 40], "cash_conversion": [0, 1.2],
                        "current_ratio": [0.75, 2], "liabilities_to_assets_pct": [80, 40]},
            "rules": {"negative_current_operating_margin_cap": 25,
                      "negative_current_eps_cap": 20,
                      "negative_current_operating_cash_flow_cap": 20},
        }
        metrics = {"revenue_yoy_pct": 10, "gross_margin_change_pp": 1,
                   "operating_margin_change_pp": 1, "operating_margin_pct": 10,
                   "eps_yoy_pct": 10, "current_eps": 2, "prior_eps": 1,
                   "operating_cash_flow": -10, "cash_conversion": 2,
                   "current_ratio": 2, "liabilities_to_assets_pct": 40}
        scores = _absolute_scores(metrics, rubric)
        self.assertEqual(scores["operating_cash_flow_quality"], 20)

    def test_ready_score_becomes_auditable_theme_input(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "quality.json"
            path.write_text(json.dumps({
                "as_of_date": "2026-10-05", "rubric_version": "rubric-v1",
                "rows": [{"ticker": "2330", "status": "READY",
                          "financial_earnings_quality": 88.5,
                          "source_url": "https://mops.example/2330"}],
            }), encoding="utf-8")
            rows = _load_financial_quality(path, "2026-10-05")
        self.assertEqual(rows["2330"]["financial_earnings_quality"], 88.5)
        self.assertEqual(rows["2330"]["evidence"]["source_family"], "MOPS_XBRL_OFFICIAL")

    def test_future_quality_snapshot_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "quality.json"
            path.write_text(json.dumps({"as_of_date": "2026-10-06", "rows": []}), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "future"):
                _load_financial_quality(path, "2026-10-05")


if __name__ == "__main__":
    unittest.main()
