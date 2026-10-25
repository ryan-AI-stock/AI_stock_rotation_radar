import json
import tempfile
import unittest
from pathlib import Path

from r1.context_event_layer import build_context_layer


class R1ContextEventLayerTest(unittest.TestCase):
    def _json(self, root, name, payload):
        path = Path(root) / name
        path.write_text(json.dumps(payload), encoding="utf-8")
        return path

    def test_broad_selloff_does_not_turn_price_weakness_into_company_thesis_break(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            evidence = root / "evidence.csv"
            evidence.write_text(
                "event_date,ticker,event_type,description,source_url,source_family,source_tier,impact_direction,affected_bottleneck,published_at,available_at,retrieved_at,evidence_status\n",
                encoding="utf-8",
            )
            negative = self._json(root, "negative.json", {"date": "2026-10-22", "rows": []})
            market = self._json(root, "market.json", {"date": "2026-10-22", "rows": [
                {"ticker": "2330", "daily_return": -0.03, "return_1w": -0.05, "return_1m": 0.1},
            ]})
            monthly = self._json(root, "monthly.json", {"date": "2026-10-22", "rows": []})
            transition = self._json(root, "transition.json", {
                "date": "2026-10-22", "triggered": True, "session_complete": True,
            })
            result = build_context_layer(
                as_of_date="2026-10-22", config_path="config/r1.json",
                catalyst_evidence_path=evidence, negative_path=negative,
                market_path=market, monthly_revenue_path=monthly, transition_path=transition,
            )
            tsmc = next(row for row in result["rows"] if row["ticker"] == "2330")
            self.assertEqual(tsmc["context_state"], "MARKET_WIDE_SELLOFF")
            self.assertEqual(tsmc["advisory_posture"], "PULLBACK_WATCH_NO_AUTO_BUY")

    def test_official_fundamental_deterioration_requires_review_not_automatic_sale(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            evidence = root / "evidence.csv"
            evidence.write_text(
                "event_date,ticker,event_type,description,source_url,source_family,source_tier,impact_direction,affected_bottleneck,published_at,available_at,retrieved_at,evidence_status\n",
                encoding="utf-8",
            )
            negative = self._json(root, "negative.json", {"date": "2026-10-22", "rows": [{
                "ticker": "2330", "event_type": "FINANCIAL_EARNINGS_CONTRACTION",
                "source_url": "https://example.test/official",
            }]})
            market = self._json(root, "market.json", {"date": "2026-10-22", "rows": []})
            monthly = self._json(root, "monthly.json", {"date": "2026-10-22", "rows": []})
            transition = self._json(root, "transition.json", {
                "date": "2026-10-22", "triggered": False, "session_complete": True,
            })
            result = build_context_layer(
                as_of_date="2026-10-22", config_path="config/r1.json",
                catalyst_evidence_path=evidence, negative_path=negative,
                market_path=market, monthly_revenue_path=monthly, transition_path=transition,
            )
            tsmc = next(row for row in result["rows"] if row["ticker"] == "2330")
            self.assertEqual(tsmc["context_state"], "FUNDAMENTAL_RISK_REVIEW")
            self.assertEqual(tsmc["advisory_posture"], "HOLD_OR_REDUCE_REVIEW")
            self.assertFalse(result["active_in_trade_decision"])
