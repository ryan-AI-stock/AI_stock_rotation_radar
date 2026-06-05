from __future__ import annotations

import csv
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from .cache_policy import is_fresh
from .data_quality import load_quote_snapshot, quote_date_mismatch_message
from .data_loader import load_sector_metrics, load_stock_metrics
from .deep_metrics import build_hot_stock_deep_metrics, merge_deep_metrics_into_stock_metrics
from .market_universe import MarketUniverseFetchError, build_fallback_universe_from_theme_map, build_market_universe
from .normalize import normalize_raw_directory
from .pipeline_settings import PipelineOptions, PipelinePaths
from .price_history import build_price_history_from_processed, load_price_history
from .public_sources import fetch_raw_market_snapshots, fetch_raw_price_snapshots, parse_trade_date, recent_weekdays
from .quote_refresh import refresh_market_quotes, refresh_stock_metrics_quotes
from .sector_metrics_builder import build_sector_metrics_from_market_quotes
from .stock_screener import build_market_stock_candidates, export_hot_sector_symbols
from .theme_history import backfill_theme_history_from_processed, load_theme_trends, update_theme_history
from .theme_metrics import build_theme_market_quotes, load_stock_theme_tags


ReportWriter = Callable[..., None]


def run_update_latest_report(args, write_report: ReportWriter) -> None:
    paths = PipelinePaths.from_args(args)
    options = PipelineOptions.from_args(args)
    market_path, sector_path = _ensure_market_universe(args, paths, options)
    print(f"Saved {market_path}")
    print(f"Saved {sector_path}")

    refreshed_path = paths.refreshed_stock_metrics
    market_quotes_path = _ensure_market_quotes(paths, options)
    quote_snapshot = load_quote_snapshot(market_quotes_path)
    if args.report_date and quote_snapshot.normalized_date != args.report_date:
        raise SystemExit(quote_date_mismatch_message(quote_snapshot, args.report_date))
    quote_date, quote_time = quote_snapshot.quote_date, quote_snapshot.quote_time
    print(f"Saved {market_quotes_path}")

    theme_quotes_path = build_theme_market_quotes(
        market_quotes_path=market_quotes_path,
        theme_map_path=args.theme_map_file,
        output_path=paths.theme_market_quotes,
        fallback_stock_metrics_path=paths.base_stock_metrics,
        theme_universe_path=args.theme_universe_file,
    )
    print(f"Saved {theme_quotes_path}")

    tracked_refreshed_path = paths.tracked_stock_metrics
    refresh_stock_metrics_quotes(
        stock_metrics_path=paths.base_stock_metrics,
        sector_map_path=sector_path,
        output_path=tracked_refreshed_path,
    )
    generated_sector_path = build_sector_metrics_from_market_quotes(
        market_quotes_path=theme_quotes_path,
        base_sector_metrics_path=paths.base_sector_metrics,
        output_path=paths.refreshed_sector_metrics,
    )
    print(f"Saved {generated_sector_path}")

    theme_history_path = update_theme_history(
        sector_metrics_path=generated_sector_path,
        theme_quotes_path=theme_quotes_path,
        output_path=paths.theme_history,
    )
    print(f"Saved {theme_history_path}")

    hot_symbols_path = export_hot_sector_symbols(
        market_quotes_path=theme_quotes_path,
        sector_metrics_path=generated_sector_path,
        output_path=paths.hot_sector_symbols,
    )
    print(f"Saved {hot_symbols_path}")

    if not options.skip_depth_refresh:
        _refresh_recent_depth_snapshots(args, paths, options)
    build_market_stock_candidates(
        market_quotes_path=theme_quotes_path,
        base_stock_metrics_path=tracked_refreshed_path,
        sector_metrics_path=generated_sector_path,
        output_path=refreshed_path,
    )
    deep_path = build_hot_stock_deep_metrics(
        hot_symbols_path=hot_symbols_path,
        processed_root=paths.processed_root,
        output_path=paths.hot_stock_deep_metrics,
    )
    print(f"Saved {deep_path}")

    merge_deep_metrics_into_stock_metrics(
        stock_metrics_path=refreshed_path,
        deep_metrics_path=deep_path,
        output_path=refreshed_path,
    )
    sectors = load_sector_metrics(generated_sector_path)
    stocks = load_stock_metrics(refreshed_path)
    candidate_symbols = {stock.symbol for stock in stocks}
    _refresh_recent_price_snapshots(args, paths, options, required_symbols=candidate_symbols)
    theme_history_path = backfill_theme_history_from_processed(
        processed_root=paths.processed_root,
        theme_map_path=args.theme_map_file,
        theme_universe_path=args.theme_universe_file,
        base_sector_metrics_path=paths.base_sector_metrics,
        output_path=paths.theme_history,
    )
    print(f"Backfilled {theme_history_path}")

    build_price_history_from_processed(
        processed_root=paths.processed_root,
        output_path=paths.price_history,
        symbols={stock.symbol for stock in stocks},
        market_quotes_path=market_quotes_path,
    )
    price_history = load_price_history(paths.price_history)
    stock_themes = load_stock_theme_tags(args.theme_map_file, args.theme_universe_file)
    theme_trends = load_theme_trends(theme_history_path, generated_sector_path)
    write_report(
        sectors,
        stocks,
        args.output,
        "latest report with refreshed quotes",
        price_history,
        stock_themes=stock_themes,
        theme_trends=theme_trends,
        quote_date=quote_date,
        quote_time=quote_time,
        generated_date=args.report_date,
    )


def _ensure_market_universe(args, paths: PipelinePaths, options: PipelineOptions) -> tuple[Path, Path]:
    market_path = paths.market_universe
    sector_path = paths.sector_map
    if (
        not options.force_sector_scan
        and is_fresh(market_path, options.universe_max_age_days)
        and is_fresh(sector_path, options.universe_max_age_days)
    ):
        return market_path, sector_path
    try:
        return build_market_universe(
            rules_path=args.industry_rules_file,
            output_path=paths.market_universe,
            sector_map_output_path=paths.sector_map,
        )
    except (OSError, MarketUniverseFetchError) as exc:
        print(f"Warning: failed to refresh exchange universe: {exc}")
        return build_fallback_universe_from_theme_map(
            theme_map_path=args.theme_map_file,
            output_path=paths.market_universe,
            sector_map_output_path=paths.sector_map,
        )


def _ensure_market_quotes(paths: PipelinePaths, options: PipelineOptions) -> Path:
    market_quotes_path = paths.market_quotes
    if (
        options.sector_scan_max_age_days > 0
        and not options.force_sector_scan
        and is_fresh(market_quotes_path, options.sector_scan_max_age_days)
    ):
        return market_quotes_path
    return refresh_market_quotes(
        sector_map_path=paths.sector_map,
        output_path=paths.market_quotes,
    )


def _refresh_recent_depth_snapshots(args, paths: PipelinePaths, options: PipelineOptions) -> None:
    today = _target_report_date(args)
    for trade_date in recent_weekdays(today, options.recent_depth_days):
        ymd = trade_date.strftime("%Y%m%d")
        processed_dir = paths.processed_root / ymd
        if _has_depth_files(processed_dir):
            print(f"Using existing depth snapshots in {processed_dir}")
            continue

        saved_raw, errors = fetch_raw_market_snapshots(trade_date, paths.raw_root)
        for path in saved_raw:
            print(f"Saved {path}")
        for error in errors:
            print(f"Warning: {error}")

        raw_dir = paths.raw_root / ymd
        if raw_dir.exists():
            for path in normalize_raw_directory(raw_dir, processed_dir):
                print(f"Saved {path}")

    _prune_date_folders(paths.raw_root, options.data_retention_days)
    _prune_date_folders(paths.processed_root, options.data_retention_days)


def _refresh_recent_price_snapshots(
    args,
    paths: PipelinePaths,
    options: PipelineOptions,
    required_symbols: set[str] | None = None,
) -> None:
    today = _target_report_date(args)
    for index, trade_date in enumerate(recent_weekdays(today, options.recent_price_days)):
        ymd = trade_date.strftime("%Y%m%d")
        processed_dir = paths.processed_root / ymd
        symbols_to_check = required_symbols if index < 7 else None
        force_refresh = processed_dir.exists() and not _has_price_files(processed_dir, symbols_to_check)
        if _has_price_files(processed_dir, symbols_to_check):
            print(f"Using existing price snapshots in {processed_dir}")
            continue
        if force_refresh:
            print(f"Refreshing incomplete price snapshots in {processed_dir}")

        saved_raw, errors = fetch_raw_price_snapshots(trade_date, paths.raw_root, force=force_refresh)
        for path in saved_raw:
            print(f"Saved {path}")
        for error in errors:
            print(f"Warning: {error}")

        raw_dir = paths.raw_root / ymd
        if raw_dir.exists():
            for path in normalize_raw_directory(raw_dir, processed_dir):
                print(f"Saved {path}")

    _prune_date_folders(paths.raw_root, options.data_retention_days)
    _prune_date_folders(paths.processed_root, options.data_retention_days)


def _target_report_date(args):
    if args.report_date:
        return parse_trade_date(args.report_date)
    return datetime.now(ZoneInfo("Asia/Taipei")).date()


def _has_depth_files(path: Path) -> bool:
    return path.exists() and any(path.glob("*institutional*.csv")) and any(path.glob("*margin*.csv"))


def _has_price_files(path: Path, required_symbols: set[str] | None = None) -> bool:
    has_files = path.exists() and any(path.glob("twse_prices*.csv")) and any(path.glob("tpex_prices*.csv"))
    if not has_files:
        return False
    if not required_symbols:
        return True
    found_symbols: set[str] = set()
    for csv_path in path.glob("*prices*.csv"):
        with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
            for row in csv.DictReader(handle):
                symbol = (row.get("證券代號") or row.get("代號") or "").strip()
                if symbol in required_symbols:
                    found_symbols.add(symbol)
    missing = sorted(required_symbols - found_symbols)
    if missing:
        preview = ", ".join(missing[:8])
        suffix = "..." if len(missing) > 8 else ""
        print(f"Warning: price snapshots in {path} miss {len(missing)} report symbols: {preview}{suffix}")
        return False
    return True


def _prune_date_folders(root: str | Path, keep_days: int) -> None:
    root_path = Path(root)
    if keep_days <= 0 or not root_path.exists():
        return
    folders = sorted((path for path in root_path.iterdir() if path.is_dir() and path.name.isdigit()), reverse=True)
    for folder in folders[keep_days:]:
        for child in sorted(folder.rglob("*"), reverse=True):
            if child.is_file():
                child.unlink()
            elif child.is_dir():
                child.rmdir()
        folder.rmdir()
        print(f"Pruned {folder}")
