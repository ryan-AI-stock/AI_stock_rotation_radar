from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen


TWSE_BWIBBU_URL = "https://www.twse.com.tw/rwd/zh/afterTrading/BWIBBU_d"
TPEX_PER_URL = "https://www.tpex.org.tw/openapi/v1/tpex_mainboard_peratio_analysis"


@dataclass(frozen=True)
class ValuationBackfillResult:
    output_path: Path
    filled_pe_count: int
    missing_pe_symbols: tuple[str, ...]
    warnings: tuple[str, ...]


def backfill_stock_valuations(
    stock_metrics_path: str | Path,
    market_quotes_path: str | Path,
    output_path: str | Path,
    *,
    report_date: str | None = None,
) -> ValuationBackfillResult:
    """Fill missing candidate PE data from exchange-published valuation tables.

    The daily quote API does not include PE ratios. Candidates that are not in
    the curated stock_metrics.csv therefore need a second public-data pass
    before report rendering.
    """

    rows = _read_csv(stock_metrics_path)
    market_by_symbol = _load_market_by_symbol(market_quotes_path)
    missing_symbols = sorted(
        {
            row["symbol"]
            for row in rows
            if _num_or_none(row.get("pe")) in (None, 0) and row["symbol"] in market_by_symbol
        }
    )
    warnings: list[str] = []
    valuation_by_symbol: dict[str, float] = {}
    if missing_symbols:
        try:
            valuation_by_symbol = fetch_exchange_pe_ratios(
                market_by_symbol=market_by_symbol,
                report_date=report_date,
            )
        except OSError as exc:
            warnings.append(f"failed to fetch exchange valuation data: {exc}")

    filled = 0
    for row in rows:
        symbol = row["symbol"]
        current_pe = _num_or_none(row.get("pe"))
        if current_pe not in (None, 0):
            continue
        pe = valuation_by_symbol.get(symbol)
        if pe is None or pe <= 0:
            continue
        row["pe"] = _fmt(pe)
        row["risk_reason"] = _clean_valuation_missing_text(row.get("risk_reason", ""))
        filled += 1

    _refresh_sector_pe_ranges(rows)
    for row in rows:
        _refresh_fair_value(row)

    still_missing = tuple(
        sorted(
            row["symbol"]
            for row in rows
            if _num_or_none(row.get("pe")) in (None, 0)
        )
    )

    path = Path(output_path)
    _write_csv(path, rows)
    return ValuationBackfillResult(
        output_path=path,
        filled_pe_count=filled,
        missing_pe_symbols=still_missing,
        warnings=tuple(warnings),
    )


def fetch_exchange_pe_ratios(
    *,
    market_by_symbol: dict[str, str],
    report_date: str | None = None,
) -> dict[str, float]:
    result: dict[str, float] = {}
    if any(market == "TWSE" for market in market_by_symbol.values()):
        result.update(_fetch_twse_pe(report_date))
    if any(market == "TPEx" for market in market_by_symbol.values()):
        result.update(_fetch_tpex_pe())
    return result


def _fetch_twse_pe(report_date: str | None) -> dict[str, float]:
    params = {"response": "json", "selectType": "ALL"}
    parsed_date = _compact_date(report_date)
    if parsed_date:
        params["date"] = parsed_date
    payload = _fetch_json(f"{TWSE_BWIBBU_URL}?{urlencode(params)}")
    rows = payload.get("data") or payload.get("tables", [{}])[0].get("data", [])
    fields = payload.get("fields") or payload.get("tables", [{}])[0].get("fields", [])
    output: dict[str, float] = {}
    for item in rows:
        row = dict(zip(fields, item)) if isinstance(item, list) else item
        symbol = _first_text(row, ("證券代號", "Code", "code", "股票代號"))
        pe = _first_number(row, ("本益比", "PER", "PEratio", "PriceEarningRatio"))
        if symbol and pe is not None and pe > 0:
            output[symbol] = pe
    return output


def _fetch_tpex_pe() -> dict[str, float]:
    payload = _fetch_json(TPEX_PER_URL)
    rows = payload if isinstance(payload, list) else payload.get("data", [])
    output: dict[str, float] = {}
    for row in rows:
        symbol = _first_text(
            row,
            (
                "SecuritiesCompanyCode",
                "Code",
                "股票代號",
                "證券代號",
                "代號",
            ),
        )
        pe = _first_number(
            row,
            (
                "PriceEarningRatio",
                "PER",
                "PEratio",
                "本益比",
                "本益比(倍)",
            ),
        )
        if symbol and pe is not None and pe > 0:
            output[symbol] = pe
    return output


def _fetch_json(url: str):
    request = Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 AI_stock_rotation_radar/0.1",
            "Accept": "application/json,text/plain,*/*",
        },
    )
    with urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8-sig"))


def _refresh_sector_pe_ranges(rows: list[dict[str, str]]) -> None:
    by_sector: dict[str, list[float]] = {}
    for row in rows:
        pe = _num_or_none(row.get("pe"))
        if pe is not None and pe > 0:
            by_sector.setdefault(row.get("sector", ""), []).append(pe)

    for row in rows:
        peers = by_sector.get(row.get("sector", ""), [])
        if not peers:
            continue
        row["sector_pe_low"] = _fmt(min(peers))
        row["sector_pe_avg"] = _fmt(sum(peers) / len(peers))
        row["sector_pe_high"] = _fmt(max(peers))


def _refresh_fair_value(row: dict[str, str]) -> None:
    close = _num_or_none(row.get("close"))
    pe = _num_or_none(row.get("pe"))
    if close is None or pe in (None, 0):
        return
    eps = close / pe
    for suffix, key in (("low", "sector_pe_low"), ("avg", "sector_pe_avg"), ("high", "sector_pe_high")):
        sector_pe = _num_or_none(row.get(key))
        if sector_pe is not None and sector_pe > 0:
            row[f"fair_value_{suffix}"] = _fmt(eps * sector_pe)


def _load_market_by_symbol(path: str | Path) -> dict[str, str]:
    output: dict[str, str] = {}
    for row in _read_csv(path):
        symbol = row.get("symbol", "").strip()
        market = row.get("market", "").strip()
        if symbol and market:
            output[symbol] = market
    return output


def _clean_valuation_missing_text(value: str) -> str:
    cleaned = value.replace("本益比、法人籌碼與融資資料尚未接入全市場資料源，", "法人籌碼與融資資料尚未完整接入，")
    cleaned = cleaned.replace("本益比、法人籌碼與融資資料尚未接入全市場資料源", "法人籌碼與融資資料尚未完整接入")
    cleaned = cleaned.replace("估值資料待補", "")
    return " ".join(cleaned.split()) or "法人籌碼與融資資料仍需追蹤。"


def _compact_date(value: str | None) -> str:
    if not value:
        return ""
    raw = value.strip()
    if len(raw) == 8 and raw.isdigit():
        return raw
    try:
        return date.fromisoformat(raw).strftime("%Y%m%d")
    except ValueError:
        return ""


def _first_text(row: dict[str, object], keys: tuple[str, ...]) -> str:
    for key in keys:
        value = row.get(key)
        if value is not None:
            return str(value).strip()
    return ""


def _first_number(row: dict[str, object], keys: tuple[str, ...]) -> float | None:
    for key in keys:
        value = _num_or_none(row.get(key))
        if value is not None:
            return value
    return None


def _read_csv(path: str | Path) -> list[dict[str, str]]:
    with Path(path).open("r", encoding="utf-8-sig", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle)]


def _write_csv(path: Path, rows: list[dict[str, str]]) -> None:
    if not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def _num_or_none(value: object) -> float | None:
    if value is None:
        return None
    raw = str(value).replace(",", "").strip()
    if raw in {"", "-", "--", "N/A", "NA"}:
        return None
    try:
        return float(raw)
    except ValueError:
        return None


def _fmt(value: float) -> str:
    return f"{value:.2f}".rstrip("0").rstrip(".")
