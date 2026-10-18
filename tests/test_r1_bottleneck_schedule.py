import unittest
import json
import tempfile
from datetime import date, datetime
from pathlib import Path

from r1.bottleneck import load_bottleneck_map
from r1.schedule import decide, weekly_output_complete


ROOT = Path(__file__).resolve().parents[1]


class R1BottleneckScheduleTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.rules = Path(self.temp.name) / "rules.json"
        self.rules.write_text(json.dumps({"profiles": {
            "daily": {"run_after": "15:00"}, "weekly": {"run_after": "15:00"}
        }}), encoding="utf-8")

    def tearDown(self):
        self.temp.cleanup()

    def test_seed_map_covers_universe_but_scores_are_missing(self):
        payload = load_bottleneck_map(ROOT / "data/r1/bottleneck_map.json", ROOT / "config/r1.json")
        self.assertEqual(len(payload["rows"]), 54)
        self.assertTrue(all(row["bottleneck_score"] is None for row in payload["rows"]))

    def test_weekly_rejects_thursday_when_friday_open(self):
        open_dates = {date(2026, 10, 1), date(2026, 10, 2)}
        result = decide(now=datetime.fromisoformat("2026-10-01T19:00:00+08:00"), profile="weekly",
                        rules_path=self.rules, open_dates=open_dates, closed_dates=set())
        self.assertEqual(result, (False, None, "not_last_trading_day_of_week"))

    def test_weekly_accepts_thursday_when_friday_closed(self):
        open_dates = {date(2026, 10, 1)}
        result = decide(now=datetime.fromisoformat("2026-10-01T19:00:00+08:00"), profile="weekly",
                        rules_path=self.rules, open_dates=open_dates, closed_dates={date(2026, 10, 2)})
        self.assertEqual(result, (True, date(2026, 10, 1), "last_trading_day_of_week"))

    def test_weekly_output_complete_requires_matching_full_public_core(self):
        root = Path(self.temp.name)
        weekly = root / "weekly"
        weekly.mkdir()
        target = date(2026, 10, 16)
        weekly.joinpath("weekly_snapshot_2026-10-16.json").write_text(json.dumps({
            "date": "2026-10-16", "future_data_violation_count": 0,
        }), encoding="utf-8")
        dashboard = root / "dashboard.json"
        dashboard.write_text(json.dumps({"date": "2026-10-16"}), encoding="utf-8")
        rank = root / "rank.json"
        rank.write_text(json.dumps({
            "date": "2026-10-16", "requested_ticker_count": 52,
            "ready_ticker_count": 52, "future_data_violation_count": 0,
        }), encoding="utf-8")
        self.assertTrue(weekly_output_complete(
            target=target, weekly_root=weekly, dashboard_path=dashboard, rank_path=rank,
        ))
        rank.write_text(json.dumps({
            "date": "2026-10-16", "requested_ticker_count": 52,
            "ready_ticker_count": 51, "future_data_violation_count": 0,
        }), encoding="utf-8")
        self.assertFalse(weekly_output_complete(
            target=target, weekly_root=weekly, dashboard_path=dashboard, rank_path=rank,
        ))


if __name__ == "__main__":
    unittest.main()
