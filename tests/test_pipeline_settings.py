from __future__ import annotations

import unittest
from pathlib import Path
from types import SimpleNamespace

from rotation_radar.pipeline_settings import PipelineOptions, PipelinePaths


class PipelineSettingsTests(unittest.TestCase):
    def test_pipeline_paths_preserve_existing_default_output_names(self) -> None:
        paths = PipelinePaths.from_args(
            SimpleNamespace(
                data_dir="data",
                market_universe_output="data/market_universe.generated.csv",
                sector_map_output="data/sector_map.generated.csv",
                market_quotes_output="data/market_quotes.generated.csv",
                theme_history_output="data/theme_history.generated.csv",
                hot_sector_symbols_output="data/hot_sector_symbols.generated.csv",
                hot_stock_deep_output="data/hot_stock_deep_metrics.generated.csv",
                price_history_file="data/price_history.csv",
                run_manifest_output="reports/latest_manifest.json",
                raw_output_dir="raw_data",
                processed_output_dir="processed_data",
            )
        )

        self.assertEqual(paths.theme_market_quotes, Path("data/theme_market_quotes.generated.csv"))
        self.assertEqual(paths.tracked_stock_metrics, Path("data/stock_metrics.tracked.refreshed.csv"))
        self.assertEqual(paths.refreshed_sector_metrics, Path("data/sector_metrics.refreshed.csv"))
        self.assertEqual(paths.refreshed_stock_metrics, Path("data/stock_metrics.refreshed.csv"))
        self.assertEqual(paths.run_manifest, Path("reports/latest_manifest.json"))
        self.assertEqual(paths.base_sector_metrics, Path("data/sector_metrics.csv"))
        self.assertEqual(paths.base_stock_metrics, Path("data/stock_metrics.csv"))

    def test_pipeline_options_preserve_existing_cli_values(self) -> None:
        options = PipelineOptions.from_args(
            SimpleNamespace(
                force_sector_scan=True,
                sector_scan_max_age_days=30,
                universe_max_age_days=7,
                recent_depth_days=5,
                recent_price_days=70,
                data_retention_days=90,
                skip_depth_refresh=False,
            )
        )

        self.assertTrue(options.force_sector_scan)
        self.assertEqual(options.sector_scan_max_age_days, 30.0)
        self.assertEqual(options.universe_max_age_days, 7.0)
        self.assertEqual(options.recent_depth_days, 5)
        self.assertEqual(options.recent_price_days, 70)
        self.assertEqual(options.data_retention_days, 90)
        self.assertFalse(options.skip_depth_refresh)


if __name__ == "__main__":
    unittest.main()
