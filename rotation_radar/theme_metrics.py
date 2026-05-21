from __future__ import annotations

import csv
from collections import defaultdict
from pathlib import Path
from typing import Any


ThemeRows = dict[str, list[dict[str, float | str]]]


def build_theme_market_quotes(
    market_quotes_path: str | Path,
    theme_map_path: str | Path,
    output_path: str | Path,
    fallback_stock_metrics_path: str | Path | None = None,
    theme_universe_path: str | Path | None = None,
) -> Path:
    """Write a quote file grouped by market theme instead of exchange industry."""

    allowed_themes = _load_theme_universe(theme_universe_path)
    symbol_themes = _load_symbol_theme_map(theme_map_path, allowed_themes)
    if fallback_stock_metrics_path is not None:
        for symbol, theme in _load_stock_metric_themes(fallback_stock_metrics_path).items():
            if symbol not in symbol_themes and _theme_allowed(theme, allowed_themes):
                symbol_themes[symbol] = [theme]
    rows: list[dict[str, str]] = []
    for row in _read_csv(market_quotes_path):
        symbol = row.get("symbol", "").strip()
        themes = symbol_themes.get(symbol, [])
        if not themes:
            continue
        for theme in themes:
            updated = dict(row)
            updated["sector"] = theme
            rows.append(updated)

    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(rows[0].keys()) if rows else list(_quote_field_order())
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    return path


def build_sector_theme_metrics(
    market_quotes_path: str | Path,
    base_stock_metrics_path: str | Path,
    limit: int = 3,
) -> ThemeRows:
    symbol_theme = _load_stock_metric_themes(base_stock_metrics_path)
    sector_totals: dict[str, float] = defaultdict(float)
    theme_totals: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))

    for row in _read_csv(market_quotes_path):
        sector = row.get("sector", "").strip()
        symbol = row.get("symbol", "").strip()
        amount = _num(row.get("amount_million"))
        if not sector or amount <= 0:
            continue
        sector_totals[sector] += amount
        theme = symbol_theme.get(symbol)
        if theme and theme != sector:
            theme_totals[sector][theme] += amount

    result: ThemeRows = {}
    for sector, themes in theme_totals.items():
        total = sector_totals.get(sector, 0.0)
        if total <= 0:
            continue
        rows: list[dict[str, float | str]] = []
        for theme, amount in sorted(themes.items(), key=lambda item: item[1], reverse=True)[:limit]:
            rows.append(
                {
                    "theme": theme,
                    "amount_million": amount,
                    "share": amount / total * 100,
                }
            )
        if rows:
            result[sector] = rows
    return result


def _load_symbol_theme_map(path: str | Path, allowed_themes: set[str] | None = None) -> dict[str, list[str]]:
    csv_path = Path(path)
    if not csv_path.exists():
        return {}
    themes: dict[str, list[str]] = {}
    for row in _read_csv(csv_path):
        symbol = row.get("symbol", "").strip()
        theme = row.get("theme", "").strip()
        primary = row.get("primary", "yes").strip().lower()
        if symbol and theme and primary not in {"no", "false", "0"} and _theme_allowed(theme, allowed_themes):
            themes.setdefault(symbol, [])
            if theme not in themes[symbol]:
                themes[symbol].append(theme)
    return themes


def _load_theme_universe(path: str | Path | None) -> set[str] | None:
    if path is None:
        return None
    csv_path = Path(path)
    if not csv_path.exists():
        return None
    themes = {row.get("theme", "").strip() for row in _read_csv(csv_path)}
    return {theme for theme in themes if theme}


def _theme_allowed(theme: str, allowed_themes: set[str] | None) -> bool:
    return allowed_themes is None or theme in allowed_themes


def _load_stock_metric_themes(path: str | Path) -> dict[str, str]:
    csv_path = Path(path)
    if not csv_path.exists():
        return {}
    themes: dict[str, str] = {}
    for row in _read_csv(csv_path):
        symbol = row.get("symbol", "").strip()
        theme = row.get("sector", "").strip()
        if symbol and theme:
            themes[symbol] = theme
    return themes


def _read_csv(path: str | Path) -> list[dict[str, str]]:
    with Path(path).open("r", encoding="utf-8-sig", newline="") as handle:
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


def _quote_field_order() -> tuple[str, ...]:
    return (
        "sector",
        "symbol",
        "name",
        "market",
        "price",
        "previous_close",
        "change_pct",
        "open",
        "high",
        "low",
        "volume_lots",
        "amount_million",
        "quote_date",
        "quote_time",
    )
