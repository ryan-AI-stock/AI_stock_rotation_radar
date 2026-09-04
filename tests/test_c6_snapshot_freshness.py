import unittest
from datetime import datetime
from zoneinfo import ZoneInfo

from rotation_radar.c6_snapshot_freshness import expected_latest_weekday, validate_payload_freshness


class C6SnapshotFreshnessTests(unittest.TestCase):
    def test_before_close_expects_previous_trading_weekday(self):
        now = datetime(2026, 9, 4, 8, 0, tzinfo=ZoneInfo("Asia/Taipei"))
        self.assertEqual(expected_latest_weekday(now), "2026-09-03")

    def test_monday_before_close_expects_friday(self):
        now = datetime(2026, 9, 7, 8, 0, tzinfo=ZoneInfo("Asia/Taipei"))
        self.assertEqual(expected_latest_weekday(now), "2026-09-04")

    def test_stale_payload_is_rejected(self):
        now = datetime(2026, 9, 4, 17, 0, tzinfo=ZoneInfo("Asia/Taipei"))
        with self.assertRaisesRegex(RuntimeError, "snapshot is stale"):
            validate_payload_freshness({"ranking_snapshot_as_of": "2026-09-03"}, now)


if __name__ == "__main__":
    unittest.main()
