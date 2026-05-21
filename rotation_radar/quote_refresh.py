from __future__ import annotations

import csv
import json
import shutil
from pathlib import Path
from urllib.parse import quote
from urllib.request import Request, urlopen


MIS_URL = "https://mis.twse.com.tw/stock/api/getStockInfo.jsp"


def refresh_stock_metrics_quotes(
    stock_metrics_path: str | Path,
    sector_map_path: str | Path,
    output_path: str | Path,
) -> Path:
    stocks = _read_csv(stock_metrics_path)
    market_by_symbol = _load_market_by_symbol(sector_map_path)
    quote_targets: list[tuple[str, str]] = []
    for row in stocks:
        market = market_by_symbol.get(row["symbol"])
        if market:
            quote_targets.append((row["symbol"], market))
        else:
            quote_targets.extend([(row["symbol"], "TWSE"), (row["symbol"], "TPEx")])
    output = Path(output_path)
    try:
        quotes = fetch_quotes(quote_targets)
    except OSError as exc:
        if output.exists():
            print(f"Warning: failed to refresh stock quotes; using existing {output}: {exc}")
            return output
        print(f"Warning: failed to refresh stock quotes; copying base metrics without quote refresh: {exc}")
        shutil.copyfile(stock_metrics_path, output)
        return output

    for row in stocks:
        quote_row = quotes.get(row["symbol"])
        if not quote_row:
            continue
        latest_price = quote_row.get("price")
        if latest_price is not None:
            _refresh_pe_and_fair_value(row, latest_price)
            row["close"] = _format_number(latest_price)

    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(stocks[0].keys()))
        writer.writeheader()
        writer.writerows(stocks)
    return output


def refresh_market_quotes(
    sector_map_path: str | Path,
    output_path: str | Path = "data/market_quotes.generated.csv",
) -> Path:
    path = Path(output_path)
    sector_rows = _read_csv(sector_map_path)
    targets = [(row["symbol"], row.get("market", "TWSE")) for row in sector_rows]
    try:
        quotes = fetch_quotes(targets)
    except OSError as exc:
        if path.exists():
            print(f"Warning: failed to refresh market quotes; using existing {path}: {exc}")
            return path
        raise

    output_rows: list[dict[str, str]] = []
    for row in sector_rows:
        quote_row = quotes.get(row["symbol"])
        if not quote_row:
            continue
        price = _number(quote_row.get("price")) or 0.0
        volume_lots = _number(quote_row.get("volume_lots")) or 0.0
        previous_close = _number(quote_row.get("previous_close")) or 0.0
        change_pct = (price - previous_close) / previous_close * 100 if previous_close else 0.0
        output_rows.append(
            {
                "sector": row["sector"],
                "symbol": row["symbol"],
                "name": row["name"],
                "market": row.get("market", ""),
                "price": _format_number(price),
                "previous_close": _format_number(previous_close),
                "change_pct": _format_number(change_pct),
                "open": _format_number(_number(quote_row.get("open")) or 0.0),
                "high": _format_number(_number(quote_row.get("high")) or 0.0),
                "low": _format_number(_number(quote_row.get("low")) or 0.0),
                "volume_lots": _format_number(volume_lots),
                "amount_million": _format_number(price * volume_lots / 1000),
                "quote_date": str(quote_row.get("date", "")),
                "quote_time": str(quote_row.get("time", "")),
            }
        )

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
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
            ],
        )
        writer.writeheader()
        writer.writerows(output_rows)
    return path


def fetch_quotes(symbols: list[tuple[str, str]], batch_size: int = 80) -> dict[str, dict[str, float | str]]:
    result: dict[str, dict[str, float | str]] = {}
    for start in range(0, len(symbols), batch_size):
        batch = symbols[start : start + batch_size]
        ex_ch = "|".join(_ex_ch(symbol, market) for symbol, market in batch)
        url = f"{MIS_URL}?ex_ch={quote(ex_ch, safe='|')}&json=1&delay=0"
        request = Request(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 AI_stock_rotation_radar/0.1",
                "Referer": "https://mis.twse.com.tw/stock/index.jsp",
            },
        )
        with urlopen(request, timeout=30) as response:
            payload = json.loads(response.read().decode("utf-8-sig"))
        for item in payload.get("msgArray", []):
            symbol = str(item.get("c", "")).strip()
            price = _number(item.get("z")) or _number(item.get("pz")) or _number(item.get("y"))
            if not symbol or price is None:
                continue
            result[symbol] = {
                "price": price,
                "name": str(item.get("n", "")),
                "volume_lots": _number(item.get("v")) or 0.0,
                "previous_close": _number(item.get("y")) or 0.0,
                "open": _number(item.get("o")) or 0.0,
                "high": _number(item.get("h")) or 0.0,
                "low": _number(item.get("l")) or 0.0,
                "time": str(item.get("t") or item.get("%") or ""),
                "date": str(item.get("d") or item.get("^") or ""),
            }
    return result


def _load_market_by_symbol(path: str | Path) -> dict[str, str]:
    csv_path = Path(path)
    if not csv_path.exists():
        return {}
    result: dict[str, str] = {}
    for row in _read_csv(csv_path):
        symbol = row.get("symbol", "")
        market = row.get("market", "")
        if symbol and market:
            result[symbol] = market
    return result


def _refresh_pe_and_fair_value(row: dict[str, str], latest_price: float) -> None:
    previous_close = _number(row.get("close"))
    previous_pe = _number(row.get("pe"))
    if previous_close in (None, 0) or previous_pe in (None, 0):
        return
    eps = previous_close / previous_pe
    if eps <= 0:
        return
    row["pe"] = _format_number(latest_price / eps)
    for suffix, pe_key in (
        ("low", "sector_pe_low"),
        ("avg", "sector_pe_avg"),
        ("high", "sector_pe_high"),
    ):
        sector_pe = _number(row.get(pe_key))
        if sector_pe is not None:
            row[f"fair_value_{suffix}"] = _format_number(eps * sector_pe)


def _ex_ch(symbol: str, market: str) -> str:
    prefix = "otc" if market in {"TPEx", "OTC"} else "tse"
    return f"{prefix}_{symbol}.tw"


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


def _format_number(value: float) -> str:
    return f"{value:.2f}".rstrip("0").rstrip(".")
