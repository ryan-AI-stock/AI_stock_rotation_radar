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
        self.assertEqual(values["提領候選槽"], "無法估算｜尚無權威整股帳本")
        self.assertEqual(values["預計賣出股數"], "")

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

    def test_partial_dashboard_keeps_withdrawal_schedule_but_not_a_fabricated_sale(self):
        values = dict(build_dashboard_values(
            model_version="c6-research-v2", snapshot_as_of="2026-08-28",
            data_status="partial_rankings_only_no_whole_share_replay", slots=[],
            historical_benchmark={"statistical_median_final_nav": 51_306_948.89, "lower_median_actual_route_id": "R38_2023-03-09"},
        ))
        self.assertEqual(values["下次提領排定日"], "2026-09-09")
        self.assertEqual(values["下下次提領排定日"], "2026-10-14")
        self.assertEqual(values["提領候選槽"], "無法估算｜尚無權威整股帳本")
        self.assertEqual(values["64條期末資產統計中位數"], 51_306_948.89)


if __name__ == "__main__":
    unittest.main()
