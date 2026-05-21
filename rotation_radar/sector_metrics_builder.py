from __future__ import annotations

import csv
from collections import defaultdict
from pathlib import Path


def build_sector_metrics_from_market_quotes(
    market_quotes_path: str | Path,
    base_sector_metrics_path: str | Path,
    output_path: str | Path,
) -> Path:
    base = _read_by_key(base_sector_metrics_path, "name")
    grouped: dict[str, list[dict[str, str]]] = defaultdict(list)
    with Path(market_quotes_path).open("r", encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            grouped[row["sector"]].append(row)

    sector_amounts = {
        sector: sum(_number(row.get("amount_million")) or 0.0 for row in rows)
        for sector, rows in grouped.items()
    }
    total_amount = sum(sector_amounts.values()) or 1.0
    max_amount = max(sector_amounts.values() or [1.0])

    output_rows: list[dict[str, str]] = []
    for sector, rows in grouped.items():
        amount = sector_amounts[sector]
        share = amount / total_amount * 100
        stock_count = len(rows)
        active_count = sum(1 for row in rows if (_number(row.get("amount_million")) or 0.0) >= 100)
        active_ratio = active_count / stock_count * 100 if stock_count else 0.0
        base_row = base.get(sector, _default_sector_row(sector))
        prev_share = _number(base_row.get("capital_share")) or 0.0
        prev_amount = _number(base_row.get("turnover_value")) or 0.0
        turnover_change_score = _change_score(amount, prev_amount)
        capital_score = amount / max_amount * 100

        output_rows.append(
            {
                "name": sector,
                "theme": base_row.get("theme") or f"{sector} 題材資金輪動",
                "capital_inflow_rank": _fmt(_clamp(capital_score)),
                "turnover_share_change": _fmt(_clamp(turnover_change_score)),
                "capital_share": _fmt(share),
                "capital_share_prev": _fmt(prev_share),
                "turnover_value": _fmt(amount),
                "turnover_value_prev": _fmt(prev_amount),
                "momentum_20d": base_row.get("momentum_20d") or "50",
                "strong_stock_ratio": _fmt(_clamp(active_ratio)),
                "industry_trend": base_row.get("industry_trend") or "50",
                "overseas_signal": base_row.get("overseas_signal") or "50",
                "pe_percentile": base_row.get("pe_percentile") or "50",
                "risk_heat": base_row.get("risk_heat") or "50",
                "catalysts": base_row.get("catalysts") or "資金占比與成交金額進入全市場排序",
                "risks": base_row.get("risks") or "需確認基本面與消息面是否同步",
            }
        )

    output_rows.sort(key=lambda row: float(row["capital_inflow_rank"]), reverse=True)
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(_sector_field_order()))
        writer.writeheader()
        writer.writerows(output_rows)
    return path


def _read_by_key(path: str | Path, key: str) -> dict[str, dict[str, str]]:
    csv_path = Path(path)
    if not csv_path.exists():
        return {}
    with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
        return {row[key]: dict(row) for row in csv.DictReader(handle)}


def _default_sector_row(sector: str) -> dict[str, str]:
    return {
        "name": sector,
        "theme": f"{sector} 題材資金輪動",
        "momentum_20d": "50",
        "industry_trend": "50",
        "overseas_signal": "50",
        "pe_percentile": "50",
        "risk_heat": "50",
    }


def _change_score(current: float, previous: float) -> float:
    if previous <= 0:
        return 55.0 if current > 0 else 50.0
    change = (current - previous) / previous * 100
    return _clamp(50 + change)


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


def _clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


def _sector_field_order() -> tuple[str, ...]:
    return (
        "name",
        "theme",
        "capital_inflow_rank",
        "turnover_share_change",
        "capital_share",
        "capital_share_prev",
        "turnover_value",
        "turnover_value_prev",
        "momentum_20d",
        "strong_stock_ratio",
        "industry_trend",
        "overseas_signal",
        "pe_percentile",
        "risk_heat",
        "catalysts",
        "risks",
    )
