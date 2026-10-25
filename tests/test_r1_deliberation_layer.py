import json
import tempfile
import unittest
from pathlib import Path

from r1.deliberation_layer import build_deliberation


class R1DeliberationLayerTest(unittest.TestCase):
    def _write(self, root, name, payload):
        path = Path(root) / name
        path.write_text(json.dumps(payload), encoding="utf-8")
        return path

    def _inputs(self, root, context_row):
        context = self._write(root, "context.json", {
            "date": "2026-10-22", "rows": [context_row],
        })
        score = self._write(root, "score.json", {"date": "2026-10-22", "rows": []})
        account = self._write(root, "account.json", {"date": "2026-10-22", "positions": []})
        themes = self._write(root, "themes.json", {
            "as_of_date": "2026-10-01", "target_portfolio_6m": [],
        })
        return context, score, account, themes

    def test_market_selloff_with_accelerating_revenue_is_watch_not_buy(self):
        with tempfile.TemporaryDirectory() as folder:
            inputs = self._inputs(folder, {
                "ticker": "2330", "company": "台積電", "context_state": "MARKET_WIDE_SELLOFF",
                "broad_selloff": True, "price_weak": True,
                "monthly_revenue_state": "ACCELERATING", "positive_event_count": 0,
                "official_negative_event_types": [], "evidence_urls": [],
            })
            result = build_deliberation(
                as_of_date="2026-10-22", context_path=inputs[0], score_path=inputs[1],
                account_path=inputs[2], themes_path=inputs[3], history_root=Path(folder) / "history",
            )
            row = result["rows"][0]
            self.assertEqual(row["conclusion"], "WATCH_POTENTIAL_DISLOCATION")
            self.assertNotIn("BUY", row["conclusion"])

    def test_single_official_risk_remains_pending_confirmation(self):
        with tempfile.TemporaryDirectory() as folder:
            inputs = self._inputs(folder, {
                "ticker": "2454", "company": "聯發科", "context_state": "FUNDAMENTAL_RISK_REVIEW",
                "broad_selloff": True, "price_weak": True,
                "monthly_revenue_state": "NOT_ACCELERATING", "positive_event_count": 1,
                "official_negative_event_types": ["FINANCIAL_EARNINGS_CONTRACTION"],
                "evidence_urls": ["https://example.test/official"],
            })
            result = build_deliberation(
                as_of_date="2026-10-22", context_path=inputs[0], score_path=inputs[1],
                account_path=inputs[2], themes_path=inputs[3], history_root=Path(folder) / "history",
            )
            row = result["rows"][0]
            self.assertEqual(row["conclusion"], "HOLD_PENDING_CONFIRMATION")
            self.assertTrue(row["contradictions"])

