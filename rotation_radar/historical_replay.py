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
    backtest_grade_manifest_path: Path
    backtest_grade_readiness_path: Path
    backtest_grade_daily_coverage_path: Path


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


REQUIRED_BACKTEST_COLUMNS = [
    "date",
    "theme",
    "symbol",
    "name",
    "theme_rank",
    "theme_score",
    "stock_score",
    "fundamental_score",
    "risk_heat",
    "stock_turnover_rank_in_theme",
    "stock_turnover_share_in_theme",
    "turnover_value",
    "capital_share",
    "bucket",
    "fundamental_pass",
    "fundamental_source_date",
    "theme_leader_flag",
    "theme_second_line_flag",
    "theme_laggard_rebound_flag",
    "overheated_flag",
]


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
    backtest_grade_manifest_path = output / "historical_backtest_grade_manifest.json"
    backtest_grade_readiness_path = output / "historical_backtest_grade_readiness.json"
    backtest_grade_daily_coverage_path = output / "historical_backtest_grade_daily_coverage.csv"
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
    inspection = _inspect_backtest_grade_snapshots(paths)
    _write_backtest_grade_daily_coverage(backtest_grade_daily_coverage_path, inspection["daily_rows"])
    _write_backtest_grade_manifest(
        manifest_path=backtest_grade_manifest_path,
        readiness_path=backtest_grade_readiness_path,
        daily_coverage_path=backtest_grade_daily_coverage_path,
        legacy_manifest_path=manifest_path,
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
        inspection=inspection,
        warnings=warnings,
    )

    return HistoricalReplayResult(
        paths=paths,
        warnings=warnings,
        manifest_path=manifest_path,
        coverage_path=coverage_path,
        backtest_grade_manifest_path=backtest_grade_manifest_path,
        backtest_grade_readiness_path=backtest_grade_readiness_path,
        backtest_grade_daily_coverage_path=backtest_grade_daily_coverage_path,
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


def _inspect_backtest_grade_snapshots(paths: list[Path]) -> dict[str, object]:
    daily_rows: list[dict[str, str | int]] = []
    missing_required_columns: dict[str, list[str]] = {}
    future_fundamental_violation_count = 0
    missing_fundamental_symbols: set[str] = set()

    for path in sorted(paths):
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            fieldnames = reader.fieldnames or []
            missing_columns = [column for column in REQUIRED_BACKTEST_COLUMNS if column not in fieldnames]
            if missing_columns:
                missing_required_columns[path.name] = missing_columns

            rows = list(reader)

        date_text = _snapshot_date_from_path(path)
        themes = {str(row.get("theme", "")) for row in rows if row.get("theme")}
        symbols = {str(row.get("symbol", "")) for row in rows if row.get("symbol")}
        fundamental_pass_count = sum(1 for row in rows if str(row.get("fundamental_pass", "")).lower() == "true")
        missing_fundamental_count = 0
        future_violations_for_date = 0
        for row in rows:
            status = str(row.get("fundamental_data_status", ""))
            symbol = str(row.get("symbol", ""))
            if status == "missing_fundamental_data":
                missing_fundamental_count += 1
                if symbol:
                    missing_fundamental_symbols.add(symbol)
            source_date = _normalize_date(str(row.get("fundamental_source_date", "")))
            row_date = _normalize_date(str(row.get("date", ""))) or date_text
            if source_date and row_date and source_date > row_date:
                future_violations_for_date += 1

        future_fundamental_violation_count += future_violations_for_date
        daily_rows.append(
            {
                "date": date_text,
                "snapshot_file": path.name,
                "row_count": len(rows),
                "theme_count": len(themes),
                "stock_count": len(symbols),
                "fundamental_pass_count": fundamental_pass_count,
                "missing_fundamental_count": missing_fundamental_count,
                "future_fundamental_violation_count": future_violations_for_date,
                "missing_required_columns": ";".join(missing_columns),
            }
        )

    return {
        "daily_rows": daily_rows,
        "missing_required_columns": missing_required_columns,
        "required_columns_missing_count": sum(len(value) for value in missing_required_columns.values()),
        "future_fundamental_violation_count": future_fundamental_violation_count,
        "missing_fundamental_symbols": sorted(missing_fundamental_symbols),
    }


def _write_backtest_grade_daily_coverage(path: Path, rows: object) -> None:
    fieldnames = [
        "date",
        "snapshot_file",
        "row_count",
        "theme_count",
        "stock_count",
        "fundamental_pass_count",
        "missing_fundamental_count",
        "future_fundamental_violation_count",
        "missing_required_columns",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)  # type: ignore[arg-type]


def _write_backtest_grade_manifest(
    *,
    manifest_path: Path,
    readiness_path: Path,
    daily_coverage_path: Path,
    legacy_manifest_path: Path,
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
    inspection: dict[str, object],
    warnings: list[str],
) -> None:
    readiness = _build_backtest_grade_readiness(
        readiness_path=readiness_path,
        daily_coverage_path=daily_coverage_path,
        start_date=start_date,
        end_date=end_date,
        dates=dates,
        missing_symbols=missing_symbols,
        inspection=inspection,
        warnings=warnings,
    )
    manifest = {
        "dataset_type": "historical_backtest_grade_replay",
        "dataset_mode": "backtest_grade_limited_replay",
        "description": (
            "Historical radar snapshots for backtest ingestion. This package is schema/readiness checked, "
            "but it is not a real-time archived daily radar record."
        ),
        "requested_start_date": start_date,
        "requested_end_date": end_date,
        "actual_start_date": dates[0] if dates else "",
        "actual_end_date": dates[-1] if dates else "",
        "snapshot_count": len(dates),
        "required_columns": REQUIRED_BACKTEST_COLUMNS,
        "price_source": str(price_cache_dir),
        "theme_map_path": str(theme_map_path),
        "stock_metrics_path": str(stock_metrics_path),
        "output_dir": str(output_dir),
        "legacy_manifest_path": str(legacy_manifest_path),
        "readiness_path": str(readiness_path),
        "daily_coverage_path": str(daily_coverage_path),
        "fundamental_mode": "limited_baseline_seed_carry_forward",
        "fundamental_source_rule": "fundamental_source_date <= snapshot date; missing rows fail closed",
        "theme_membership_mode": "current_static_map",
        "versioned_theme_membership_available": False,
        "turnover_mode": "approximate_close_times_volume",
        "turnover_unit": "TWD million",
        "theme_rank_method": "replay_final_composite_score",
        "theme_map_symbol_count": len({row.symbol for row in theme_map}),
        "covered_symbol_count": len(covered_symbols),
        "missing_ohlcv_symbol_count": len(missing_symbols),
        "missing_ohlcv_symbols": missing_symbols,
        "missing_fundamental_symbol_count": len(readiness["missing_fundamental_symbols"]),
        "missing_fundamental_symbols": readiness["missing_fundamental_symbols"],
        "readiness_summary": readiness,
        "limitations": [
            "This output is a limited historical replay package, not a real-time archived daily radar history.",
            "Theme membership uses the current static theme_map.csv and may not reflect historical membership changes.",
            "Turnover value is approximated from close * volume because the OHLCV cache does not provide official exchange turnover amount.",
            "Fundamental fields use the configured baseline stock metrics file seeded at the first replay date; missing rows fail closed.",
            "Formal strategy conclusions should disclose these modes and should not present this as a fully point-in-time historical production feed.",
        ],
        "warnings": warnings,
    }
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    with manifest_path.open("w", encoding="utf-8") as handle:
        json.dump(manifest, handle, ensure_ascii=False, indent=2)
    with readiness_path.open("w", encoding="utf-8") as handle:
        json.dump(readiness, handle, ensure_ascii=False, indent=2)


def _build_backtest_grade_readiness(
    *,
    readiness_path: Path,
    daily_coverage_path: Path,
    start_date: str,
    end_date: str,
    dates: list[str],
    missing_symbols: list[str],
    inspection: dict[str, object],
    warnings: list[str],
) -> dict[str, object]:
    missing_required_columns = inspection["missing_required_columns"]
    future_fundamental_violation_count = int(inspection["future_fundamental_violation_count"])
    daily_rows = inspection["daily_rows"]  # type: ignore[assignment]
    snapshot_count = len(dates)
    missing_snapshot_dates = [
        str(row["date"])
        for row in daily_rows  # type: ignore[union-attr]
        if int(row["row_count"]) <= 0
    ]
    ready_for_ingestion = (
        snapshot_count > 0
        and not missing_snapshot_dates
        and int(inspection["required_columns_missing_count"]) == 0
        and future_fundamental_violation_count == 0
    )
    status = "ready_with_limitations" if ready_for_ingestion else "not_ready"
    return {
        "ready_for_backtest_lab_ingestion": ready_for_ingestion,
        "ready_for_formal_strategy_conclusion": False,
        "readiness_status": status,
        "requested_start_date": start_date,
        "requested_end_date": end_date,
        "actual_start_date": dates[0] if dates else "",
        "actual_end_date": dates[-1] if dates else "",
        "snapshot_count": snapshot_count,
        "missing_snapshot_count": len(missing_snapshot_dates),
        "missing_snapshot_dates": missing_snapshot_dates,
        "required_columns_missing_count": int(inspection["required_columns_missing_count"]),
        "missing_required_columns_by_file": missing_required_columns,
        "future_fundamental_violation_count": future_fundamental_violation_count,
        "missing_ohlcv_symbol_count": len(missing_symbols),
        "missing_ohlcv_symbols": missing_symbols,
        "missing_fundamental_symbol_count": len(inspection["missing_fundamental_symbols"]),  # type: ignore[arg-type]
        "missing_fundamental_symbols": inspection["missing_fundamental_symbols"],
        "fundamental_mode": "limited_baseline_seed_carry_forward",
        "theme_membership_mode": "current_static_map",
        "turnover_mode": "approximate_close_times_volume",
        "daily_coverage_path": str(daily_coverage_path),
        "readiness_path": str(readiness_path),
        "warnings": warnings,
    }


def _snapshot_date_from_path(path: Path) -> str:
    stem = path.stem
    return stem.rsplit("_", 1)[-1] if "_" in stem else ""
