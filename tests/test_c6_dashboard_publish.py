import unittest

from rotation_radar.c6_dashboard_publish import _append_only, build_dashboard_values, select_withdrawal_slot


class C6DashboardPublishTests(unittest.TestCase):
    def test_withdrawal_prefers_lowest_relative_return_slot(self):
        result = select_withdrawal_slot([
            {"slot_id": "A", "ticker": "1111", "shares": 1000, "raw_close": 100, "position_cost": 90_000},
            {"slot_id": "B", "ticker": "2222", "shares": 1000, "raw_close": 100, "position_cost": 110_000},
            {"slot_id": "C", "ticker": "3333", "shares": 1000, "raw_close": 100, "position_cost": 100_000},
        ])
        self.assertEqual(result["slot_id"], "B")
        self.assertEqual(result["planned_shares"], 750)
        self.assertLess(result["relative_return_pct"], 0)

    def test_dashboard_declares_research_version_and_missing_data(self):
        values = dict(build_dashboard_values(
            model_version="c6-research-v1", snapshot_as_of="2026-08-30T15:00:00+08:00",
            data_status="blocked_source_or_replay_not_materialized", slots=[], notes="C6 daily source/replay pending",
        ))
        self.assertEqual(values["model_version"], "c6-research-v1")
        self.assertEqual(values["data_status"], "blocked_source_or_replay_not_materialized")
        self.assertEqual(values["提領候選槽"], "空手／現金")

    def test_cash_sufficient_for_withdrawal_does_not_sell_a_slot(self):
        result = select_withdrawal_slot(
            [{"slot_id": "A", "ticker": "1111", "shares": 1000, "raw_close": 100, "position_cost": 90_000}],
            cash=80_000,
        )
        self.assertEqual(result["status"], "cash_withdrawal")
        self.assertEqual(result["planned_shares"], 0)

    def test_same_version_snapshot_is_not_overwritten(self):
        headers = ["model_version", "snapshot_as_of", "signal_date", "rank"]
        existing = [headers, ["c6-v1", "2026-08-05T15:00:00+08:00", "2026-08-05", 1]]
        additions = _append_only(
            existing, headers,
            [{"model_version": "c6-v1", "snapshot_as_of": "2026-08-05T15:00:00+08:00", "signal_date": "2026-08-05", "rank": 1}],
            ("model_version", "snapshot_as_of", "signal_date", "rank"),
        )
        self.assertEqual(additions, [])


if __name__ == "__main__":
    unittest.main()
