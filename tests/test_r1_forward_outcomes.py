import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from r1.forward_outcomes import materialize


class R1ForwardOutcomeTest(unittest.TestCase):
    def test_uses_exact_nth_later_observation_and_keeps_longer_horizons_pending(self):
        with TemporaryDirectory() as folder:
            root = Path(folder)
            weekly = root / "weekly"
            daily = root / "daily"
            weekly.mkdir()
            daily.mkdir()
            (weekly / "weekly_snapshot_2026-01-02.json").write_text(json.dumps({
                "date": "2026-01-02", "rows": [{"ticker": "2330", "raw_close": 100}],
            }), encoding="utf-8")
            for offset, day in enumerate(("2026-01-05", "2026-01-06", "2026-01-07", "2026-01-08", "2026-01-09"), 1):
                (daily / f"{day}.json").write_text(json.dumps({
                    "date": day, "price_rows": [{"ticker": "2330", "close": 100 + offset}],
                }), encoding="utf-8")
            result = materialize(as_of_date="2026-01-09", weekly_root=weekly, daily_source_root=daily)
            ready = next(row for row in result["rows"] if row["horizon_td"] == 5)
            pending = next(row for row in result["rows"] if row["horizon_td"] == 20)
            self.assertEqual(ready["exit_date"], "2026-01-09")
            self.assertAlmostEqual(ready["forward_return"], 0.05)
            self.assertEqual(pending["status"], "PENDING")

    def test_future_source_dates_are_not_used(self):
        with TemporaryDirectory() as folder:
            root = Path(folder)
            weekly = root / "weekly"
            daily = root / "daily"
            weekly.mkdir()
            daily.mkdir()
            (weekly / "weekly_snapshot_2026-01-02.json").write_text(
                json.dumps({"date": "2026-01-02", "rows": [{"ticker": "2330", "raw_close": 100}]}),
                encoding="utf-8",
            )
            (daily / "2026-02-01.json").write_text(
                json.dumps({"date": "2026-02-01", "price_rows": [{"ticker": "2330", "close": 999}]}),
                encoding="utf-8",
            )
            result = materialize(as_of_date="2026-01-09", weekly_root=weekly, daily_source_root=daily)
            self.assertTrue(all(row["status"] == "PENDING" for row in result["rows"]))


if __name__ == "__main__":
    unittest.main()
