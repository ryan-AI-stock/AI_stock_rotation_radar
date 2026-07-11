from __future__ import annotations

import csv
import gzip
import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

from rotation_radar.daily_risk_features import IncompleteSourceError, classify_calendar_day, run_date, tdcc_should_append


def source(family: str, market: str, target: str, status: str = "accepted") -> dict:
    return {"family": family, "market": market, "requested_date": target, "actual_source_date": target if status == "accepted" else "", "status": status, "row_count": 1, "source_hash": "abc", "retrieved_at_utc": "2026-07-11T00:00:00+00:00"}


class DailyRiskFeatureTests(unittest.TestCase):
    def test_calendar_weekend_and_scheduled_close(self) -> None:
        self.assertEqual(classify_calendar_day(date(2026, 7, 11), set(), set()), "weekend_closed")
        self.assertEqual(classify_calendar_day(date(2026, 7, 10), set(), {date(2026, 7, 10)}), "scheduled_closed")

    def test_tdcc_no_new_week(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td); path = root / "tdcc/20260703.csv.gz"; path.parent.mkdir(parents=True)
            with gzip.open(path, "wt", encoding="utf-8") as f: f.write("x\n")
            self.assertFalse(tdcc_should_append("20260703", root))
            self.assertTrue(tdcc_should_append("20260710", root))

    def test_market_closed_both_official_no_rows_is_success(self) -> None:
        with self._workspace() as (root, scope):
            no_rows = [source("official_raw_execution_ohlcv", "TWSE", "2026-07-10", "no_rows"), source("official_raw_execution_ohlcv", "TPEx", "2026-07-10", "no_rows")]
            with patch("rotation_radar.daily_risk_features.fetch_price", return_value=([], no_rows)):
                result = run_date(date(2026, 7, 10), root, scope, "calendar_unknown_weekday")
            self.assertEqual(result["status"], "skipped_market_closed")

    def test_source_delay_fails_without_stale_fallback(self) -> None:
        with self._workspace() as (root, scope):
            manifests = [source("official_raw_execution_ohlcv", "TWSE", "2026-07-09"), source("official_raw_execution_ohlcv", "TPEx", "2026-07-09", "blocked")]
            with patch("rotation_radar.daily_risk_features.fetch_price", return_value=([{"date": "2026-07-09"}], manifests)):
                with self.assertRaises(IncompleteSourceError): run_date(date(2026, 7, 9), root, scope, "scheduled_open")

    def test_normal_day_is_idempotent_and_rejects_stale_mandatory_date(self) -> None:
        target = date(2026, 7, 9); target_s = target.isoformat()
        price_manifest = [source("official_raw_execution_ohlcv", "TWSE", target_s), source("official_raw_execution_ohlcv", "TPEx", target_s)]
        chip_manifest = [source(f, m, target_s) for f in ("institutional", "margin_short", "securities_lending") for m in ("TWSE", "TPEx")]
        with self._workspace() as (root, scope):
            patches = [
                patch("rotation_radar.daily_risk_features.fetch_price", return_value=([{"date": target_s, "ticker": "2330"}], price_manifest)),
                patch("rotation_radar.daily_risk_features.fetch_chip_family", return_value=([], chip_manifest)),
                patch("rotation_radar.daily_risk_features.fetch_foreign_ownership", return_value=([], [source("foreign_ownership", "TWSE", target_s), source("foreign_ownership", "TPEx", target_s)])),
                patch("rotation_radar.daily_risk_features.fetch_taifex", return_value=([], source("taifex_foreign_oi", "TAIFEX", target_s))),
                patch("rotation_radar.daily_risk_features.fetch_global", return_value=([], [])),
                patch("rotation_radar.daily_risk_features.fetch_corporate_calendar", return_value=([], [])),
                patch("rotation_radar.daily_risk_features.fetch_tdcc_if_new", return_value=([], source("tdcc_holder_distribution", "TDCC", target_s, "no_rows"))),
            ]
            for p in patches: p.start()
            try:
                self.assertEqual(run_date(target, root, scope, "scheduled_open")["status"], "accepted")
                self.assertEqual(run_date(target, root, scope, "scheduled_open")["status"], "accepted")
            finally:
                for p in reversed(patches): p.stop()
            path = root / "daily/2026/07/09/official_raw_execution_ohlcv.csv.gz"
            with gzip.open(path, "rt", encoding="utf-8") as f: self.assertEqual(len(list(csv.DictReader(f))), 1)

            stale = [source("official_raw_execution_ohlcv", "TWSE", target_s), source("official_raw_execution_ohlcv", "TPEx", target_s)]
            stale[0]["actual_source_date"] = "2026-07-08"
            with patch("rotation_radar.daily_risk_features.fetch_price", return_value=([{"date": target_s}], stale)), patch("rotation_radar.daily_risk_features.fetch_chip_family", return_value=([], chip_manifest)), patch("rotation_radar.daily_risk_features.fetch_foreign_ownership", return_value=([], [])), patch("rotation_radar.daily_risk_features.fetch_taifex", return_value=([], source("taifex_foreign_oi", "TAIFEX", target_s))), patch("rotation_radar.daily_risk_features.fetch_global", return_value=([], [])), patch("rotation_radar.daily_risk_features.fetch_corporate_calendar", return_value=([], [])), patch("rotation_radar.daily_risk_features.fetch_tdcc_if_new", return_value=([], source("tdcc_holder_distribution", "TDCC", target_s, "no_rows"))):
                with self.assertRaises(IncompleteSourceError): run_date(target, root, scope, "scheduled_open")

    def _workspace(self):
        class Context:
            def __enter__(self_inner):
                self_inner.tmp = tempfile.TemporaryDirectory(); root = Path(self_inner.tmp.name); scope = root / "scope.csv"
                scope.write_text("ticker,name,market\n2330,台積電,TWSE\n", encoding="utf-8")
                return root, scope
            def __exit__(self_inner, *args): self_inner.tmp.cleanup()
        return Context()


if __name__ == "__main__": unittest.main()
