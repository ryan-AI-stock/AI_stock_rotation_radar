from __future__ import annotations

import unittest
from contextlib import ExitStack
from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import Mock, patch

import rotation_radar.daily_pipeline as pipeline
from rotation_radar.data_quality import QuoteSnapshot
from rotation_radar.pipeline_settings import PipelineOptions, PipelinePaths


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

    def test_manual_rerun_falls_back_to_quote_date_and_records_manifest(self) -> None:
        args = _args(report_date="2026-06-04", manual_rerun=True)
        stock = SimpleNamespace(symbol="2330")

        with ExitStack() as stack:
            stack.enter_context(
                patch.object(pipeline, "_ensure_market_universe", return_value=(Path("market.csv"), Path("sector.csv")))
            )
            stack.enter_context(patch.object(pipeline, "_ensure_market_quotes", return_value=Path("quotes.csv")))
            stack.enter_context(
                patch.object(pipeline, "load_quote_snapshot", return_value=QuoteSnapshot("20260605", "14:30:00"))
            )
            stack.enter_context(patch.object(pipeline, "build_theme_market_quotes", return_value=Path("theme_quotes.csv")))
            stack.enter_context(patch.object(pipeline, "refresh_stock_metrics_quotes"))
            stack.enter_context(
                patch.object(pipeline, "build_sector_metrics_from_market_quotes", return_value=Path("sector_metrics.csv"))
            )
            stack.enter_context(patch.object(pipeline, "update_theme_history", return_value=Path("theme_history.csv")))
            stack.enter_context(patch.object(pipeline, "export_hot_sector_symbols", return_value=Path("hot_symbols.csv")))
            stack.enter_context(patch.object(pipeline, "_refresh_recent_depth_snapshots"))
            stack.enter_context(patch.object(pipeline, "build_market_stock_candidates"))
            backfill_valuations = stack.enter_context(
                patch.object(
                    pipeline,
                    "backfill_stock_valuations",
                    return_value=SimpleNamespace(filled_pe_count=1, missing_pe_symbols=(), warnings=[]),
                )
            )
            stack.enter_context(patch.object(pipeline, "build_hot_stock_deep_metrics", return_value=Path("deep.csv")))
            stack.enter_context(patch.object(pipeline, "merge_deep_metrics_into_stock_metrics"))
            stack.enter_context(patch.object(pipeline, "load_sector_metrics", return_value=["sector"]))
            stack.enter_context(patch.object(pipeline, "load_stock_metrics", return_value=[stock]))
            write_formal_candidates = stack.enter_context(
                patch.object(pipeline, "write_formal_radar_candidates", return_value=Path("formal_candidates.csv"))
            )
            refresh_prices = stack.enter_context(patch.object(pipeline, "_refresh_recent_price_snapshots"))
            stack.enter_context(patch.object(pipeline, "backfill_theme_history_from_processed", return_value=Path("theme_history.csv")))
            stack.enter_context(patch.object(pipeline, "build_price_history_from_processed"))
            stack.enter_context(
                patch.object(pipeline, "build_radar_snapshots", return_value=SimpleNamespace(paths=[Path("snapshot.csv")], warnings=[]))
            )
            stack.enter_context(patch.object(pipeline, "load_price_history", return_value={}))
            stack.enter_context(patch.object(pipeline, "load_stock_theme_tags", return_value={}))
            stack.enter_context(patch.object(pipeline, "load_theme_trends", return_value={}))
            write_run_manifest = stack.enter_context(patch.object(pipeline, "write_run_manifest", return_value=Path("manifest.json")))
            stack.enter_context(patch("builtins.print"))
            write_report = Mock()

            pipeline.run_update_latest_report(args, write_report)

            self.assertEqual(backfill_valuations.call_args.kwargs["report_date"], "2026-06-05")
            self.assertEqual(write_formal_candidates.call_args.kwargs["report_date"], "2026-06-05")
            refresh_prices.assert_called_once()
            self.assertEqual(refresh_prices.call_args.args[0].report_date, "2026-06-05")
            self.assertEqual(write_report.call_args.kwargs["generated_date"], "2026-06-05")
            manifest = write_run_manifest.call_args.args[1]
            self.assertEqual(manifest["report_date"], "2026-06-05")
            self.assertEqual(manifest["requested_date"], "2026-06-04")
            self.assertEqual(manifest["actual_report_date"], "2026-06-05")
            self.assertIn("requested report date 2026-06-04 was unavailable", manifest["fallback_reason"])
            self.assertTrue(manifest["manual_rerun"])

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
            backfill_valuations = stack.enter_context(
                patch.object(
                    pipeline,
                    "backfill_stock_valuations",
                    return_value=SimpleNamespace(filled_pe_count=1, missing_pe_symbols=(), warnings=[]),
                )
            )
            stack.enter_context(patch.object(pipeline, "build_hot_stock_deep_metrics", return_value=Path("deep.csv")))
            merge_deep_metrics = stack.enter_context(patch.object(pipeline, "merge_deep_metrics_into_stock_metrics"))
            stack.enter_context(patch.object(pipeline, "load_sector_metrics", return_value=["sector"]))
            stack.enter_context(patch.object(pipeline, "load_stock_metrics", return_value=[stock]))
            write_formal_candidates = stack.enter_context(
                patch.object(pipeline, "write_formal_radar_candidates", return_value=Path("formal_candidates.csv"))
            )
            refresh_prices = stack.enter_context(patch.object(pipeline, "_refresh_recent_price_snapshots"))
            backfill_theme_history = stack.enter_context(
                patch.object(pipeline, "backfill_theme_history_from_processed", return_value=Path("theme_history.csv"))
            )
            build_price_history = stack.enter_context(patch.object(pipeline, "build_price_history_from_processed"))
            build_radar_snapshots = stack.enter_context(
                patch.object(pipeline, "build_radar_snapshots", return_value=SimpleNamespace(paths=[Path("snapshot.csv")], warnings=[]))
            )
            stack.enter_context(patch.object(pipeline, "load_price_history", return_value={}))
            stack.enter_context(patch.object(pipeline, "load_stock_theme_tags", return_value={}))
            stack.enter_context(patch.object(pipeline, "load_theme_trends", return_value={}))
            write_run_manifest = stack.enter_context(patch.object(pipeline, "write_run_manifest", return_value=Path("manifest.json")))
            stack.enter_context(patch("builtins.print"))
            write_report = Mock()

            pipeline.run_update_latest_report(args, write_report)

            refresh_stock_metrics_quotes.assert_called_once()
            refresh_depth.assert_not_called()
            build_candidates.assert_called_once()
            backfill_valuations.assert_called_once()
            self.assertEqual(backfill_valuations.call_args.kwargs["stock_metrics_path"], Path("data/stock_metrics.refreshed.csv"))
            self.assertEqual(backfill_valuations.call_args.kwargs["market_quotes_path"], Path("theme_quotes.csv"))
            self.assertEqual(backfill_valuations.call_args.kwargs["report_date"], "2026-06-04")
            merge_deep_metrics.assert_called_once()
            write_formal_candidates.assert_called_once()
            self.assertEqual(write_formal_candidates.call_args.kwargs["stocks"], [stock])
            self.assertEqual(write_formal_candidates.call_args.kwargs["report_date"], "2026-06-04")
            refresh_prices.assert_called_once()
            self.assertEqual(refresh_prices.call_args.kwargs["required_symbols"], {"2330"})
            self.assertEqual(backfill_theme_history.call_args.kwargs["keep_days"], 20)
            build_price_history.assert_called_once()
            build_radar_snapshots.assert_called_once()
            self.assertEqual(build_radar_snapshots.call_args.kwargs["stock_metrics_path"], Path("data/stock_metrics.refreshed.csv"))
            self.assertEqual(build_radar_snapshots.call_args.kwargs["days"], 20)
            write_report.assert_called_once()
            self.assertEqual(write_report.call_args.kwargs["quote_date"], "20260604")
            self.assertEqual(write_report.call_args.kwargs["quote_time"], "14:30:00")
            write_run_manifest.assert_called_once()
            manifest = write_run_manifest.call_args.args[1]
            self.assertEqual(manifest["report_date"], "2026-06-04")
            self.assertEqual(manifest["quote_date"], "2026-06-04")
            self.assertEqual(manifest["outputs"]["formal_candidates"], "formal_candidates.csv")
            self.assertEqual(manifest["refresh_status"]["depth"], "skipped")
            self.assertEqual(manifest["refresh_status"]["price"], "attempted")
            self.assertEqual(manifest["refresh_status"]["candidate_symbol_count"], 1)

    def test_collect_data_quality_warnings_reports_missing_snapshots(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            args = _args(
                processed_output_dir=str(root / "processed"),
                raw_output_dir=str(root / "raw"),
                report_date="2026-06-04",
                recent_depth_days=1,
                recent_price_days=1,
                skip_depth_refresh=False,
            )
            paths = PipelinePaths.from_args(args)
            options = PipelineOptions.from_args(args)

            warnings = pipeline._collect_data_quality_warnings(args, paths, options, {"2330"})

        self.assertTrue(any("missing depth snapshot files" in warning for warning in warnings))
        self.assertTrue(any("missing price snapshot files" in warning for warning in warnings))

    def test_latest_complete_price_snapshot_date_uses_newest_complete_folder(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            incomplete = root / "20260605"
            older = root / "20260604"
            newer = root / "20260606"
            for folder in (incomplete, older, newer):
                folder.mkdir()
            (incomplete / "twse_prices.csv").write_text("", encoding="utf-8")
            (older / "twse_prices.csv").write_text("", encoding="utf-8")
            (older / "tpex_prices.csv").write_text("", encoding="utf-8")
            (newer / "twse_prices.csv").write_text("", encoding="utf-8")
            (newer / "tpex_prices.csv").write_text("", encoding="utf-8")

            self.assertEqual(pipeline._latest_complete_price_snapshot_date(root), date(2026, 6, 6))


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
        "radar_snapshot_days": 20,
        "radar_snapshot_output_dir": "data/history",
        "raw_output_dir": "raw_data",
        "recent_depth_days": 5,
        "recent_price_days": 70,
        "report_date": "2026-06-04",
        "manual_rerun": False,
        "require_exact_report_date": False,
        "run_manifest_output": "reports/latest_manifest.json",
        "sector_map_output": "data/sector_map.generated.csv",
        "sector_scan_max_age_days": 0.0,
        "skip_depth_refresh": False,
        "theme_history_output": "data/theme_history.generated.csv",
        "theme_map_file": "data/theme_map.csv",
        "theme_universe_file": "data/theme_universe.csv",
        "universe_max_age_days": 30.0,
        "data_retention_days": 90,
        "output": "reports/latest.html",
    }
    values.update(overrides)
    return SimpleNamespace(**values)


if __name__ == "__main__":
    unittest.main()
