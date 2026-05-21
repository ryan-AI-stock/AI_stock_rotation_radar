from __future__ import annotations

import csv
from datetime import datetime
from pathlib import Path
from typing import Any


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
        days = len({row.get("date", "") for row in rows if row.get("date")})
        amount_5d = sum(_num(row.get("turnover_value")) for row in rows)
        avg_share = sum(_num(row.get("capital_share")) for row in rows) / days if days else 0.0

        if days < 2:
            status = "資料累積中"
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
        }
    return trends


def _trade_date_from_quotes(path: str | Path) -> str | None:
    rows = _read_csv(path)
    for row in rows:
        raw = row.get("quote_date", "").strip()
        if len(raw) == 8 and raw.isdigit():
            return f"{raw[:4]}-{raw[4:6]}-{raw[6:]}"
    return None


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
