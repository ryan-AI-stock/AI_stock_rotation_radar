from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from .cache_policy import is_fresh
from .data_loader import load_dataset, load_sector_metrics, load_stock_metrics
from .deep_metrics import build_hot_stock_deep_metrics, merge_deep_metrics_into_stock_metrics
from .demo_data import demo_sectors, demo_stocks
from .market_universe import build_market_universe
from .metrics_builder import update_sector_metrics_from_stocks, update_stock_metrics_from_processed
from .models import Report
from .normalize import normalize_raw_directory
from .price_history import build_price_history_from_processed, load_price_history
from .public_sources import fetch_raw_market_snapshots, fetch_raw_price_snapshots, parse_trade_date, recent_weekdays
from .quote_refresh import refresh_market_quotes, refresh_stock_metrics_quotes
from .report import render_report
from .scoring import build_results
from .sector_metrics_builder import build_sector_metrics_from_market_quotes
from .stock_screener import build_market_stock_candidates, export_hot_sector_symbols
from .theme_metrics import build_theme_market_quotes


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate Taiwan market-theme rotation HTML report.")
    parser.add_argument("--demo", action="store_true", help="Use bundled demo data.")
    parser.add_argument("--data-dir", default="data", help="Directory containing sector_metrics.csv and stock_metrics.csv.")
    parser.add_argument("--sector-metrics-file", help="Theme metrics CSV for report generation.")
    parser.add_argument("--stock-metrics-file", help="Stock metrics CSV for report generation.")
    parser.add_argument("--price-history-file", default="data/price_history.csv", help="Optional OHLC and MA CSV for charts.")
    parser.add_argument("--refresh-quotes", action="store_true", help="Refresh latest prices before generating a report.")
    parser.add_argument("--update-latest-report", action="store_true", help="Build universe, refresh quotes, and write latest report.")
    parser.add_argument("--sector-map-file", default="data/sector_map.csv", help="Sector map CSV with optional market column.")
    parser.add_argument("--theme-map-file", default="data/theme_map.csv", help="Market theme to stock mapping CSV.")
    parser.add_argument("--theme-universe-file", default="data/theme_universe.csv", help="Market theme universe CSV.")
    parser.add_argument("--build-market-universe", action="store_true", help="Fetch listed/OTC company universe and build sector map.")
    parser.add_argument("--industry-rules-file", default="data/industry_sector_rules.csv", help="Industry code to sector mapping.")
    parser.add_argument("--market-universe-output", default="data/market_universe.generated.csv", help="Generated market universe CSV.")
    parser.add_argument("--sector-map-output", default="data/sector_map.generated.csv", help="Generated full-market sector map CSV.")
    parser.add_argument("--market-quotes-output", default="data/market_quotes.generated.csv", help="Generated full-market quote CSV.")
    parser.add_argument("--hot-sector-symbols-output", default="data/hot_sector_symbols.generated.csv", help="Symbols selected for deeper hot-theme analysis.")
    parser.add_argument("--hot-stock-deep-output", default="data/hot_stock_deep_metrics.generated.csv", help="Deep metrics for hot-sector symbols.")
    parser.add_argument("--sector-scan-max-age-days", type=float, default=3.0, help="Reuse full-market theme scan cache within this many days.")
    parser.add_argument("--universe-max-age-days", type=float, default=30.0, help="Reuse listed/OTC universe cache within this many days.")
    parser.add_argument("--force-sector-scan", action="store_true", help="Force refresh full-market quotes and theme ranking.")
    parser.add_argument("--fetch-raw", help="Fetch raw TWSE/TPEx JSON snapshots for a trade date, YYYY-MM-DD.")
    parser.add_argument("--daily-update", help="Run fetch, normalize, metric build, and report generation for YYYY-MM-DD.")
    parser.add_argument("--fetch-recent-depth", help="Fetch and normalize recent weekday snapshots ending at YYYY-MM-DD.")
    parser.add_argument("--recent-depth-days", type=int, default=5, help="Number of recent weekdays to fetch for depth metrics.")
    parser.add_argument("--fetch-recent-prices", help="Fetch and normalize recent weekday price snapshots ending at YYYY-MM-DD.")
    parser.add_argument("--recent-price-days", type=int, default=25, help="Number of recent weekdays to fetch for OHLC charts.")
    parser.add_argument(
        "--skip-depth-refresh",
        action="store_true",
        help="Skip fetching the latest institutional and margin depth snapshot before --update-latest-report.",
    )
    parser.add_argument("--raw-output-dir", default="raw_data", help="Directory for raw public market data snapshots.")
    parser.add_argument("--normalize-raw", help="Normalize raw JSON snapshots for a trade date, YYYY-MM-DD.")
    parser.add_argument("--raw-input-dir", default="raw_data", help="Directory containing raw public market data snapshots.")
    parser.add_argument("--processed-output-dir", default="processed_data", help="Directory for normalized CSV snapshots.")
    parser.add_argument("--build-stock-metrics", action="store_true", help="Update stock_metrics.csv from processed data.")
    parser.add_argument("--build-sector-metrics", action="store_true", help="Update sector_metrics.csv from stock metrics.")
    parser.add_argument("--stock-metrics-input", default="data/stock_metrics.csv", help="Base stock metrics CSV.")
    parser.add_argument("--stock-metrics-output", default="data/stock_metrics.csv", help="Updated stock metrics CSV.")
    parser.add_argument("--sector-metrics-input", default="data/sector_metrics.csv", help="Base sector metrics CSV.")
    parser.add_argument("--sector-metrics-output", default="data/sector_metrics.csv", help="Updated sector metrics CSV.")
    parser.add_argument("--processed-input-dir", default="processed_data", help="Directory containing normalized CSV snapshots.")
    parser.add_argument("--output", default="reports/latest.html", help="Output HTML path.")
    args = parser.parse_args()

    if args.update_latest_report:
        market_path, sector_path = _ensure_market_universe(args)
        print(f"Saved {market_path}")
        print(f"Saved {sector_path}")

        refreshed_path = Path("data/stock_metrics.refreshed.csv")
        market_quotes_path = _ensure_market_quotes(args, sector_path)
        print(f"Saved {market_quotes_path}")
        theme_quotes_path = build_theme_market_quotes(
            market_quotes_path=market_quotes_path,
            theme_map_path=args.theme_map_file,
            output_path=Path(args.data_dir) / "theme_market_quotes.generated.csv",
            fallback_stock_metrics_path=Path(args.data_dir) / "stock_metrics.csv",
            theme_universe_path=args.theme_universe_file,
        )
        print(f"Saved {theme_quotes_path}")
        tracked_refreshed_path = Path("data/stock_metrics.tracked.refreshed.csv")
        refresh_stock_metrics_quotes(
            stock_metrics_path=Path(args.data_dir) / "stock_metrics.csv",
            sector_map_path=sector_path,
            output_path=tracked_refreshed_path,
        )
        generated_sector_path = build_sector_metrics_from_market_quotes(
            market_quotes_path=theme_quotes_path,
            base_sector_metrics_path=Path(args.data_dir) / "sector_metrics.csv",
            output_path=Path("data/sector_metrics.refreshed.csv"),
        )
        print(f"Saved {generated_sector_path}")
        hot_symbols_path = export_hot_sector_symbols(
            market_quotes_path=theme_quotes_path,
            sector_metrics_path=generated_sector_path,
            output_path=args.hot_sector_symbols_output,
        )
        print(f"Saved {hot_symbols_path}")
        if not args.skip_depth_refresh:
            _refresh_latest_depth_snapshot(args)
        build_market_stock_candidates(
            market_quotes_path=theme_quotes_path,
            base_stock_metrics_path=tracked_refreshed_path,
            sector_metrics_path=generated_sector_path,
            output_path=refreshed_path,
        )
        deep_path = build_hot_stock_deep_metrics(
            hot_symbols_path=hot_symbols_path,
            processed_root=args.processed_output_dir,
            output_path=args.hot_stock_deep_output,
        )
        print(f"Saved {deep_path}")
        merge_deep_metrics_into_stock_metrics(
            stock_metrics_path=refreshed_path,
            deep_metrics_path=deep_path,
            output_path=refreshed_path,
        )
        sectors = load_sector_metrics(generated_sector_path)
        stocks = load_stock_metrics(refreshed_path)
        build_price_history_from_processed(
            processed_root=args.processed_output_dir,
            output_path=args.price_history_file,
            symbols={stock.symbol for stock in stocks},
            market_quotes_path=market_quotes_path,
        )
        price_history = load_price_history(args.price_history_file)
        _write_report(sectors, stocks, args.output, "latest report with refreshed quotes", price_history)
        return

    if args.build_market_universe:
        market_path, sector_path = build_market_universe(
            rules_path=args.industry_rules_file,
            output_path=args.market_universe_output,
            sector_map_output_path=args.sector_map_output,
        )
        print(f"Saved {market_path}")
        print(f"Saved {sector_path}")
        return

    if args.fetch_recent_prices:
        try:
            end_date = parse_trade_date(args.fetch_recent_prices)
        except ValueError as exc:
            parser.error(str(exc))
        for trade_date in recent_weekdays(end_date, args.recent_price_days):
            ymd = trade_date.strftime("%Y%m%d")
            saved_raw, errors = fetch_raw_price_snapshots(trade_date, args.raw_output_dir)
            for path in saved_raw:
                print(f"Saved {path}")
            for error in errors:
                print(f"Warning: {error}")
            raw_dir = Path(args.raw_output_dir) / ymd
            processed_dir = Path(args.processed_output_dir) / ymd
            if raw_dir.exists():
                for path in normalize_raw_directory(raw_dir, processed_dir):
                    print(f"Saved {path}")
        return

    if args.fetch_recent_depth:
        try:
            end_date = parse_trade_date(args.fetch_recent_depth)
        except ValueError as exc:
            parser.error(str(exc))
        for trade_date in recent_weekdays(end_date, args.recent_depth_days):
            ymd = trade_date.strftime("%Y%m%d")
            saved_raw, errors = fetch_raw_market_snapshots(trade_date, args.raw_output_dir)
            for path in saved_raw:
                print(f"Saved {path}")
            for error in errors:
                print(f"Warning: {error}")
            raw_dir = Path(args.raw_output_dir) / ymd
            processed_dir = Path(args.processed_output_dir) / ymd
            if raw_dir.exists():
                saved_processed = normalize_raw_directory(raw_dir, processed_dir)
                for path in saved_processed:
                    print(f"Saved {path}")
        return

    if args.daily_update:
        try:
            trade_date = parse_trade_date(args.daily_update)
        except ValueError as exc:
            parser.error(str(exc))
        ymd = trade_date.strftime("%Y%m%d")

        saved_raw, errors = fetch_raw_market_snapshots(trade_date, args.raw_output_dir)
        for path in saved_raw:
            print(f"Saved {path}")
        for error in errors:
            print(f"Warning: {error}")

        raw_dir = Path(args.raw_output_dir) / ymd
        if not saved_raw and not raw_dir.exists():
            raise SystemExit(1)
        if not saved_raw and raw_dir.exists():
            print(f"Using existing raw snapshots in {raw_dir}")

        processed_dir = Path(args.processed_output_dir) / ymd
        saved_processed = normalize_raw_directory(raw_dir, processed_dir)
        for path in saved_processed:
            print(f"Saved {path}")

        generated_stock_metrics = Path("data/stock_metrics.generated.csv")
        generated_sector_metrics = Path("data/sector_metrics.generated.csv")
        update_stock_metrics_from_processed(
            stock_metrics_path=args.stock_metrics_input,
            processed_root=args.processed_output_dir,
            output_path=generated_stock_metrics,
        )
        refresh_stock_metrics_quotes(
            stock_metrics_path=generated_stock_metrics,
            sector_map_path=args.sector_map_file,
            output_path=generated_stock_metrics,
        )
        update_sector_metrics_from_stocks(
            sector_metrics_path=args.sector_metrics_input,
            stock_metrics_path=generated_stock_metrics,
            output_path=generated_sector_metrics,
        )

        sectors = load_sector_metrics(generated_sector_metrics)
        stocks = load_stock_metrics(generated_stock_metrics)
        price_history = load_price_history(args.price_history_file)
        _write_report(sectors, stocks, args.output, f"daily update: {args.daily_update}", price_history)
        return

    if args.fetch_raw:
        try:
            trade_date = parse_trade_date(args.fetch_raw)
        except ValueError as exc:
            parser.error(str(exc))
        saved, errors = fetch_raw_market_snapshots(trade_date, args.raw_output_dir)
        for path in saved:
            print(f"Saved {path}")
        for error in errors:
            print(f"Warning: {error}")
        if not saved:
            raise SystemExit(1)
        return

    if args.normalize_raw:
        try:
            trade_date = parse_trade_date(args.normalize_raw)
        except ValueError as exc:
            parser.error(str(exc))
        ymd = trade_date.strftime("%Y%m%d")
        raw_dir = Path(args.raw_input_dir) / ymd
        output_dir = Path(args.processed_output_dir) / ymd
        saved = normalize_raw_directory(raw_dir, output_dir)
        for path in saved:
            print(f"Saved {path}")
        if not saved:
            print(f"No non-empty tables found in {raw_dir}")
        return

    if args.build_stock_metrics:
        path = update_stock_metrics_from_processed(
            stock_metrics_path=args.stock_metrics_input,
            processed_root=args.processed_input_dir,
            output_path=args.stock_metrics_output,
        )
        print(f"Updated {path}")
        return

    if args.build_sector_metrics:
        path = update_sector_metrics_from_stocks(
            sector_metrics_path=args.sector_metrics_input,
            stock_metrics_path=args.stock_metrics_input,
            output_path=args.sector_metrics_output,
        )
        print(f"Updated {path}")
        return

    if args.demo:
        sectors, stocks = demo_sectors(), demo_stocks()
        data_source = "demo data"
    elif args.sector_metrics_file or args.stock_metrics_file:
        if not args.sector_metrics_file or not args.stock_metrics_file:
            parser.error("--sector-metrics-file and --stock-metrics-file must be used together.")
        sectors = load_sector_metrics(args.sector_metrics_file)
        stocks = load_stock_metrics(args.stock_metrics_file)
        data_source = f"CSV files: {args.sector_metrics_file}, {args.stock_metrics_file}"
    else:
        if args.refresh_quotes:
            refreshed_path = Path("data/stock_metrics.refreshed.csv")
            refresh_stock_metrics_quotes(
                stock_metrics_path=Path(args.data_dir) / "stock_metrics.csv",
                sector_map_path=args.sector_map_file,
                output_path=refreshed_path,
            )
            generated_sector_path = Path("data/sector_metrics.refreshed.csv")
            update_sector_metrics_from_stocks(
                sector_metrics_path=Path(args.data_dir) / "sector_metrics.csv",
                stock_metrics_path=refreshed_path,
                output_path=generated_sector_path,
            )
            sectors = load_sector_metrics(generated_sector_path)
            stocks = load_stock_metrics(refreshed_path)
            data_source = "CSV data with refreshed quotes"
        else:
            sectors, stocks = load_dataset(args.data_dir)
            data_source = f"CSV data: {args.data_dir}"

    price_history = load_price_history(args.price_history_file)
    _write_report(sectors, stocks, args.output, data_source, price_history)


def _write_report(sectors, stocks, output_path: str, data_source: str, price_history=None, sector_themes=None) -> None:
    sector_results, stock_results = build_results(sectors, stocks)

    report = Report(
        title="台股題材輪動與波段選股雷達",
        generated_at=datetime.now(ZoneInfo("Asia/Taipei")).strftime("%Y-%m-%d %H:%M"),
        market_view=(
            "模型先抓全市場報價，再把已標記股票映射到記憶體、PCB/載板、CPO/矽光子、被動元件等市場題材，"
            "以題材資金占比與成交活性排序前三名，並在同一題材池內篩選短線波段個股。"
        ),
        sector_results=sector_results,
        stock_results=stock_results,
        price_history=price_history or {},
        sector_themes=sector_themes or {},
    )

    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(render_report(report), encoding="utf-8")
    print(f"Report written to {output} ({data_source})")


def _ensure_market_universe(args) -> tuple[Path, Path]:
    market_path = Path(args.market_universe_output)
    sector_path = Path(args.sector_map_output)
    if (
        not args.force_sector_scan
        and is_fresh(market_path, args.universe_max_age_days)
        and is_fresh(sector_path, args.universe_max_age_days)
    ):
        return market_path, sector_path
    return build_market_universe(
        rules_path=args.industry_rules_file,
        output_path=args.market_universe_output,
        sector_map_output_path=args.sector_map_output,
    )


def _ensure_market_quotes(args, sector_path: Path) -> Path:
    market_quotes_path = Path(args.market_quotes_output)
    if not args.force_sector_scan and is_fresh(market_quotes_path, args.sector_scan_max_age_days):
        return market_quotes_path
    return refresh_market_quotes(
        sector_map_path=sector_path,
        output_path=args.market_quotes_output,
    )


def _ensure_sector_metrics(args, market_quotes_path: Path) -> Path:
    generated_sector_path = Path("data/sector_metrics.refreshed.csv")
    if (
        not args.force_sector_scan
        and is_fresh(generated_sector_path, args.sector_scan_max_age_days)
        and is_fresh(market_quotes_path, args.sector_scan_max_age_days)
    ):
        return generated_sector_path
    return build_sector_metrics_from_market_quotes(
        market_quotes_path=market_quotes_path,
        base_sector_metrics_path=Path(args.data_dir) / "sector_metrics.csv",
        output_path=generated_sector_path,
    )


def _refresh_latest_depth_snapshot(args) -> None:
    today = datetime.now(ZoneInfo("Asia/Taipei")).date()
    trade_date = recent_weekdays(today, 1)[0]
    ymd = trade_date.strftime("%Y%m%d")
    saved_raw, errors = fetch_raw_market_snapshots(trade_date, args.raw_output_dir)
    for path in saved_raw:
        print(f"Saved {path}")
    for error in errors:
        print(f"Warning: {error}")

    raw_dir = Path(args.raw_output_dir) / ymd
    if not raw_dir.exists():
        return
    processed_dir = Path(args.processed_output_dir) / ymd
    for path in normalize_raw_directory(raw_dir, processed_dir):
        print(f"Saved {path}")


if __name__ == "__main__":
    main()
