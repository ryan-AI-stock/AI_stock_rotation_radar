from __future__ import annotations

import csv
import json
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlencode

from rotation_radar.public_sources import SourceFetchError, fetch_public_json


TURNOVER_FIELDS = [
    "symbol",
    "date",
    "official_turnover_value",
    "exchange",
    "source",
    "source_url",
    "ingested_at",
]

GAP_FIELDS = [
    "symbol",
    "date",
    "exchange",
    "missing_reason",
    "source_url",
    "checked_at",
]


@dataclass(frozen=True)
class SymbolExchange:
    symbol: str
    exchange: str


@dataclass(frozen=True)
class OfficialTurnoverBuildResult:
    turnover_path: Path
    gap_report_path: Path
    readiness_path: Path
    readiness: dict[str, Any]


JsonFetcher = Callable[[str], dict[str, Any]]


def build_official_turnover_dataset(
    *,
    formal_universe_path: str | Path,
    market_universe_path: str | Path,
    output_path: str | Path,
    gap_report_path: str | Path,
    readiness_output_path: str | Path,
    start_date: str,
    end_date: str,
    raw_cache_dir: str | Path | None = None,
    force_fetch: bool = False,
    sleep_seconds: float = 0.0,
    retry_attempts: int = 3,
    retry_sleep_seconds: float = 1.0,
    fetcher: JsonFetcher | None = None,
    progress_every: int = 50,
) -> OfficialTurnoverBuildResult:
    start = _parse_iso_date(start_date)
    end = _parse_iso_date(end_date)
    if end < start:
        raise ValueError("end_date must be on or after start_date")

    symbols = load_formal_universe_symbols(formal_universe_path, market_universe_path)
    fetch_json = fetcher or fetch_public_json
    cache_root = Path(raw_cache_dir) if raw_cache_dir else None
    months = _month_starts(start, end)
    ingested_at = _utc_now_iso()
    checked_at = ingested_at

    turnover_rows: list[dict[str, str]] = []
    fetch_errors: list[dict[str, str]] = []
    source_urls_by_exchange: dict[str, set[str]] = {"TWSE": set(), "TPEx": set()}

    total_requests = len(symbols) * len(months)
    request_count = 0
    for symbol_info in symbols:
        for month_start in months:
            request_count += 1
            source_url = build_source_url(symbol_info.exchange, symbol_info.symbol, month_start)
            source_urls_by_exchange[symbol_info.exchange].add(source_url)
            try:
                payload = _fetch_month_payload(
                    source_url=source_url,
                    cache_root=cache_root,
                    exchange=symbol_info.exchange,
                    symbol=symbol_info.symbol,
                    month_start=month_start,
                    force_fetch=force_fetch,
                    fetcher=fetch_json,
                    retry_attempts=retry_attempts,
                    retry_sleep_seconds=retry_sleep_seconds,
                )
                rows = parse_month_payload(
                    payload=payload,
                    exchange=symbol_info.exchange,
                    symbol=symbol_info.symbol,
                    source_url=source_url,
                    ingested_at=ingested_at,
                    start=start,
                    end=end,
                )
                turnover_rows.extend(rows)
            except (SourceFetchError, ValueError, KeyError, TypeError) as exc:
                fetch_errors.append(
                    {
                        "symbol": symbol_info.symbol,
                        "exchange": symbol_info.exchange,
                        "month": month_start.strftime("%Y-%m"),
                        "source_url": source_url,
                        "error": str(exc),
                    }
                )
            if sleep_seconds > 0:
                time.sleep(sleep_seconds)
            if progress_every > 0 and request_count % progress_every == 0:
                print(f"Fetched official turnover source {request_count}/{total_requests}", flush=True)

    turnover_rows = _dedupe_and_sort_turnover_rows(turnover_rows)
    gap_rows = build_gap_rows(
        symbols=symbols,
        turnover_rows=turnover_rows,
        fetch_errors=fetch_errors,
        source_urls_by_exchange=source_urls_by_exchange,
        start=start,
        end=end,
        checked_at=checked_at,
    )
    readiness = build_readiness(
        symbols=symbols,
        turnover_rows=turnover_rows,
        gap_rows=gap_rows,
        start=start,
        end=end,
        fetch_errors=fetch_errors,
    )

    output = Path(output_path)
    gap_output = Path(gap_report_path)
    readiness_output = Path(readiness_output_path)
    _write_rows(output, TURNOVER_FIELDS, turnover_rows)
    _write_rows(gap_output, GAP_FIELDS, gap_rows)
    _write_json(readiness_output, readiness)

    return OfficialTurnoverBuildResult(
        turnover_path=output,
        gap_report_path=gap_output,
        readiness_path=readiness_output,
        readiness=readiness,
    )


def validate_official_turnover(
    *,
    turnover_file: str | Path,
    formal_universe_path: str | Path,
    market_universe_path: str | Path,
    start_date: str,
    end_date: str,
    output_path: str | Path,
    gap_report_path: str | Path | None = None,
) -> dict[str, Any]:
    start = _parse_iso_date(start_date)
    end = _parse_iso_date(end_date)
    symbols = load_formal_universe_symbols(formal_universe_path, market_universe_path)
    turnover_rows = _read_turnover_rows(Path(turnover_file), start, end)
    checked_at = _utc_now_iso()
    source_urls_by_exchange = _source_urls_from_turnover(turnover_rows)
    gap_rows = build_gap_rows(
        symbols=symbols,
        turnover_rows=turnover_rows,
        fetch_errors=[],
        source_urls_by_exchange=source_urls_by_exchange,
        start=start,
        end=end,
        checked_at=checked_at,
    )
    readiness = build_readiness(
        symbols=symbols,
        turnover_rows=turnover_rows,
        gap_rows=gap_rows,
        start=start,
        end=end,
        fetch_errors=[],
    )
    _write_json(Path(output_path), readiness)
    if gap_report_path:
        _write_rows(Path(gap_report_path), GAP_FIELDS, gap_rows)
    return readiness


def load_formal_universe_symbols(
    formal_universe_path: str | Path,
    market_universe_path: str | Path,
) -> list[SymbolExchange]:
    market_by_symbol: dict[str, str] = {}
    with Path(market_universe_path).open("r", encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            symbol = str(row.get("symbol", "")).strip()
            market = str(row.get("market", "")).strip()
            if symbol and market in {"TWSE", "TPEx"}:
                market_by_symbol[symbol] = market

    output: list[SymbolExchange] = []
    with Path(formal_universe_path).open("r", encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            symbol = str(row.get("symbol", "")).strip()
            if not symbol:
                continue
            exchange = market_by_symbol.get(symbol, "")
            if not exchange:
                exchange = "UNKNOWN"
            output.append(SymbolExchange(symbol=symbol, exchange=exchange))
    return sorted(output, key=lambda item: item.symbol)


def build_source_url(exchange: str, symbol: str, month_start: date) -> str:
    if exchange == "TWSE":
        return _url(
            "https://www.twse.com.tw/rwd/zh/afterTrading/STOCK_DAY",
            date=month_start.strftime("%Y%m%d"),
            stockNo=symbol,
            response="json",
        )
    if exchange == "TPEx":
        return _url(
            "https://www.tpex.org.tw/www/zh-tw/afterTrading/tradingStock",
            code=symbol,
            date=month_start.strftime("%Y/%m/%d"),
            response="json",
        )
    raise ValueError(f"Unsupported exchange: {exchange}")


def parse_month_payload(
    *,
    payload: dict[str, Any],
    exchange: str,
    symbol: str,
    source_url: str,
    ingested_at: str,
    start: date,
    end: date,
) -> list[dict[str, str]]:
    if exchange == "TWSE":
        rows = payload.get("data", [])
        fields = payload.get("fields", [])
        if payload.get("stat") != "OK":
            return []
        date_index = _field_index(fields, "日期")
        turnover_index = _field_index(fields, "成交金額")
        source = "twse_stock_day"
        multiplier = 1
    elif exchange == "TPEx":
        table = _first_table(payload)
        rows = table.get("data", [])
        fields = table.get("fields", [])
        if payload.get("stat") not in {"ok", "OK"}:
            return []
        date_index = _field_index(fields, "日 期")
        turnover_index = _field_index(fields, "成交仟元")
        source = "tpex_trading_stock"
        multiplier = 1000
    else:
        raise ValueError(f"Unsupported exchange: {exchange}")

    output: list[dict[str, str]] = []
    for raw_row in rows:
        if not isinstance(raw_row, list):
            continue
        if max(date_index, turnover_index) >= len(raw_row):
            continue
        trade_date = _parse_roc_date(str(raw_row[date_index]))
        if trade_date < start or trade_date > end:
            continue
        turnover_value = _parse_int(str(raw_row[turnover_index])) * multiplier
        if turnover_value <= 0:
            continue
        output.append(
            {
                "symbol": symbol,
                "date": trade_date.isoformat(),
                "official_turnover_value": str(turnover_value),
                "exchange": exchange,
                "source": source,
                "source_url": source_url,
                "ingested_at": ingested_at,
            }
        )
    return output


def build_gap_rows(
    *,
    symbols: list[SymbolExchange],
    turnover_rows: list[dict[str, str]],
    fetch_errors: list[dict[str, str]],
    source_urls_by_exchange: dict[str, set[str]],
    start: date,
    end: date,
    checked_at: str,
) -> list[dict[str, str]]:
    rows_by_symbol_date = {(row["symbol"], row["date"]) for row in turnover_rows}
    trading_dates_by_exchange: dict[str, set[str]] = {"TWSE": set(), "TPEx": set()}
    for row in turnover_rows:
        trading_dates_by_exchange.setdefault(row["exchange"], set()).add(row["date"])

    output: list[dict[str, str]] = []
    by_exchange: dict[str, list[str]] = {}
    for item in symbols:
        by_exchange.setdefault(item.exchange, []).append(item.symbol)

    for item in symbols:
        if item.exchange not in {"TWSE", "TPEx"}:
            output.append(
                _gap_row(
                    symbol=item.symbol,
                    day=start,
                    exchange=item.exchange,
                    reason="unknown_exchange_mapping",
                    source_url="",
                    checked_at=checked_at,
                )
            )

    for exchange in ("TWSE", "TPEx"):
        exchange_symbols = by_exchange.get(exchange, [])
        trading_dates = trading_dates_by_exchange.get(exchange, set())
        source_url = _sample_source_url(source_urls_by_exchange.get(exchange, set()))
        for symbol in exchange_symbols:
            for trade_date in sorted(trading_dates):
                if (symbol, trade_date) not in rows_by_symbol_date:
                    output.append(
                        {
                            "symbol": symbol,
                            "date": trade_date,
                            "exchange": exchange,
                            "missing_reason": "missing_official_turnover_on_exchange_trading_day",
                            "source_url": source_url,
                            "checked_at": checked_at,
                        }
                    )

        for closed_day in _non_trading_days(start, end, trading_dates):
            for symbol in exchange_symbols:
                output.append(
                    _gap_row(
                        symbol=symbol,
                        day=closed_day,
                        exchange=exchange,
                        reason="market_closed_or_no_official_rows",
                        source_url=source_url,
                        checked_at=checked_at,
                    )
                )

    for error in fetch_errors:
        output.append(
            {
                "symbol": error.get("symbol", ""),
                "date": f"{error.get('month', '')}-01",
                "exchange": error.get("exchange", ""),
                "missing_reason": f"source_fetch_or_parse_failed: {error.get('error', '')}",
                "source_url": error.get("source_url", ""),
                "checked_at": checked_at,
            }
        )

    return sorted(output, key=lambda row: (row["exchange"], row["symbol"], row["date"], row["missing_reason"]))


def build_readiness(
    *,
    symbols: list[SymbolExchange],
    turnover_rows: list[dict[str, str]],
    gap_rows: list[dict[str, str]],
    start: date,
    end: date,
    fetch_errors: list[dict[str, str]],
) -> dict[str, Any]:
    symbol_counts = {
        "TWSE": sum(1 for item in symbols if item.exchange == "TWSE"),
        "TPEx": sum(1 for item in symbols if item.exchange == "TPEx"),
        "UNKNOWN": sum(1 for item in symbols if item.exchange not in {"TWSE", "TPEx"}),
    }
    trading_dates_by_exchange: dict[str, set[str]] = {"TWSE": set(), "TPEx": set()}
    for row in turnover_rows:
        trading_dates_by_exchange.setdefault(row["exchange"], set()).add(row["date"])

    expected = (
        symbol_counts["TWSE"] * len(trading_dates_by_exchange.get("TWSE", set()))
        + symbol_counts["TPEx"] * len(trading_dates_by_exchange.get("TPEx", set()))
    )
    blocking_gap_reasons = {"unknown_exchange_mapping"}
    blocking_gap_count = sum(1 for row in gap_rows if row["missing_reason"] in blocking_gap_reasons)
    no_trade_gap_count = sum(
        1 for row in gap_rows if row["missing_reason"] == "missing_official_turnover_on_exchange_trading_day"
    )
    missing_count = blocking_gap_count + no_trade_gap_count + len(fetch_errors)
    coverage_ratio = (len(turnover_rows) / expected) if expected else 0.0
    ready = (
        expected > 0
        and blocking_gap_count == 0
        and len(fetch_errors) == 0
        and coverage_ratio >= 0.99
        and symbol_counts["UNKNOWN"] == 0
    )
    source_mode = "official_exchange_turnover" if ready else "official_partial_with_gap_report"
    if ready and no_trade_gap_count:
        source_mode = "official_partial_with_gap_report"

    blocking_issues: list[str] = []
    if expected == 0:
        blocking_issues.append("No exchange trading dates were detected from official source rows.")
    if symbol_counts["UNKNOWN"]:
        blocking_issues.append(f"{symbol_counts['UNKNOWN']} formal-universe symbols have unknown exchange mapping.")
    if fetch_errors:
        blocking_issues.append(f"{len(fetch_errors)} source fetch/parse errors occurred.")
    if blocking_gap_count:
        blocking_issues.append(f"{blocking_gap_count} symbol-date turnover rows are blocked by exchange mapping issues.")

    return {
        "ready": ready,
        "date_start": start.isoformat(),
        "date_end": end.isoformat(),
        "formal_universe_symbol_count": len(symbols),
        "expected_symbol_date_count": expected,
        "official_turnover_row_count": len(turnover_rows),
        "coverage_ratio": round(coverage_ratio, 8),
        "missing_count": missing_count,
        "missing_official_turnover_on_exchange_trading_day_count": no_trade_gap_count,
        "twse_symbol_count": symbol_counts["TWSE"],
        "tpex_symbol_count": symbol_counts["TPEx"],
        "twse_trading_date_count": len(trading_dates_by_exchange.get("TWSE", set())),
        "tpex_trading_date_count": len(trading_dates_by_exchange.get("TPEx", set())),
        "non_trading_gap_row_count": sum(
            1 for row in gap_rows if row["missing_reason"] == "market_closed_or_no_official_rows"
        ),
        "source_mode": source_mode,
        "blocking_issues": blocking_issues,
        "non_blocking_issues": (
            [f"{no_trade_gap_count} official source symbol-date rows were absent and are listed in the gap report."]
            if no_trade_gap_count
            else []
        ),
    }


def _fetch_month_payload(
    *,
    source_url: str,
    cache_root: Path | None,
    exchange: str,
    symbol: str,
    month_start: date,
    force_fetch: bool,
    fetcher: JsonFetcher,
    retry_attempts: int,
    retry_sleep_seconds: float,
) -> dict[str, Any]:
    cache_path = None
    if cache_root:
        cache_path = cache_root / exchange / symbol / f"{month_start.strftime('%Y%m')}.json"
        if cache_path.exists() and not force_fetch:
            return json.loads(cache_path.read_text(encoding="utf-8"))
    attempts = max(1, retry_attempts)
    last_error: SourceFetchError | None = None
    for attempt in range(1, attempts + 1):
        try:
            payload = fetcher(source_url)
            break
        except SourceFetchError as exc:
            last_error = exc
            if attempt < attempts and retry_sleep_seconds > 0:
                time.sleep(retry_sleep_seconds * attempt)
    else:
        assert last_error is not None
        raise last_error
    if cache_path:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return payload


def _read_turnover_rows(path: Path, start: date, end: date) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = [
            {key: (value or "").strip() for key, value in row.items()}
            for row in csv.DictReader(handle)
        ]
    output: list[dict[str, str]] = []
    for row in rows:
        trade_date = _parse_iso_date(row["date"])
        if start <= trade_date <= end:
            output.append(row)
    return _dedupe_and_sort_turnover_rows(output)


def _source_urls_from_turnover(rows: list[dict[str, str]]) -> dict[str, set[str]]:
    output: dict[str, set[str]] = {"TWSE": set(), "TPEx": set()}
    for row in rows:
        output.setdefault(row.get("exchange", ""), set()).add(row.get("source_url", ""))
    return output


def _dedupe_and_sort_turnover_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    by_key: dict[tuple[str, str], dict[str, str]] = {}
    for row in rows:
        key = (row["symbol"], row["date"])
        by_key[key] = row
    return sorted(by_key.values(), key=lambda row: (row["exchange"], row["symbol"], row["date"]))


def _non_trading_days(start: date, end: date, trading_dates: set[str]) -> list[date]:
    output: list[date] = []
    current = start
    while current <= end:
        if current.isoformat() not in trading_dates:
            output.append(current)
        current += timedelta(days=1)
    return output


def _gap_row(
    *,
    symbol: str,
    day: date,
    exchange: str,
    reason: str,
    source_url: str,
    checked_at: str,
) -> dict[str, str]:
    return {
        "symbol": symbol,
        "date": day.isoformat(),
        "exchange": exchange,
        "missing_reason": reason,
        "source_url": source_url,
        "checked_at": checked_at,
    }


def _sample_source_url(urls: set[str]) -> str:
    return sorted(urls)[0] if urls else ""


def _first_table(payload: dict[str, Any]) -> dict[str, Any]:
    tables = payload.get("tables", [])
    if not tables:
        raise ValueError("TPEx payload missing tables")
    table = tables[0]
    if not isinstance(table, dict):
        raise ValueError("TPEx first table is not an object")
    return table


def _field_index(fields: list[Any], target: str) -> int:
    normalized = [_normalize_field(str(field)) for field in fields]
    try:
        return normalized.index(_normalize_field(target))
    except ValueError as exc:
        raise ValueError(f"Missing field {target}") from exc


def _normalize_field(value: str) -> str:
    return value.replace(" ", "").strip()


def _parse_roc_date(value: str) -> date:
    parts = value.strip().split("/")
    if len(parts) != 3:
        raise ValueError(f"Invalid ROC date: {value}")
    year = int(parts[0]) + 1911
    return date(year, int(parts[1]), int(parts[2]))


def _parse_iso_date(value: str) -> date:
    return datetime.strptime(value, "%Y-%m-%d").date()


def _parse_int(value: str) -> int:
    stripped = value.replace(",", "").replace("--", "").strip()
    if not stripped:
        return 0
    return int(float(stripped))


def _month_starts(start: date, end: date) -> list[date]:
    output: list[date] = []
    current = date(start.year, start.month, 1)
    while current <= end:
        output.append(current)
        if current.month == 12:
            current = date(current.year + 1, 1, 1)
        else:
            current = date(current.year, current.month + 1, 1)
    return output


def _url(base: str, **query: str) -> str:
    return f"{base}?{urlencode(query)}"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _write_rows(path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
