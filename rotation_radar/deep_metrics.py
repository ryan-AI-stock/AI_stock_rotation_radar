from __future__ import annotations

import csv
from collections import defaultdict
from pathlib import Path


def build_hot_stock_deep_metrics(
    hot_symbols_path: str | Path,
    processed_root: str | Path,
    output_path: str | Path,
) -> Path:
    hot_rows = _read_csv(hot_symbols_path)
    hot_symbols = {row["symbol"] for row in hot_rows}
    inst_by_symbol = _load_institutional(processed_root, hot_symbols)
    margin_by_symbol = _load_margin(processed_root, hot_symbols)

    output_rows: list[dict[str, str]] = []
    for row in hot_rows:
        symbol = row["symbol"]
        inst = inst_by_symbol.get(symbol, {})
        margin = margin_by_symbol.get(symbol, {})
        output_rows.append(
            {
                "sector": row["sector"],
                "symbol": symbol,
                "name": row["name"],
                "market": row.get("market", ""),
                "price": row.get("price", ""),
                "amount_million": row.get("amount_million", ""),
                "change_pct": row.get("change_pct", ""),
                "foreign_5d": _fmt(inst.get("foreign_5d", 0.0)),
                "trust_5d": _fmt(inst.get("trust_5d", 0.0)),
                "dealer_5d": _fmt(inst.get("dealer_5d", 0.0)),
                "margin_change_5d": _fmt(margin.get("margin_change_5d", 0.0)),
                "margin_balance": _fmt(margin.get("margin_balance", 0.0)),
                "deep_data_status": _status(inst, margin),
            }
        )

    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(_field_order()))
        writer.writeheader()
        writer.writerows(output_rows)
    return path


def merge_deep_metrics_into_stock_metrics(
    stock_metrics_path: str | Path,
    deep_metrics_path: str | Path,
    output_path: str | Path,
) -> Path:
    stocks = _read_csv(stock_metrics_path)
    deep_by_symbol = _read_by_key(deep_metrics_path, "symbol")
    if not stocks:
        return Path(output_path)

    for stock in stocks:
        deep = deep_by_symbol.get(stock["symbol"])
        if not deep:
            continue
        stock["foreign_5d"] = deep["foreign_5d"]
        stock["trust_5d"] = deep["trust_5d"]
        stock["margin_change_5d"] = deep["margin_change_5d"]
        stock["chip_cleanliness"] = _fmt(_chip_score(stock))
        stock["risk_heat"] = _fmt(_risk_heat(stock))
        if deep["deep_data_status"] != "complete":
            stock["risk_reason"] = f"{stock['risk_reason']} 深度資料狀態：{deep['deep_data_status']}。"

    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(stocks[0].keys()))
        writer.writeheader()
        writer.writerows(stocks)
    return path


def _load_institutional(processed_root: str | Path, hot_symbols: set[str]) -> dict[str, dict[str, float]]:
    totals: dict[str, dict[str, float]] = defaultdict(lambda: {"foreign_5d": 0.0, "trust_5d": 0.0, "dealer_5d": 0.0})
    for path in _recent_files(processed_root, "*institutional*.csv"):
        for row in _read_csv(path):
            symbol = row.get("代號", "").strip()
            if not symbol:
                symbol = row.get("證券代號", "").strip()
            if symbol not in hot_symbols:
                continue
            totals[symbol]["foreign_5d"] += _shares_to_lots(
                _num(row.get("買賣超股數") or row.get("外陸資買賣超股數(不含外資自營商)"))
            )
            totals[symbol]["trust_5d"] += _shares_to_lots(
                _num(row.get("買賣超股數_2") or row.get("投信買賣超股數"))
            )
            totals[symbol]["dealer_5d"] += _shares_to_lots(
                _num(row.get("買賣超股數_3") or row.get("自營商買賣超股數"))
            )
    return totals


def _load_margin(processed_root: str | Path, hot_symbols: set[str]) -> dict[str, dict[str, float]]:
    by_symbol: dict[str, list[tuple[str, float, float]]] = defaultdict(list)
    for path in _recent_files(processed_root, "*margin*.csv"):
        trade_date = path.parent.name
        for row in _read_csv(path):
            symbol = row.get("代號", "").strip()
            if not symbol:
                symbol = row.get("股票代號", "").strip()
            if symbol not in hot_symbols:
                continue
            prev_balance = _num(row.get("前資餘額(張)") or row.get("融資前日餘額") or row.get("前日餘額"))
            balance = _num(row.get("資餘額") or row.get("融資今日餘額") or row.get("今日餘額"))
            by_symbol[symbol].append((trade_date, prev_balance, balance))

    result: dict[str, dict[str, float]] = {}
    for symbol, rows in by_symbol.items():
        rows.sort(key=lambda item: item[0])
        first_prev = rows[0][1] or rows[0][2]
        latest = rows[-1][2]
        change = (latest - first_prev) / first_prev * 100 if first_prev else 0.0
        result[symbol] = {"margin_change_5d": change, "margin_balance": latest}
    return result


def _recent_files(processed_root: str | Path, pattern: str) -> list[Path]:
    root = Path(processed_root)
    if not root.exists():
        return []
    folders = sorted((path for path in root.iterdir() if path.is_dir()), reverse=True)[:5]
    files: list[Path] = []
    for folder in folders:
        files.extend(sorted(folder.glob(pattern)))
    return files


def _chip_score(stock: dict[str, str]) -> float:
    foreign = _num(stock.get("foreign_5d"))
    trust = _num(stock.get("trust_5d"))
    margin = _num(stock.get("margin_change_5d"))
    score = 52.0
    if foreign > 0:
        score += 8
    if trust > 0:
        score += 12
    if foreign > 0 and trust > 0:
        score += 8
    if margin < 0:
        score += 8
    elif margin <= 5:
        score += 4
    elif margin > 12:
        score -= 14
    return max(0.0, min(100.0, score))


def _risk_heat(stock: dict[str, str]) -> float:
    margin = _num(stock.get("margin_change_5d"))
    technical = _num(stock.get("technical_setup"))
    risk = 45.0
    if margin > 12:
        risk += 16
    elif margin > 5:
        risk += 7
    if technical >= 78:
        risk += 8
    return max(0.0, min(100.0, risk))


def _status(inst: dict[str, float], margin: dict[str, float]) -> str:
    if inst and margin:
        return "complete"
    if inst:
        return "missing_margin"
    if margin:
        return "missing_institutional"
    return "missing_deep_data"


def _read_by_key(path: str | Path, key: str) -> dict[str, dict[str, str]]:
    return {row[key]: row for row in _read_csv(path)}


def _read_csv(path: str | Path) -> list[dict[str, str]]:
    with Path(path).open("r", encoding="utf-8-sig", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def _num(value: str | float | int | None) -> float:
    if value is None:
        return 0.0
    raw = str(value).replace(",", "").strip()
    if raw in {"", "-", "--"}:
        return 0.0
    try:
        return float(raw)
    except ValueError:
        return 0.0


def _shares_to_lots(value: float) -> float:
    return value / 1000


def _fmt(value: float) -> str:
    return f"{value:.2f}".rstrip("0").rstrip(".")


def _field_order() -> tuple[str, ...]:
    return (
        "sector",
        "symbol",
        "name",
        "market",
        "price",
        "amount_million",
        "change_pct",
        "foreign_5d",
        "trust_5d",
        "dealer_5d",
        "margin_change_5d",
        "margin_balance",
        "deep_data_status",
    )
