from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path


SNAPSHOT_COLUMNS = [
    "date",
    "theme",
    "symbol",
    "name",
    "theme_rank",
    "theme_score",
    "capital_share",
    "capital_share_5d_avg",
    "capital_share_5d_change",
    "turnover_value",
    "turnover_value_5d",
    "strong_stock_ratio",
    "theme_risk_heat",
    "stock_score",
    "bucket",
    "fundamental_pass",
    "fundamental_score",
    "fundamental_data_status",
    "fundamental_source_date",
    "fundamental_reason",
    "risk_heat",
    "liquidity",
    "foreign_5d",
    "trust_5d",
    "margin_change_5d",
    "stock_turnover_rank_in_theme",
    "stock_turnover_share_in_theme",
    "stock_turnover_share_change_5d",
    "theme_leader_flag",
    "theme_second_line_flag",
    "theme_laggard_rebound_flag",
    "overheated_flag",
]


@dataclass(frozen=True)
class SnapshotBuildResult:
    paths: list[Path]
    warnings: list[str]


@dataclass(frozen=True)
class ThemeHistoryRow:
    date: str
    theme: str
    rank: int
    capital_share: float
    turnover_value: float
    strong_stock_ratio: float
    risk_heat: float


@dataclass(frozen=True)
class ThemeMapRow:
    theme: str
    symbol: str
    name: str


@dataclass(frozen=True)
class PriceRow:
    symbol: str
    name: str
    close: float
    amount_million: float
    change_pct: float


def build_radar_snapshots(
    *,
    processed_root: str | Path,
    theme_history_path: str | Path,
    theme_map_path: str | Path,
    stock_metrics_path: str | Path,
    output_dir: str | Path,
    days: int = 20,
    overwrite_existing: bool = False,
    baseline_stock_metrics_path: str | Path | None = None,
) -> SnapshotBuildResult:
    theme_history = _load_theme_history(theme_history_path)
    theme_map = _load_theme_map(theme_map_path)
    stock_metrics = _load_stock_metrics(stock_metrics_path)
    baseline_stock_metrics = _load_stock_metrics(baseline_stock_metrics_path) if baseline_stock_metrics_path else {}
    processed_dates = _available_processed_dates(processed_root)
    target_dates = [date for date in sorted(theme_history) if date in processed_dates][-days:]

    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)

    paths: list[Path] = []
    warnings: list[str] = []
    daily_prices: dict[str, dict[str, PriceRow]] = {}
    daily_theme_stock_shares: dict[str, dict[tuple[str, str], float]] = {}

    for date in target_dates:
        daily_prices[date] = _load_processed_prices(Path(processed_root) / date, _previous_price_map(date, daily_prices))
        if not daily_prices[date]:
            warnings.append(f"missing processed price rows for {date}")
        daily_theme_stock_shares[date] = _stock_turnover_shares(theme_map, daily_prices[date])

    latest_date = target_dates[-1] if target_dates else ""
    earliest_date = target_dates[0] if target_dates else ""
    if earliest_date and baseline_stock_metrics:
        _write_fundamental_snapshot(output / f"fundamental_snapshot_{earliest_date}.csv", baseline_stock_metrics)
    if latest_date:
        _write_fundamental_snapshot(
            output / f"fundamental_snapshot_{latest_date}.csv",
            _merge_stock_metrics(stock_metrics, baseline_stock_metrics),
        )
    fundamental_snapshots = _load_fundamental_snapshots(output)
    for date in target_dates:
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
            warnings.append(f"no snapshot rows built for {date}")
            continue
        _write_snapshot(path, rows)
        paths.append(path)

    if not target_dates:
        warnings.append("no overlapping theme history and processed price dates")
    elif len(target_dates) < days:
        warnings.append(f"only {len(target_dates)} overlapping trading dates available; requested {days}")
    return SnapshotBuildResult(paths=paths, warnings=warnings)


def _build_snapshot_rows(
    *,
    date: str,
    theme_history: dict[str, dict[str, ThemeHistoryRow]],
    theme_map: list[ThemeMapRow],
    stock_metrics: dict[str, dict[str, str]],
    fundamental_source_date: str,
    prices: dict[str, PriceRow],
    daily_theme_stock_shares: dict[str, dict[tuple[str, str], float]],
) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    theme_rows = theme_history.get(date, {})
    theme_map_by_theme: dict[str, list[ThemeMapRow]] = {}
    for item in theme_map:
        theme_map_by_theme.setdefault(item.theme, []).append(item)

    for theme, history_row in sorted(theme_rows.items(), key=lambda item: item[1].rank):
        mapped = theme_map_by_theme.get(theme, [])
        if not mapped:
            continue
        theme_window = _theme_window(theme_history, date, theme)
        capital_share_5d_avg = _average([item.capital_share for item in theme_window])
        turnover_value_5d = sum(item.turnover_value for item in theme_window)
        previous_window = theme_window[:-1]
        previous_capital_share = _average([item.capital_share for item in previous_window])
        capital_share_5d_change = history_row.capital_share - previous_capital_share if previous_window else 0.0
        theme_score = _bounded(
            history_row.capital_share * 2.0
            + history_row.strong_stock_ratio * 0.35
            + max(0.0, 100.0 - history_row.risk_heat) * 0.15
        )
        rank_lookup = _theme_rank_lookup(theme, mapped, prices)

        for stock in mapped:
            price = prices.get(stock.symbol)
            stock_metric = stock_metrics.get(stock.symbol, {})
            fundamental = _fundamental_status(stock_metric, source_date=fundamental_source_date)
            stock_share = daily_theme_stock_shares.get(date, {}).get((theme, stock.symbol), 0.0)
            stock_share_change = stock_share - _previous_stock_share_average(
                daily_theme_stock_shares, date, theme, stock.symbol
            )
            turnover_rank = rank_lookup.get(stock.symbol, 0)
            liquidity = _liquidity_score(price.amount_million if price else 0.0)
            risk_heat = _stock_risk_heat(history_row.risk_heat, price.change_pct if price else 0.0)
            overheated = risk_heat >= 70.0 or (price.change_pct if price else 0.0) >= 7.0
            leader = turnover_rank > 0 and turnover_rank <= 2 and stock_share >= 15.0
            second_line = 3 <= turnover_rank <= 5 and stock_share_change > 0.0
            laggard_rebound = turnover_rank > 5 and stock_share_change >= 2.0
            bucket = _bucket(fundamental, overheated, leader, second_line, laggard_rebound)
            stock_score = _bounded(liquidity * 0.35 + stock_share * 0.35 + max(0.0, 100.0 - risk_heat) * 0.30)
            rows.append(
                {
                    "date": _format_date(date),
                    "theme": theme,
                    "symbol": stock.symbol,
                    "name": price.name if price and price.name else stock.name,
                    "theme_rank": str(history_row.rank),
                    "theme_score": _fmt(theme_score),
                    "capital_share": _fmt(history_row.capital_share),
                    "capital_share_5d_avg": _fmt(capital_share_5d_avg),
                    "capital_share_5d_change": _fmt(capital_share_5d_change),
                    "turnover_value": _fmt(history_row.turnover_value),
                    "turnover_value_5d": _fmt(turnover_value_5d),
                    "strong_stock_ratio": _fmt(history_row.strong_stock_ratio),
                    "theme_risk_heat": _fmt(history_row.risk_heat),
                    "stock_score": _fmt(stock_score),
                    "bucket": bucket,
                    "fundamental_pass": str(fundamental["pass"]).lower(),
                    "fundamental_score": _fmt(fundamental["score"]),
                    "fundamental_data_status": str(fundamental["status"]),
                    "fundamental_source_date": _format_date(fundamental_source_date) if fundamental_source_date else "",
                    "fundamental_reason": str(fundamental["reason"]),
                    "risk_heat": _fmt(risk_heat),
                    "liquidity": _fmt(liquidity),
                    "foreign_5d": stock_metric.get("foreign_5d", "0") or "0",
                    "trust_5d": stock_metric.get("trust_5d", "0") or "0",
                    "margin_change_5d": stock_metric.get("margin_change_5d", "0") or "0",
                    "stock_turnover_rank_in_theme": str(turnover_rank),
                    "stock_turnover_share_in_theme": _fmt(stock_share),
                    "stock_turnover_share_change_5d": _fmt(stock_share_change),
                    "theme_leader_flag": str(leader).lower(),
                    "theme_second_line_flag": str(second_line).lower(),
                    "theme_laggard_rebound_flag": str(laggard_rebound).lower(),
                    "overheated_flag": str(overheated).lower(),
                }
            )
    return rows


def _load_theme_history(path: str | Path) -> dict[str, dict[str, ThemeHistoryRow]]:
    history: dict[str, dict[str, ThemeHistoryRow]] = {}
    with Path(path).open("r", encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            date = _normalize_date(row.get("date", ""))
            theme = (row.get("theme") or "").strip()
            if not date or not theme:
                continue
            history.setdefault(date, {})[theme] = ThemeHistoryRow(
                date=date,
                theme=theme,
                rank=int(_to_float(row.get("rank"), 0)),
                capital_share=_to_float(row.get("capital_share"), 0),
                turnover_value=_to_float(row.get("turnover_value"), 0),
                strong_stock_ratio=_to_float(row.get("strong_stock_ratio"), 0),
                risk_heat=_to_float(row.get("risk_heat"), 0),
            )
    return history


def _load_theme_map(path: str | Path) -> list[ThemeMapRow]:
    rows: list[ThemeMapRow] = []
    with Path(path).open("r", encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            theme = (row.get("theme") or "").strip()
            symbol = (row.get("symbol") or "").strip()
            if not theme or not symbol:
                continue
            rows.append(ThemeMapRow(theme=theme, symbol=symbol, name=(row.get("name") or "").strip()))
    return rows


def _load_stock_metrics(path: str | Path) -> dict[str, dict[str, str]]:
    stock_path = Path(path)
    if not stock_path.exists():
        return {}
    with stock_path.open("r", encoding="utf-8-sig", newline="") as handle:
        return {
            (row.get("symbol") or "").strip(): row
            for row in csv.DictReader(handle)
            if (row.get("symbol") or "").strip()
        }


def _merge_stock_metrics(
    primary: dict[str, dict[str, str]],
    fallback: dict[str, dict[str, str]],
) -> dict[str, dict[str, str]]:
    merged = {symbol: dict(row) for symbol, row in primary.items()}
    for symbol, fallback_row in fallback.items():
        current = merged.get(symbol, {})
        if _has_fundamental_data(current):
            continue
        merged[symbol] = dict(current) | dict(fallback_row)
    return merged


def _has_fundamental_data(row: dict[str, str]) -> bool:
    return _to_float(row.get("pe"), 0) > 0 and _to_float(row.get("revenue_yoy"), 0) != 0


def _write_fundamental_snapshot(path: Path, rows: dict[str, dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "symbol",
        "name",
        "pe",
        "revenue_yoy",
        "revenue_mom",
        "foreign_5d",
        "trust_5d",
        "margin_change_5d",
        "risk_reason",
    ]
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for symbol, row in sorted(rows.items()):
            writer.writerow({field: row.get(field, "") for field in fieldnames} | {"symbol": symbol})


def _load_fundamental_snapshots(path: Path) -> dict[str, dict[str, dict[str, str]]]:
    snapshots: dict[str, dict[str, dict[str, str]]] = {}
    for csv_path in sorted(path.glob("fundamental_snapshot_*.csv")):
        date = _normalize_date(csv_path.stem.replace("fundamental_snapshot_", ""))
        if not date:
            continue
        snapshots[date] = _load_stock_metrics(csv_path)
    return snapshots


def _fundamental_snapshot_for_date(
    snapshots: dict[str, dict[str, dict[str, str]]],
    date: str,
) -> tuple[str, dict[str, dict[str, str]]]:
    valid_dates = [snapshot_date for snapshot_date in sorted(snapshots) if snapshot_date <= date]
    if not valid_dates:
        return "", {}
    source_date = valid_dates[-1]
    return source_date, snapshots[source_date]


def _available_processed_dates(root: str | Path) -> set[str]:
    root_path = Path(root)
    if not root_path.exists():
        return set()
    return {path.name for path in root_path.iterdir() if path.is_dir() and path.name.isdigit()}


def _load_processed_prices(path: Path, previous_prices: dict[str, PriceRow]) -> dict[str, PriceRow]:
    prices: dict[str, PriceRow] = {}
    if not path.exists():
        return prices
    for csv_path in sorted(path.glob("*prices*.csv")):
        with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
            for row in csv.DictReader(handle):
                symbol = (row.get("證券代號") or row.get("代號") or "").strip()
                if not symbol:
                    continue
                close = _to_float(row.get("收盤價") or row.get("收盤"), 0)
                amount = _to_float(row.get("成交金額") or row.get("成交金額(元)"), 0) / 1_000_000
                previous_close = previous_prices.get(symbol).close if symbol in previous_prices else 0.0
                change_pct = ((close - previous_close) / previous_close * 100.0) if previous_close else 0.0
                prices[symbol] = PriceRow(
                    symbol=symbol,
                    name=(row.get("證券名稱") or row.get("名稱") or "").strip(),
                    close=close,
                    amount_million=amount,
                    change_pct=change_pct,
                )
    return prices


def _previous_price_map(date: str, daily_prices: dict[str, dict[str, PriceRow]]) -> dict[str, PriceRow]:
    previous_dates = [item for item in sorted(daily_prices) if item < date]
    if not previous_dates:
        return {}
    return daily_prices[previous_dates[-1]]


def _stock_turnover_shares(theme_map: list[ThemeMapRow], prices: dict[str, PriceRow]) -> dict[tuple[str, str], float]:
    totals: dict[str, float] = {}
    for item in theme_map:
        totals[item.theme] = totals.get(item.theme, 0.0) + (prices.get(item.symbol).amount_million if item.symbol in prices else 0.0)
    shares: dict[tuple[str, str], float] = {}
    for item in theme_map:
        total = totals.get(item.theme, 0.0)
        amount = prices.get(item.symbol).amount_million if item.symbol in prices else 0.0
        shares[(item.theme, item.symbol)] = (amount / total * 100.0) if total else 0.0
    return shares


def _theme_rank_lookup(theme: str, mapped: list[ThemeMapRow], prices: dict[str, PriceRow]) -> dict[str, int]:
    ranked = sorted(
        ((item.symbol, prices.get(item.symbol).amount_million if item.symbol in prices else 0.0) for item in mapped),
        key=lambda item: item[1],
        reverse=True,
    )
    return {symbol: index for index, (symbol, amount) in enumerate(ranked, start=1) if amount > 0.0}


def _theme_window(
    theme_history: dict[str, dict[str, ThemeHistoryRow]],
    date: str,
    theme: str,
) -> list[ThemeHistoryRow]:
    rows = [
        theme_rows[theme]
        for current_date, theme_rows in sorted(theme_history.items())
        if current_date <= date and theme in theme_rows
    ]
    return rows[-5:]


def _previous_stock_share_average(
    daily_theme_stock_shares: dict[str, dict[tuple[str, str], float]],
    date: str,
    theme: str,
    symbol: str,
) -> float:
    values = [
        shares.get((theme, symbol), 0.0)
        for current_date, shares in sorted(daily_theme_stock_shares.items())
        if current_date < date
    ][-4:]
    return _average(values)


def _fundamental_status(row: dict[str, str], *, source_date: str) -> dict[str, object]:
    if not source_date:
        return {
            "pass": False,
            "score": 0.0,
            "status": "missing_fundamental_data",
            "reason": "No dated fundamental source for this historical snapshot; excluded from qualified candidates",
        }
    pe = _to_float(row.get("pe"), 0)
    revenue_yoy = _to_float(row.get("revenue_yoy"), 0)
    revenue_mom = _to_float(row.get("revenue_mom"), 0)
    if not row or pe <= 0 or revenue_yoy == 0 or row.get("risk_reason") == "missing_deep_data":
        return {
            "pass": False,
            "score": 0.0,
            "status": "missing_fundamental_data",
            "reason": "PE or revenue data missing; excluded from qualified candidates",
        }
    score = 0.0
    score += 45.0 if revenue_yoy > 0 else 0.0
    score += 25.0 if revenue_mom >= -20 else 0.0
    score += 30.0 if 0 < pe <= 80 else 0.0
    passed = score >= 70.0
    return {
        "pass": passed,
        "score": score,
        "status": "ok",
        "reason": "fundamental checks passed" if passed else "fundamental checks incomplete",
    }


def _bucket(
    fundamental: dict[str, object],
    overheated: bool,
    leader: bool,
    second_line: bool,
    laggard_rebound: bool,
) -> str:
    if not fundamental["pass"]:
        return "excluded_missing_fundamental"
    if overheated:
        return "excluded_overheated"
    if leader:
        return "theme_leader"
    if second_line:
        return "theme_second_line"
    if laggard_rebound:
        return "laggard_rebound"
    return "watch"


def _liquidity_score(amount_million: float) -> float:
    return _bounded(amount_million / 20.0)


def _stock_risk_heat(theme_risk_heat: float, change_pct: float) -> float:
    return _bounded(theme_risk_heat * 0.75 + max(0.0, change_pct) * 4.0)


def _write_snapshot(path: Path, rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=SNAPSHOT_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)


def _normalize_date(value: str) -> str:
    digits = "".join(ch for ch in str(value) if ch.isdigit())
    return digits[:8] if len(digits) >= 8 else ""


def _format_date(value: str) -> str:
    return f"{value[:4]}-{value[4:6]}-{value[6:8]}"


def _average(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _bounded(value: float) -> float:
    return max(0.0, min(100.0, value))


def _to_float(value: object, default: float = 0.0) -> float:
    try:
        text = str(value if value is not None else "").replace(",", "").strip()
        return float(text) if text not in {"", "-"} else default
    except (TypeError, ValueError):
        return default


def _fmt(value: float) -> str:
    return f"{value:.1f}"
