from __future__ import annotations

import csv
from pathlib import Path

from .data_loader import load_sector_metrics
from .scoring import select_top_sector_names


def build_market_stock_candidates(
    market_quotes_path: str | Path,
    base_stock_metrics_path: str | Path,
    sector_metrics_path: str | Path,
    output_path: str | Path,
    limit: int = 45,
) -> Path:
    base_by_symbol = _read_by_key(base_stock_metrics_path, "symbol")
    top_sectors = _top_sectors(sector_metrics_path, limit=3)

    candidates: list[dict[str, str]] = []
    for quote in _read_csv(market_quotes_path):
        amount = _number(quote.get("amount_million")) or 0.0
        price = _number(quote.get("price")) or 0.0
        if amount < 200 or price <= 0:
            continue
        if quote["sector"] not in top_sectors:
            continue
        candidates.append(_candidate_row(quote, base_by_symbol.get(quote["symbol"])))

    candidates.sort(key=_candidate_sort_key, reverse=True)
    selected = _merge_tracked_first(candidates[:limit], base_by_symbol, {row["symbol"]: row for row in candidates})

    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(_stock_field_order()))
        writer.writeheader()
        writer.writerows(selected)
    return path


def export_hot_sector_symbols(
    market_quotes_path: str | Path,
    sector_metrics_path: str | Path,
    output_path: str | Path,
    top_sector_limit: int = 3,
    per_sector_limit: int = 40,
) -> Path:
    top_sectors = _top_sectors(sector_metrics_path, limit=top_sector_limit)
    rows_by_sector: dict[str, list[dict[str, str]]] = {sector: [] for sector in top_sectors}
    for row in _read_csv(market_quotes_path):
        if row["sector"] in top_sectors:
            rows_by_sector[row["sector"]].append(row)

    output_rows: list[dict[str, str]] = []
    for sector, rows in rows_by_sector.items():
        rows.sort(key=lambda row: _number(row.get("amount_million")) or 0.0, reverse=True)
        for row in rows[:per_sector_limit]:
            output_rows.append(
                {
                    "sector": sector,
                    "symbol": row["symbol"],
                    "name": row["name"],
                    "market": row.get("market", ""),
                    "price": row.get("price", ""),
                    "amount_million": row.get("amount_million", ""),
                    "change_pct": row.get("change_pct", ""),
                }
            )

    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["sector", "symbol", "name", "market", "price", "amount_million", "change_pct"],
        )
        writer.writeheader()
        writer.writerows(output_rows)
    return path


def _candidate_row(quote: dict[str, str], base: dict[str, str] | None) -> dict[str, str]:
    if base:
        row = dict(base)
        row["sector"] = quote["sector"]
        row["close"] = quote["price"]
        _refresh_fair_value(row)
        return row

    amount = _number(quote.get("amount_million")) or 0.0
    change_pct = _number(quote.get("change_pct")) or 0.0
    return {
        "symbol": quote["symbol"],
        "name": quote["name"],
        "sector": quote["sector"],
        "close": quote["price"],
        "pullback_quality": _fmt(_pullback_proxy(change_pct)),
        "chip_cleanliness": "50",
        "foreign_5d": "0",
        "trust_5d": "0",
        "margin_change_5d": "0",
        "pe": "0",
        "sector_pe_low": "0",
        "sector_pe_avg": "0",
        "sector_pe_high": "0",
        "fair_value_low": "0",
        "fair_value_avg": "0",
        "fair_value_high": "0",
        "revenue_yoy": "0",
        "revenue_mom": "0",
        "technical_setup": _fmt(_technical_score(change_pct)),
        "liquidity": _fmt(_liquidity_score(amount)),
        "risk_heat": _fmt(_risk_proxy(change_pct, amount)),
        "thesis": f"全市場初篩：成交金額 {amount:,.0f} 百萬元，當日漲跌 {change_pct:+.1f}%。",
        "risk_reason": "本益比、法人籌碼與融資資料尚未接入全市場資料源，先列為初篩候選。",
    }


def _merge_tracked_first(
    candidates: list[dict[str, str]],
    base_by_symbol: dict[str, dict[str, str]],
    candidates_by_symbol: dict[str, dict[str, str]],
) -> list[dict[str, str]]:
    selected_by_symbol = {row["symbol"]: row for row in candidates}
    for symbol, row in base_by_symbol.items():
        if symbol in candidates_by_symbol:
            selected_by_symbol.setdefault(symbol, candidates_by_symbol[symbol])
    return list(selected_by_symbol.values())


def _candidate_sort_key(row: dict[str, str]) -> tuple[float, float, float]:
    return (
        _number(row.get("liquidity")) or 0.0,
        _number(row.get("technical_setup")) or 0.0,
        -(_number(row.get("risk_heat")) or 0.0),
    )


def _top_sectors(path: str | Path, limit: int) -> tuple[str, ...]:
    return select_top_sector_names(load_sector_metrics(path), limit=limit)


def _refresh_fair_value(row: dict[str, str]) -> None:
    close = _number(row.get("close"))
    pe = _number(row.get("pe"))
    if close is None or pe in (None, 0):
        return
    eps = close / pe
    for suffix, key in (("low", "sector_pe_low"), ("avg", "sector_pe_avg"), ("high", "sector_pe_high")):
        sector_pe = _number(row.get(key))
        if sector_pe is not None:
            row[f"fair_value_{suffix}"] = _fmt(eps * sector_pe)


def _liquidity_score(amount_million: float) -> float:
    if amount_million >= 3000:
        return 100
    if amount_million >= 1500:
        return 92
    if amount_million >= 800:
        return 84
    if amount_million >= 400:
        return 72
    return 58


def _technical_score(change_pct: float) -> float:
    if 0.5 <= change_pct <= 5:
        return 78
    if -2 <= change_pct < 0.5:
        return 66
    if 5 < change_pct <= 8:
        return 62
    if change_pct < -2:
        return 45
    return 40


def _pullback_proxy(change_pct: float) -> float:
    if -2 <= change_pct <= 1.5:
        return 70
    if 1.5 < change_pct <= 4:
        return 62
    if change_pct < -2:
        return 52
    return 44


def _risk_proxy(change_pct: float, amount_million: float) -> float:
    risk = 48
    if change_pct >= 5:
        risk += 18
    if change_pct <= -4:
        risk += 10
    if amount_million >= 5000 and change_pct >= 3:
        risk += 8
    return min(100, risk)


def _read_by_key(path: str | Path, key: str) -> dict[str, dict[str, str]]:
    csv_path = Path(path)
    if not csv_path.exists():
        return {}
    return {row[key]: row for row in _read_csv(csv_path)}


def _read_csv(path: str | Path) -> list[dict[str, str]]:
    with Path(path).open("r", encoding="utf-8-sig", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def _number(value: str | float | int | None) -> float | None:
    if value is None:
        return None
    raw = str(value).replace(",", "").strip()
    if raw in {"", "-", "--"}:
        return None
    try:
        return float(raw)
    except ValueError:
        return None


def _fmt(value: float) -> str:
    return f"{value:.2f}".rstrip("0").rstrip(".")


def _stock_field_order() -> tuple[str, ...]:
    return (
        "symbol",
        "name",
        "sector",
        "close",
        "pullback_quality",
        "chip_cleanliness",
        "foreign_5d",
        "trust_5d",
        "margin_change_5d",
        "pe",
        "sector_pe_low",
        "sector_pe_avg",
        "sector_pe_high",
        "fair_value_low",
        "fair_value_avg",
        "fair_value_high",
        "revenue_yoy",
        "revenue_mom",
        "technical_setup",
        "liquidity",
        "risk_heat",
        "thesis",
        "risk_reason",
    )
