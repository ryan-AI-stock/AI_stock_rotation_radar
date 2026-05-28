from __future__ import annotations

import csv
from datetime import datetime
from collections import defaultdict
from pathlib import Path
from typing import Any

from .theme_metrics import load_stock_theme_tags


def update_theme_history(
    sector_metrics_path: str | Path,
    theme_quotes_path: str | Path,
    output_path: str | Path,
    keep_days: int = 14,
) -> Path:
    trade_date = _trade_date_from_quotes(theme_quotes_path) or datetime.now().strftime("%Y-%m-%d")
    current_rows = _read_csv(sector_metrics_path)
    existing_rows = _read_csv(output_path) if Path(output_path).exists() else []
    merged: dict[tuple[str, str], dict[str, str]] = {}

    for row in existing_rows:
        date = row.get("date", "").strip()
        theme = row.get("theme", "").strip()
        if date and theme:
            merged[(date, theme)] = row

    for rank, row in enumerate(current_rows, start=1):
        theme = row.get("name", "").strip()
        if not theme:
            continue
        merged[(trade_date, theme)] = {
            "date": trade_date,
            "theme": theme,
            "rank": str(rank),
            "capital_share": row.get("capital_share", "0"),
            "turnover_value": row.get("turnover_value", "0"),
            "strong_stock_ratio": row.get("strong_stock_ratio", "0"),
            "risk_heat": row.get("risk_heat", "0"),
        }

    dates = sorted({date for date, _theme in merged.keys()})[-keep_days:]
    output_rows = [row for (date, _theme), row in merged.items() if date in dates]
    output_rows.sort(key=lambda row: (row["date"], _num(row.get("rank"))))

    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(_field_order()))
        writer.writeheader()
        writer.writerows(output_rows)
    return path


def backfill_theme_history_from_processed(
    processed_root: str | Path,
    theme_map_path: str | Path,
    theme_universe_path: str | Path,
    base_sector_metrics_path: str | Path,
    output_path: str | Path,
    keep_days: int = 14,
) -> Path:
    """Backfill theme history from normalized historical price snapshots.

    This prevents one missed scheduled run from leaving the 5-day theme view
    permanently short. It only uses exchange-published historical snapshots that
    are already cached or fetched by the daily report flow.
    """

    root = Path(processed_root)
    existing_rows = _read_csv(output_path) if Path(output_path).exists() else []
    merged: dict[tuple[str, str], dict[str, str]] = {}
    base_rows = {row.get("name", "").strip(): row for row in _read_csv(base_sector_metrics_path)}
    symbol_themes = load_stock_theme_tags(theme_map_path, theme_universe_path)

    for row in existing_rows:
        date = row.get("date", "").strip()
        theme = row.get("theme", "").strip()
        if date and theme:
            merged[(date, theme)] = row

    if root.exists():
        folders = sorted(path for path in root.iterdir() if path.is_dir() and path.name.isdigit())[-keep_days:]
        for folder in folders:
            date_text = _display_date(folder.name)
            theme_rows = _theme_rows_from_processed_folder(folder, symbol_themes, base_rows)
            for rank, row in enumerate(theme_rows, start=1):
                theme = row["theme"]
                merged[(date_text, theme)] = {
                    "date": date_text,
                    "theme": theme,
                    "rank": str(rank),
                    "capital_share": _fmt(row["capital_share"]),
                    "turnover_value": _fmt(row["turnover_value"]),
                    "strong_stock_ratio": _fmt(row["strong_stock_ratio"]),
                    "risk_heat": _fmt(row["risk_heat"]),
                }

    dates = sorted({date for date, _theme in merged.keys()})[-keep_days:]
    output_rows = [row for (date, _theme), row in merged.items() if date in dates]
    output_rows.sort(key=lambda row: (row["date"], _num(row.get("rank"))))

    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(_field_order()))
        writer.writeheader()
        writer.writerows(output_rows)
    return path


def load_theme_trends(
    history_path: str | Path,
    current_metrics_path: str | Path,
    window_days: int = 5,
) -> dict[str, dict[str, float | str]]:
    history_rows = _read_csv(history_path) if Path(history_path).exists() else []
    current_themes = [row.get("name", "").strip() for row in _read_csv(current_metrics_path)]
    trends: dict[str, dict[str, float | str]] = {}

    for theme in current_themes:
        rows = [row for row in history_rows if row.get("theme") == theme]
        rows.sort(key=lambda row: row.get("date", ""))
        rows = rows[-window_days:]
        available_dates = [row.get("date", "") for row in rows if row.get("date")]
        days = len(set(available_dates))
        amount_5d = sum(_num(row.get("turnover_value")) for row in rows)
        avg_share = sum(_num(row.get("capital_share")) for row in rows) / days if days else 0.0

        if days < 2:
            status = "今日觀察"
            rank_change = 0.0
            amount_change_pct = 0.0
        else:
            first, latest = rows[0], rows[-1]
            rank_change = _num(first.get("rank")) - _num(latest.get("rank"))
            first_amount = _num(first.get("turnover_value"))
            latest_amount = _num(latest.get("turnover_value"))
            amount_change_pct = (latest_amount - first_amount) / first_amount * 100 if first_amount else 0.0
            status = _trend_status(rank_change, amount_change_pct)

        trends[theme] = {
            "days": days,
            "amount_5d": amount_5d,
            "avg_share": avg_share,
            "rank_change": rank_change,
            "amount_change_pct": amount_change_pct,
            "status": status,
            "start_date": available_dates[0] if available_dates else "",
            "latest_date": available_dates[-1] if available_dates else "",
            "window_days": window_days,
            "missing_days": max(0, window_days - days),
        }
    return trends


def _theme_rows_from_processed_folder(
    folder: Path,
    symbol_themes: dict[str, list[str]],
    base_rows: dict[str, dict[str, str]],
) -> list[dict[str, float | str]]:
    symbol_quotes: dict[str, dict[str, float | str]] = {}
    for path in folder.glob("*prices*.csv"):
        for row in _read_csv(path):
            item = _price_row(row)
            if not item:
                continue
            symbol_quotes[str(item["symbol"])] = item

    theme_amounts: dict[str, float] = defaultdict(float)
    theme_counts: dict[str, int] = defaultdict(int)
    theme_active_counts: dict[str, int] = defaultdict(int)
    for symbol, quote in symbol_quotes.items():
        amount = float(quote["amount_million"])
        if amount <= 0:
            continue
        for theme in symbol_themes.get(symbol, []):
            theme_amounts[theme] += amount
            theme_counts[theme] += 1
            if amount >= 100:
                theme_active_counts[theme] += 1

    total_amount = sum(theme_amounts.values()) or 1.0
    rows: list[dict[str, float | str]] = []
    for theme, amount in theme_amounts.items():
        count = theme_counts.get(theme, 0)
        base_row = base_rows.get(theme, {})
        rows.append(
            {
                "theme": theme,
                "turnover_value": amount,
                "capital_share": amount / total_amount * 100,
                "strong_stock_ratio": theme_active_counts.get(theme, 0) / count * 100 if count else 0.0,
                "risk_heat": _num(base_row.get("risk_heat")) or 50.0,
            }
        )
    rows.sort(key=lambda row: float(row["turnover_value"]), reverse=True)
    return rows


def _price_row(row: dict[str, str]) -> dict[str, float | str] | None:
    symbol = (row.get("證券代號") or row.get("代號") or "").strip()
    amount = _num(row.get("成交金額(元)") or row.get("成交金額"))
    open_ = _num(row.get("開盤價") or row.get("開盤"))
    high = _num(row.get("最高價") or row.get("最高"))
    low = _num(row.get("最低價") or row.get("最低"))
    close = _num(row.get("收盤價") or row.get("收盤"))
    if not symbol or amount <= 0 or min(open_, high, low, close) <= 0:
        return None
    return {"symbol": symbol, "amount_million": amount / 1_000_000}


def _trade_date_from_quotes(path: str | Path) -> str | None:
    rows = _read_csv(path)
    for row in rows:
        raw = row.get("quote_date", "").strip()
        if len(raw) == 8 and raw.isdigit():
            return f"{raw[:4]}-{raw[4:6]}-{raw[6:]}"
    return None


def _display_date(value: str) -> str:
    if len(value) == 8 and value.isdigit():
        return f"{value[:4]}-{value[4:6]}-{value[6:]}"
    return value


def _trend_status(rank_change: float, amount_change_pct: float) -> str:
    if rank_change >= 2 or amount_change_pct >= 20:
        return "升溫"
    if rank_change <= -2 or amount_change_pct <= -20:
        return "降溫"
    return "持平"


def _read_csv(path: str | Path) -> list[dict[str, str]]:
    csv_path = Path(path)
    if not csv_path.exists():
        return []
    with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def _num(value: Any) -> float:
    if value is None:
        return 0.0
    raw = str(value).replace(",", "").strip()
    if raw in {"", "-", "--"}:
        return 0.0
    try:
        return float(raw)
    except ValueError:
        return 0.0


def _fmt(value: float) -> str:
    return f"{value:.2f}".rstrip("0").rstrip(".")


def _field_order() -> tuple[str, ...]:
    return (
        "date",
        "theme",
        "rank",
        "capital_share",
        "turnover_value",
        "strong_stock_ratio",
        "risk_heat",
    )
