import json
import tempfile
import unittest
from pathlib import Path

from r1.actual_account import build_actual_account


class ActualAccountTest(unittest.TestCase):
    def test_current_confirmed_positions_keep_remaining_globalwafers_shares(self):
        root = Path(__file__).resolve().parents[1]
        result = build_actual_account(
            date="2026-10-08", config_path=root / "config/r1.json",
            market_path=root / "data/r1/daily_market_latest.json",
        )
        globalwafers = next(row for row in result["positions"] if row["ticker"] == "6488")
        self.assertEqual(globalwafers["shares"], 500)
        self.assertEqual(result["equity_market_value"], 12468534.0)

    def test_equity_is_visible_while_unknown_cash_blocks_nav(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            config = root / "config.json"
            market = root / "market.json"
            config.write_text(json.dumps({
                "version": "r1-0.1.0", "action_policy_approved": False, "timezone": "Asia/Taipei",
                "weights": {"eps_revision": .3, "forward_valuation": .25, "bottleneck": .2, "catalyst": .15, "price_chip": .1},
                "score_policy": {
                    "version": "r1-score-v0.1-research",
                    "eps_revision": {"weights": {"1w": .2, "4w": .5, "12w": .3}},
                    "forward_valuation": {"weights": {"own_forward_pe": .45, "base_upside": .35, "next_year_eps_growth": .2}},
                    "bottleneck": {"weights": {"stage": .6, "tightness": .2, "financial_proof": .2}, "stage_scores": {"THESIS": 1}, "financial_proof_stage_scores": {"THESIS": 1}, "tightness_event_scores": {"X": 1}},
                    "catalyst": {"event_policy": {"X": {"impact": 1, "expiry_weeks": 1}}},
                    "price_chip": {"weights": {"earnings_vs_price": .4, "overheat_safety": .3, "institutional": .2, "leverage_structure": .1}},
                },
                "rotation": {"max_weekly_rotation": .1, "shadow_policy_approved": True, "overheat_percentile": .95, "minimum_score_advantage": 10, "staged_transfer_fraction": .25, "max_holdings": 5},
                "securities": [{"ticker": "2330", "company": "台積電", "market": "TWSE", "shares": 2, "core_lock": True, "roles": ["PORTFOLIO"]}],
            }), encoding="utf-8")
            market.write_text(json.dumps({"rows": [{"ticker": "2330", "raw_close": 1000}]}), encoding="utf-8")
            result = build_actual_account(date="2026-10-08", config_path=config, market_path=market)
        self.assertEqual(result["equity_market_value"], 2000)
        self.assertIsNone(result["nav"])
        self.assertEqual(result["status"], "CASH_RECONCILIATION_REQUIRED")


if __name__ == "__main__":
    unittest.main()
