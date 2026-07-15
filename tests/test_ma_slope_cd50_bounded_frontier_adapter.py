from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path

import pandas as pd


SCRIPT = Path(__file__).resolve().parents[1] / "scripts/run_p1_p2_ma_slope_cd50_bounded_frontier_adapter.py"
SPEC = importlib.util.spec_from_file_location("bounded_frontier_adapter", SCRIPT)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError(f"cannot load adapter: {SCRIPT}")
adapter = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(adapter)


class BoundedFrontierAdapterTest(unittest.TestCase):
    def frames(self):
        frontier = pd.DataFrame([{
            "variant_id": "S01_CD2",
            "period": "P1",
            "decision_date": "2020-01-02",
            "ticker": "2330",
            "role": "buy",
            "requested_execution_date": "2020-01-03",
        }])
        request = pd.DataFrame([{
            "period": "P1",
            "ticker": "2330",
            "requested_start": "2020-01-02",
            "requested_end": "2020-01-03",
            "unclassified_dates": "2",
            "network_download_authorized": "False",
        }])
        atomic = pd.DataFrame([{"blocker": "policy_only"}])
        readiness = {
            "frontier_exact_official_raw_gap_legs": 1,
            "incumbent_analysis_unclassified_rows": 2,
            "atomic_policy_blockers": 1,
            "all_provisional_unique_raw_gap_legs": 10,
        }
        return frontier, request, atomic, readiness

    def test_valid_scope_passes(self):
        frontier, request, atomic, readiness = self.frames()
        adapter.validate_preflight(frontier, request, atomic, readiness, 2, 10)

    def test_null_execution_date_is_policy_blocker(self):
        frontier, request, atomic, readiness = self.frames()
        frontier.loc[0, "requested_execution_date"] = ""
        with self.assertRaisesRegex(adapter.PolicyBlocker, "null requested_execution_date"):
            adapter.validate_preflight(frontier, request, atomic, readiness, 2, 10)

    def test_incumbent_network_authority_is_policy_blocker(self):
        frontier, request, atomic, readiness = self.frames()
        request.loc[0, "network_download_authorized"] = "True"
        with self.assertRaisesRegex(adapter.PolicyBlocker, "local-only"):
            adapter.validate_preflight(frontier, request, atomic, readiness, 2, 10)

    def test_market_source_conflict_stops_before_download(self):
        frontier, _request, _atomic, _readiness = self.frames()
        route = pd.DataFrame([{
            "period": "P1",
            "ticker": "2330",
            "requested_execution_date": "2020-01-03",
            "market": "TPEx",
            "trusted_raw_source_url": "https://query1.finance.yahoo.com/2330.TW",
        }])
        with tempfile.TemporaryDirectory() as temp:
            output = Path(temp)
            route.to_csv(output / "frontier_bounded_route_plan.csv", index=False)
            with self.assertRaisesRegex(adapter.PolicyBlocker, "suffix conflicts"):
                adapter.validate_route_plan(output, frontier)


if __name__ == "__main__":
    unittest.main()
