from __future__ import annotations

import unittest
from pathlib import Path
from types import SimpleNamespace

from rotation_radar.pipeline_settings import PipelinePaths


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
                raw_output_dir="raw_data",
                processed_output_dir="processed_data",
            )
        )

        self.assertEqual(paths.theme_market_quotes, Path("data/theme_market_quotes.generated.csv"))
        self.assertEqual(paths.tracked_stock_metrics, Path("data/stock_metrics.tracked.refreshed.csv"))
        self.assertEqual(paths.refreshed_sector_metrics, Path("data/sector_metrics.refreshed.csv"))
        self.assertEqual(paths.refreshed_stock_metrics, Path("data/stock_metrics.refreshed.csv"))
        self.assertEqual(paths.base_sector_metrics, Path("data/sector_metrics.csv"))
        self.assertEqual(paths.base_stock_metrics, Path("data/stock_metrics.csv"))


if __name__ == "__main__":
    unittest.main()
