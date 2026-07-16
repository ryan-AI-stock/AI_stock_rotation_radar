from __future__ import annotations

import sys
import unittest
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from run_p1_p2_primary80_path_independent_raw_close_local_audit import (
    assign_market,
    classify,
    merge_intervals,
)


class Primary80PathIndependentRawCloseAuditTest(unittest.TestCase):
    def test_market_assignment_uses_historical_snapshot_not_current_status(self) -> None:
        history = pd.DataFrame({
            "snapshot_date": pd.to_datetime(["2023-01-06", "2023-06-02"]),
            "market": ["TPEx", "TWSE"],
        })
        dates = list(pd.to_datetime(["2022-12-30", "2023-05-31", "2023-06-02"]))

        self.assertEqual(assign_market(history, dates), ["TPEx", "TPEx", "TWSE"])

    def test_adjacent_source_scope_intervals_are_coalesced(self) -> None:
        ranges = [
            (pd.Timestamp("2020-01-01"), pd.Timestamp("2020-01-03")),
            (pd.Timestamp("2020-01-04"), pd.Timestamp("2020-01-06")),
        ]

        self.assertEqual(merge_intervals(ranges), [(pd.Timestamp("2020-01-01"), pd.Timestamp("2020-01-06"))])

    def test_classification_preserves_required_market_for_route_plan(self) -> None:
        day = pd.Timestamp("2020-01-02")
        requirements = pd.DataFrame([{
            "ticker": "2330", "date": day, "market": "TWSE", "markets": "TWSE",
            "market_policy_blocked": False,
        }])
        close_index = pd.DataFrame(columns=["ticker", "date", "close", "market"])
        routes = pd.DataFrame([{
            "market": "TWSE", "date": day, "route_response_valid": False,
        }])

        result = classify(
            requirements, close_index, pd.DataFrame(columns=["ticker", "date"]),
            {}, {}, {}, {}, {}, routes, prior_no_trade=set(),
        )

        self.assertEqual(result.loc[0, "market"], "TWSE")
        self.assertEqual(result.loc[0, "classification"], "true_missing")

    def test_classification_uses_injected_prior_no_trade_without_local_artifact(self) -> None:
        day = pd.Timestamp("2020-01-02")
        requirements = pd.DataFrame([{
            "ticker": "2330", "date": day, "market": "TWSE", "markets": "TWSE",
            "market_policy_blocked": False,
        }])
        close_index = pd.DataFrame(columns=["ticker", "date", "close", "market"])
        routes = pd.DataFrame([{
            "market": "TWSE", "date": day, "route_response_valid": True,
        }])

        result = classify(
            requirements, close_index, pd.DataFrame(columns=["ticker", "date"]),
            {}, {}, {}, {}, {}, routes, prior_no_trade={("2330", day)},
        )

        self.assertEqual(result.loc[0, "classification"], "official_no_trade_or_termination")
        self.assertEqual(result.loc[0, "classification_reason"], "prior_official_market_file_valid_exact_ticker_absent")


if __name__ == "__main__":
    unittest.main()
