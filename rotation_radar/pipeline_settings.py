from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class PipelineOptions:
    force_sector_scan: bool
    sector_scan_max_age_days: float
    universe_max_age_days: float
    recent_depth_days: int
    recent_price_days: int
    data_retention_days: int
    skip_depth_refresh: bool

    @classmethod
    def from_args(cls, args) -> "PipelineOptions":
        return cls(
            force_sector_scan=bool(args.force_sector_scan),
            sector_scan_max_age_days=float(args.sector_scan_max_age_days),
            universe_max_age_days=float(args.universe_max_age_days),
            recent_depth_days=int(args.recent_depth_days),
            recent_price_days=int(args.recent_price_days),
            data_retention_days=int(args.data_retention_days),
            skip_depth_refresh=bool(args.skip_depth_refresh),
        )


@dataclass(frozen=True)
class PipelinePaths:
    data_dir: Path
    market_universe: Path
    sector_map: Path
    market_quotes: Path
    theme_market_quotes: Path
    tracked_stock_metrics: Path
    refreshed_sector_metrics: Path
    refreshed_stock_metrics: Path
    theme_history: Path
    hot_sector_symbols: Path
    hot_stock_deep_metrics: Path
    price_history: Path
    radar_snapshot_dir: Path
    run_manifest: Path
    raw_root: Path
    processed_root: Path

    @classmethod
    def from_args(cls, args) -> "PipelinePaths":
        data_dir = Path(args.data_dir)
        return cls(
            data_dir=data_dir,
            market_universe=Path(args.market_universe_output),
            sector_map=Path(args.sector_map_output),
            market_quotes=Path(args.market_quotes_output),
            theme_market_quotes=data_dir / "theme_market_quotes.generated.csv",
            tracked_stock_metrics=Path("data/stock_metrics.tracked.refreshed.csv"),
            refreshed_sector_metrics=Path("data/sector_metrics.refreshed.csv"),
            refreshed_stock_metrics=Path("data/stock_metrics.refreshed.csv"),
            theme_history=Path(args.theme_history_output),
            hot_sector_symbols=Path(args.hot_sector_symbols_output),
            hot_stock_deep_metrics=Path(args.hot_stock_deep_output),
            price_history=Path(args.price_history_file),
            radar_snapshot_dir=Path(args.radar_snapshot_output_dir),
            run_manifest=Path(args.run_manifest_output),
            raw_root=Path(args.raw_output_dir),
            processed_root=Path(args.processed_output_dir),
        )

    @property
    def base_sector_metrics(self) -> Path:
        return self.data_dir / "sector_metrics.csv"

    @property
    def base_stock_metrics(self) -> Path:
        return self.data_dir / "stock_metrics.csv"
