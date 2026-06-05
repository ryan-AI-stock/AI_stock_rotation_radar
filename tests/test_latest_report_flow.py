from __future__ import annotations

import unittest
from contextlib import ExitStack
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import rotation_radar.daily_pipeline as pipeline
from rotation_radar.data_quality import QuoteSnapshot


class LatestReportFlowTests(unittest.TestCase):
    def test_update_latest_report_stops_when_quote_date_does_not_match_target(self) -> None:
        args = _args(report_date="2026-06-04")

        with (
            patch.object(pipeline, "_ensure_market_universe", return_value=(Path("market.csv"), Path("sector.csv"))),
            patch.object(pipeline, "_ensure_market_quotes", return_value=Path("quotes.csv")),
            patch.object(pipeline, "load_quote_snapshot", return_value=QuoteSnapshot("20260605", "14:30:00")),
            patch.object(pipeline, "build_theme_market_quotes") as build_theme_market_quotes,
            patch("builtins.print"),
        ):
            with self.assertRaisesRegex(SystemExit, "does not match target report date 2026-06-04"):
                pipeline.run_update_latest_report(args, write_report=lambda *args, **kwargs: None)

        build_theme_market_quotes.assert_not_called()

    def test_update_latest_report_runs_expected_internal_flow_without_depth_refresh(self) -> None:
        args = _args(skip_depth_refresh=True)
        stock = SimpleNamespace(symbol="2330")

        with ExitStack() as stack:
            stack.enter_context(
                patch.object(pipeline, "_ensure_market_universe", return_value=(Path("market.csv"), Path("sector.csv")))
            )
            stack.enter_context(patch.object(pipeline, "_ensure_market_quotes", return_value=Path("quotes.csv")))
            stack.enter_context(
                patch.object(pipeline, "load_quote_snapshot", return_value=QuoteSnapshot("20260604", "14:30:00"))
            )
            stack.enter_context(patch.object(pipeline, "build_theme_market_quotes", return_value=Path("theme_quotes.csv")))
            refresh_stock_metrics_quotes = stack.enter_context(patch.object(pipeline, "refresh_stock_metrics_quotes"))
            stack.enter_context(
                patch.object(pipeline, "build_sector_metrics_from_market_quotes", return_value=Path("sector_metrics.csv"))
            )
            stack.enter_context(patch.object(pipeline, "update_theme_history", return_value=Path("theme_history.csv")))
            stack.enter_context(patch.object(pipeline, "export_hot_sector_symbols", return_value=Path("hot_symbols.csv")))
            refresh_depth = stack.enter_context(patch.object(pipeline, "_refresh_recent_depth_snapshots"))
            build_candidates = stack.enter_context(patch.object(pipeline, "build_market_stock_candidates"))
            stack.enter_context(patch.object(pipeline, "build_hot_stock_deep_metrics", return_value=Path("deep.csv")))
            merge_deep_metrics = stack.enter_context(patch.object(pipeline, "merge_deep_metrics_into_stock_metrics"))
            stack.enter_context(patch.object(pipeline, "load_sector_metrics", return_value=["sector"]))
            stack.enter_context(patch.object(pipeline, "load_stock_metrics", return_value=[stock]))
            refresh_prices = stack.enter_context(patch.object(pipeline, "_refresh_recent_price_snapshots"))
            stack.enter_context(
                patch.object(pipeline, "backfill_theme_history_from_processed", return_value=Path("theme_history.csv"))
            )
            build_price_history = stack.enter_context(patch.object(pipeline, "build_price_history_from_processed"))
            stack.enter_context(patch.object(pipeline, "load_price_history", return_value={}))
            stack.enter_context(patch.object(pipeline, "load_stock_theme_tags", return_value={}))
            stack.enter_context(patch.object(pipeline, "load_theme_trends", return_value={}))
            stack.enter_context(patch("builtins.print"))
            write_report = Mock()

            pipeline.run_update_latest_report(args, write_report)

            refresh_stock_metrics_quotes.assert_called_once()
            refresh_depth.assert_not_called()
            build_candidates.assert_called_once()
            merge_deep_metrics.assert_called_once()
            refresh_prices.assert_called_once_with(args, required_symbols={"2330"})
            build_price_history.assert_called_once()
            write_report.assert_called_once()
            self.assertEqual(write_report.call_args.kwargs["quote_date"], "20260604")
            self.assertEqual(write_report.call_args.kwargs["quote_time"], "14:30:00")


def _args(**overrides):
    values = {
        "data_dir": "data",
        "force_sector_scan": False,
        "hot_sector_symbols_output": "data/hot_sector_symbols.generated.csv",
        "hot_stock_deep_output": "data/hot_stock_deep_metrics.generated.csv",
        "market_quotes_output": "data/market_quotes.generated.csv",
        "market_universe_output": "data/market_universe.generated.csv",
        "price_history_file": "data/price_history.csv",
        "processed_output_dir": "processed_data",
        "report_date": "2026-06-04",
        "sector_map_output": "data/sector_map.generated.csv",
        "sector_scan_max_age_days": 0.0,
        "skip_depth_refresh": False,
        "theme_history_output": "data/theme_history.generated.csv",
        "theme_map_file": "data/theme_map.csv",
        "theme_universe_file": "data/theme_universe.csv",
        "universe_max_age_days": 30.0,
        "output": "reports/latest.html",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


if __name__ == "__main__":
    unittest.main()
