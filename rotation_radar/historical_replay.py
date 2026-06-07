from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from pathlib import Path

from .radar_snapshot import (
    PriceRow,
    SnapshotBuildResult,
    ThemeHistoryRow,
    ThemeMapRow,
    _bounded,
    _build_snapshot_rows,
    _fundamental_snapshot_for_date,
    _load_fundamental_snapshots,
    _load_stock_metrics,
    _load_theme_map,
    _normalize_date,
    _stock_turnover_shares,
    _to_float,
    _write_fundamental_snapshot,
    _write_snapshot,
)


@dataclass(frozen=True)
class HistoricalReplayResult(SnapshotBuildResult):
    manifest_path: Path
    coverage_path: Path


@dataclass(frozen=True)
class ReplayPriceRow:
    date: str
    symbol: str
    name: str
    close: float
    volume: float

    @property
    def amount_million(self) -> float:
        return self.close * self.volume / 1_000_000


def build_historical_replay_snapshots(
    *,
    price_cache_dir: str | Path,
    theme_map_path: str | Path,
    stock_metrics_path: str | Path,
    output_dir: str | Path,
    start_date: str = "2022-01-01",
    end_date: str = "2023-12-31",
    overwrite_existing: bool = False,
) -> HistoricalReplayResult:
    """Build clearly marked historical replay snapshots from OHLCV cache data.

    This is intentionally separate from the daily report snapshot flow. The input
    cache does not contain official exchange turnover, so turnover is approximated
    with close * volume and documented in the replay manifest.
    """

    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)

    theme_map_all = _load_theme_map(theme_map_path)
    stock_metrics = _load_stock_metrics(stock_metrics_path)
    price_rows_by_date, covered_symbols = _load_price_cache(
        price_cache_dir=price_cache_dir,
        theme_map=theme_map_all,
        start_date=_normalize_date(start_date),
        end_date=_normalize_date(end_date),
    )
    theme_map = [row for row in theme_map_all if row.symbol in covered_symbols]
    missing_symbols = sorted({row.symbol for row in theme_map_all} - covered_symbols)

    dates = sorted(price_rows_by_date)
    warnings: list[str] = []
    if not dates:
        warnings.append("no historical replay price rows found for requested date range")

    if dates:
        _write_fundamental_snapshot(output / f"fundamental_snapshot_{dates[0]}.csv", stock_metrics)

    daily_prices = _build_daily_prices(price_rows_by_date)
    daily_theme_stock_shares = {
        date: _stock_turnover_shares(theme_map, prices)
        for date, prices in daily_prices.items()
    }
    theme_history = _build_theme_history(theme_map, daily_prices)
    fundamental_snapshots = _load_fundamental_snapshots(output)

    paths: list[Path] = []
    for date in dates:
        path = output / f"radar_snapshot_{date}.csv"
        if path.exists() and not overwrite_existing:
            paths.append(path)
            continue
        fundamental_source_date, dated_stock_metrics = _fundamental_snapshot_for_date(fundamental_snapshots, date)
        rows = _build_snapshot_rows(
            date=date,
            theme_history=theme_history,
            theme_map=theme_map,
            stock_metrics=dated_stock_metrics,
            fundamental_source_date=fundamental_source_date,
            prices=daily_prices.get(date, {}),
            daily_theme_stock_shares=daily_theme_stock_shares,
        )
        if not rows:
            warnings.append(f"no replay snapshot rows built for {date}")
            continue
        _write_snapshot(path, rows)
        paths.append(path)

    coverage_path = output / "historical_replay_coverage.csv"
    manifest_path = output / "historical_replay_manifest.json"
    _write_coverage(
        coverage_path=coverage_path,
        theme_map=theme_map_all,
        covered_symbols=covered_symbols,
        missing_symbols=missing_symbols,
    )
    _write_manifest(
        manifest_path=manifest_path,
        price_cache_dir=Path(price_cache_dir),
        theme_map_path=Path(theme_map_path),
        stock_metrics_path=Path(stock_metrics_path),
        output_dir=output,
        start_date=start_date,
        end_date=end_date,
        dates=dates,
        theme_map=theme_map_all,
        covered_symbols=covered_symbols,
        missing_symbols=missing_symbols,
        warnings=warnings,
    )

    return HistoricalReplayResult(
        paths=paths,
        warnings=warnings,
        manifest_path=manifest_path,
        coverage_path=coverage_path,
    )


def _load_price_cache(
    *,
    price_cache_dir: str | Path,
    theme_map: list[ThemeMapRow],
    start_date: str,
    end_date: str,
) -> tuple[dict[str, dict[str, ReplayPriceRow]], set[str]]:
    cache_dir = Path(price_cache_dir)
    theme_names = {row.symbol: row.name for row in theme_map}
    price_rows_by_date: dict[str, dict[str, ReplayPriceRow]] = {}
    covered_symbols: set[str] = set()

    for csv_path in sorted(cache_dir.glob("*.csv")):
        symbol = _symbol_from_cache_file(csv_path)
        if symbol not in theme_names:
            continue
        with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
            rows_for_symbol = []
            for row in csv.DictReader(handle):
                date = _normalize_date(row.get("date", ""))
                if not date or date < start_date or date > end_date:
                    continue
                close = _to_float(row.get("close"), 0.0)
                volume = _to_float(row.get("volume"), 0.0)
                if close <= 0 or volume <= 0:
                    continue
                rows_for_symbol.append(
                    ReplayPriceRow(
                        date=date,
                        symbol=symbol,
                        name=theme_names[symbol],
                        close=close,
                        volume=volume,
                    )
                )
            if not rows_for_symbol:
                continue
            covered_symbols.add(symbol)
            for item in rows_for_symbol:
                price_rows_by_date.setdefault(item.date, {})[symbol] = item

    return price_rows_by_date, covered_symbols


def _symbol_from_cache_file(path: Path) -> str:
    return path.stem.split("_", 1)[0].strip()


def _build_daily_prices(price_rows_by_date: dict[str, dict[str, ReplayPriceRow]]) -> dict[str, dict[str, PriceRow]]:
    daily_prices: dict[str, dict[str, PriceRow]] = {}
    previous_prices: dict[str, ReplayPriceRow] = {}
    for date, rows in sorted(price_rows_by_date.items()):
        daily_prices[date] = {}
        for symbol, row in rows.items():
            previous_close = previous_prices.get(symbol).close if symbol in previous_prices else 0.0
            change_pct = ((row.close - previous_close) / previous_close * 100.0) if previous_close else 0.0
            daily_prices[date][symbol] = PriceRow(
                symbol=symbol,
                name=row.name,
                close=row.close,
                amount_million=row.amount_million,
                change_pct=change_pct,
            )
        previous_prices = previous_prices | rows
    return daily_prices


def _build_theme_history(
    theme_map: list[ThemeMapRow],
    daily_prices: dict[str, dict[str, PriceRow]],
) -> dict[str, dict[str, ThemeHistoryRow]]:
    theme_map_by_theme: dict[str, list[ThemeMapRow]] = {}
    for row in theme_map:
        theme_map_by_theme.setdefault(row.theme, []).append(row)

    history: dict[str, dict[str, ThemeHistoryRow]] = {}
    for date, prices in sorted(daily_prices.items()):
        raw_rows: list[tuple[str, float, float, float, float, float]] = []
        theme_amounts = {
            theme: sum(prices.get(row.symbol).amount_million for row in rows if row.symbol in prices)
            for theme, rows in theme_map_by_theme.items()
        }
        total_amount = sum(theme_amounts.values())
        for theme, mapped in theme_map_by_theme.items():
            amount = theme_amounts.get(theme, 0.0)
            if amount <= 0:
                continue
            priced = [prices[row.symbol] for row in mapped if row.symbol in prices]
            strong_stock_ratio = len([row for row in priced if row.change_pct > 0]) / len(priced) * 100.0 if priced else 0.0
            avg_change = sum(row.change_pct for row in priced) / len(priced) if priced else 0.0
            risk_heat = _bounded(45.0 + max(0.0, avg_change) * 5.0 + max(0.0, strong_stock_ratio - 60.0) * 0.35)
            capital_share = amount / total_amount * 100.0 if total_amount else 0.0
            score = _theme_score(capital_share, strong_stock_ratio, risk_heat)
            raw_rows.append((theme, capital_share, amount, strong_stock_ratio, risk_heat, score))

        ranked_rows = sorted(raw_rows, key=lambda row: row[5], reverse=True)
        history[date] = {
            theme: ThemeHistoryRow(
                date=date,
                theme=theme,
                rank=rank,
                capital_share=capital_share,
                turnover_value=amount,
                strong_stock_ratio=strong_stock_ratio,
                risk_heat=risk_heat,
            )
            for rank, (theme, capital_share, amount, strong_stock_ratio, risk_heat, score) in enumerate(ranked_rows, start=1)
        }
    return history


def _theme_score(capital_share: float, strong_stock_ratio: float, risk_heat: float) -> float:
    return _bounded(capital_share * 2.0 + strong_stock_ratio * 0.35 + max(0.0, 100.0 - risk_heat) * 0.15)


def _write_coverage(
    *,
    coverage_path: Path,
    theme_map: list[ThemeMapRow],
    covered_symbols: set[str],
    missing_symbols: list[str],
) -> None:
    names = {row.symbol: row.name for row in theme_map}
    coverage_path.parent.mkdir(parents=True, exist_ok=True)
    with coverage_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["symbol", "name", "coverage_status"])
        writer.writeheader()
        for symbol in sorted(covered_symbols):
            writer.writerow({"symbol": symbol, "name": names.get(symbol, ""), "coverage_status": "covered"})
        for symbol in missing_symbols:
            writer.writerow({"symbol": symbol, "name": names.get(symbol, ""), "coverage_status": "missing_price_cache"})


def _write_manifest(
    *,
    manifest_path: Path,
    price_cache_dir: Path,
    theme_map_path: Path,
    stock_metrics_path: Path,
    output_dir: Path,
    start_date: str,
    end_date: str,
    dates: list[str],
    theme_map: list[ThemeMapRow],
    covered_symbols: set[str],
    missing_symbols: list[str],
    warnings: list[str],
) -> None:
    manifest = {
        "dataset_type": "historical_replay",
        "description": "Historical replay snapshots for backtesting only; not real-time daily radar history.",
        "requested_start_date": start_date,
        "requested_end_date": end_date,
        "actual_start_date": dates[0] if dates else "",
        "actual_end_date": dates[-1] if dates else "",
        "trading_day_count": len(dates),
        "snapshot_count": len(dates),
        "price_source": str(price_cache_dir),
        "theme_map_path": str(theme_map_path),
        "stock_metrics_path": str(stock_metrics_path),
        "output_dir": str(output_dir),
        "turnover_method": "approximate_close_times_volume_million",
        "fundamental_method": "baseline_stock_metrics_seeded_at_first_replay_date_fail_closed_for_missing_rows",
        "theme_rank_method": "replay_final_composite_score",
        "theme_map_symbol_count": len({row.symbol for row in theme_map}),
        "covered_symbol_count": len(covered_symbols),
        "missing_symbol_count": len(missing_symbols),
        "missing_symbols": missing_symbols,
        "limitations": [
            "This output is marked as historical replay and should not be treated as real-time daily radar history.",
            "Turnover value is approximated from close * volume because the OHLCV cache does not provide official exchange turnover amount.",
            "Fundamental fields use the configured baseline stock metrics file and fail closed when a symbol has no usable row.",
            "The replay universe is limited to theme_map symbols that exist in the supplied price cache.",
        ],
        "warnings": warnings,
    }
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    with manifest_path.open("w", encoding="utf-8") as handle:
        json.dump(manifest, handle, ensure_ascii=False, indent=2)
