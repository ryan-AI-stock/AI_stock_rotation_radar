from __future__ import annotations

import csv
import json
import time
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlencode

from rotation_radar.formal_sources.chip_flow_overlay import TARGET_UNIVERSE
from rotation_radar.formal_sources.institutional_flows import load_twse_trading_dates
from rotation_radar.public_sources import SourceFetchError, fetch_public_json


DAY_TRADING_FIELDS = [
    "date",
    "symbol",
    "ticker",
    "name",
    "day_trading_buy_volume",
    "day_trading_sell_volume",
    "day_trading_total_volume",
    "total_trading_volume",
    "day_trading_volume_ratio",
    "day_trading_ratio_5d_avg",
    "day_trading_ratio_20d_avg",
    "day_trading_ratio_5d_change",
    "day_trading_ratio_20d_change",
    "day_trading_overheat_flag",
    "data_source",
    "source_url",
    "data_quality_status",
]

GAP_FIELDS = [
    "symbol",
    "ticker",
    "name",
    "date",
    "missing_reason",
    "source_url",
    "blocking",
    "checked_at",
]

REQUIRED_READINESS_FIELDS = [
    "ready",
    "source_mode",
    "start_date",
    "end_date",
    "target_symbol_count",
    "covered_symbol_count",
    "trading_day_count",
    "expected_symbol_date_count",
    "day_trading_row_count",
    "coverage_ratio",
    "stock_coverage_ratio",
    "etf_gap_count",
    "stock_gap_count",
    "future_data_violation_count",
    "blocking_issues",
    "warnings",
]

ETF_SYMBOLS = {"0050", "00631L"}
DATA_SOURCE = "twse_twtb4u_day_trading_stock_day_volume"
DATA_QUALITY_STATUS = "official_twse_twtb4u_total_volume_only_stock_day_denominator_buy_sell_volume_unavailable"


@dataclass(frozen=True)
class DayTradingBuildResult:
    output_path: Path
    gap_report_path: Path
    readiness_path: Path
    readiness: dict[str, object]


JsonFetcher = Callable[[str], dict[str, Any]]


def build_day_trading_dataset(
    *,
    output_path: str | Path,
    gap_report_path: str | Path,
    readiness_output_path: str | Path,
    trading_dates_source: str | Path = "data/formal_sources/official_turnover_20211201_20231231.csv",
    start_date: str = "2021-12-01",
    end_date: str = "2023-12-29",
    raw_day_trading_cache_dir: str | Path | None = "data/formal_sources/chip_flow_overlay_2021_2023/raw_twse_day_trading_cache",
    raw_volume_cache_dir: str | Path | None = "data/formal_sources/chip_flow_overlay_2021_2023/raw_twse_stock_day_volume_cache",
    force_fetch: bool = False,
    sleep_seconds: float = 0.0,
    retry_attempts: int = 3,
    retry_sleep_seconds: float = 1.0,
    fetcher: JsonFetcher | None = None,
    progress_every: int = 50,
) -> DayTradingBuildResult:
    start = _parse_iso_date(start_date)
    end = _parse_iso_date(end_date)
    trading_dates = load_twse_trading_dates(trading_dates_source, start, end)
    fetch_json = fetcher or fetch_public_json
    day_cache_root = Path(raw_day_trading_cache_dir) if raw_day_trading_cache_dir else None
    volume_cache_root = Path(raw_volume_cache_dir) if raw_volume_cache_dir else None
    checked_at = _utc_now_iso()

    fetch_errors: list[dict[str, str]] = []
    volume_by_key = build_total_volume_map(
        trading_dates=trading_dates,
        cache_root=volume_cache_root,
        force_fetch=force_fetch,
        fetcher=fetch_json,
        retry_attempts=retry_attempts,
        retry_sleep_seconds=retry_sleep_seconds,
        sleep_seconds=sleep_seconds,
        progress_every=progress_every,
        fetch_errors=fetch_errors,
    )

    rows: list[dict[str, str]] = []
    for index, trade_date in enumerate(trading_dates, start=1):
        source_url = build_twse_day_trading_url(trade_date)
        try:
            payload = _fetch_daily_payload(
                source_url=source_url,
                cache_root=day_cache_root,
                trade_date=trade_date,
                force_fetch=force_fetch,
                fetcher=fetch_json,
                retry_attempts=retry_attempts,
                retry_sleep_seconds=retry_sleep_seconds,
            )
            rows.extend(
                parse_twse_day_trading_payload(
                    payload=payload,
                    trade_date=trade_date,
                    source_url=source_url,
                    volume_by_symbol={symbol: volume_by_key.get((symbol, trade_date.isoformat())) for symbol, _, _ in TARGET_UNIVERSE},
                )
            )
        except (SourceFetchError, ValueError, KeyError, TypeError) as exc:
            fetch_errors.append({"date": trade_date.isoformat(), "source_url": source_url, "error": str(exc)})
        if sleep_seconds > 0:
            time.sleep(sleep_seconds)
        if progress_every > 0 and index % progress_every == 0:
            print(f"Fetched TWSE TWTB4U day-trading source {index}/{len(trading_dates)}", flush=True)

    rows = _dedupe_and_sort(rows)
    rows = _add_rolling_ratio_fields(rows)
    gap_rows = build_gap_rows(rows=rows, trading_dates=trading_dates, fetch_errors=fetch_errors, checked_at=checked_at)
    readiness = build_readiness(
        rows=rows,
        gap_rows=gap_rows,
        trading_dates=trading_dates,
        fetch_errors=fetch_errors,
        start=start,
        end=end,
    )

    output = Path(output_path)
    gap_output = Path(gap_report_path)
    readiness_output = Path(readiness_output_path)
    _write_rows(output, DAY_TRADING_FIELDS, rows)
    _write_rows(gap_output, GAP_FIELDS, gap_rows)
    _write_json(readiness_output, readiness)
    return DayTradingBuildResult(output, gap_output, readiness_output, readiness)


def validate_day_trading_dataset(
    *,
    input_path: str | Path,
    gap_report_path: str | Path,
    readiness_output_path: str | Path,
    trading_dates_source: str | Path = "data/formal_sources/official_turnover_20211201_20231231.csv",
    start_date: str = "2021-12-01",
    end_date: str = "2023-12-29",
) -> dict[str, object]:
    start = _parse_iso_date(start_date)
    end = _parse_iso_date(end_date)
    trading_dates = load_twse_trading_dates(trading_dates_source, start, end)
    rows = _read_rows(Path(input_path))
    _assert_header(Path(input_path), DAY_TRADING_FIELDS)
    checked_at = _utc_now_iso()
    gap_rows = build_gap_rows(rows=rows, trading_dates=trading_dates, fetch_errors=[], checked_at=checked_at)
    readiness = build_readiness(
        rows=rows,
        gap_rows=gap_rows,
        trading_dates=trading_dates,
        fetch_errors=[],
        start=start,
        end=end,
    )
    _write_rows(Path(gap_report_path), GAP_FIELDS, gap_rows)
    _write_json(Path(readiness_output_path), readiness)
    _validate_readiness(readiness)
    return readiness


def build_total_volume_map(
    *,
    trading_dates: list[date],
    cache_root: Path | None,
    force_fetch: bool,
    fetcher: JsonFetcher,
    retry_attempts: int,
    retry_sleep_seconds: float,
    sleep_seconds: float,
    progress_every: int,
    fetch_errors: list[dict[str, str]],
) -> dict[tuple[str, str], int]:
    months = sorted({date(day.year, day.month, 1) for day in trading_dates})
    output: dict[tuple[str, str], int] = {}
    total_requests = len(TARGET_UNIVERSE) * len(months)
    request_count = 0
    for symbol, _, _ in TARGET_UNIVERSE:
        for month_start in months:
            request_count += 1
            source_url = build_twse_stock_day_url(symbol, month_start)
            try:
                payload = _fetch_month_payload(
                    source_url=source_url,
                    cache_root=cache_root,
                    symbol=symbol,
                    month_start=month_start,
                    force_fetch=force_fetch,
                    fetcher=fetcher,
                    retry_attempts=retry_attempts,
                    retry_sleep_seconds=retry_sleep_seconds,
                )
                output.update(parse_twse_stock_day_volumes(payload=payload, symbol=symbol))
            except (SourceFetchError, ValueError, KeyError, TypeError) as exc:
                fetch_errors.append({"date": month_start.strftime("%Y-%m"), "source_url": source_url, "error": str(exc)})
            if sleep_seconds > 0:
                time.sleep(sleep_seconds)
            if progress_every > 0 and request_count % progress_every == 0:
                print(f"Fetched TWSE STOCK_DAY volume source {request_count}/{total_requests}", flush=True)
    return output


def build_twse_day_trading_url(trade_date: date) -> str:
    return _url(
        "https://www.twse.com.tw/rwd/zh/dayTrading/TWTB4U",
        date=trade_date.strftime("%Y%m%d"),
        selectType="All",
        response="json",
    )


def build_twse_stock_day_url(symbol: str, month_start: date) -> str:
    return _url(
        "https://www.twse.com.tw/rwd/zh/afterTrading/STOCK_DAY",
        date=month_start.strftime("%Y%m%d"),
        stockNo=symbol,
        response="json",
    )


def parse_twse_day_trading_payload(
    *,
    payload: dict[str, Any],
    trade_date: date,
    source_url: str,
    volume_by_symbol: dict[str, int | None],
) -> list[dict[str, str]]:
    if payload.get("stat") != "OK":
        return []
    table = _find_table(payload.get("tables", []), "當日沖銷交易標的及成交量值")
    if not table:
        return []
    fields = table.get("fields", [])
    data = table.get("data", [])
    symbol_index = _field_index(fields, "證券代號")
    name_index = _field_index(fields, "證券名稱")
    day_volume_index = _field_index(fields, "當日沖銷交易成交股數")
    target_meta = {symbol: (ticker, name) for symbol, ticker, name in TARGET_UNIVERSE}
    output: list[dict[str, str]] = []
    for raw_row in data:
        if not isinstance(raw_row, list) or max(symbol_index, name_index, day_volume_index) >= len(raw_row):
            continue
        symbol = str(raw_row[symbol_index]).strip()
        if symbol not in target_meta:
            continue
        ticker, fallback_name = target_meta[symbol]
        day_volume = _parse_int(str(raw_row[day_volume_index]))
        total_volume = volume_by_symbol.get(symbol)
        ratio = day_volume / total_volume * 100 if total_volume else None
        output.append(
            {
                "date": trade_date.isoformat(),
                "symbol": symbol,
                "ticker": ticker,
                "name": str(raw_row[name_index]).strip() or fallback_name,
                "day_trading_buy_volume": "",
                "day_trading_sell_volume": "",
                "day_trading_total_volume": str(day_volume),
                "total_trading_volume": "" if total_volume is None else str(total_volume),
                "day_trading_volume_ratio": _format_float(ratio),
                "day_trading_ratio_5d_avg": "",
                "day_trading_ratio_20d_avg": "",
                "day_trading_ratio_5d_change": "",
                "day_trading_ratio_20d_change": "",
                "day_trading_overheat_flag": "false",
                "data_source": DATA_SOURCE,
                "source_url": source_url,
                "data_quality_status": DATA_QUALITY_STATUS if total_volume else f"{DATA_QUALITY_STATUS};total_volume_missing",
            }
        )
    return output


def parse_twse_stock_day_volumes(*, payload: dict[str, Any], symbol: str) -> dict[tuple[str, str], int]:
    if payload.get("stat") != "OK":
        return {}
    fields = payload.get("fields", [])
    data = payload.get("data", [])
    date_index = _field_index(fields, "日期")
    volume_index = _field_index(fields, "成交股數")
    output: dict[tuple[str, str], int] = {}
    for row in data:
        if not isinstance(row, list) or max(date_index, volume_index) >= len(row):
            continue
        trade_date = _parse_roc_date(str(row[date_index]))
        output[(symbol, trade_date.isoformat())] = _parse_int(str(row[volume_index]))
    return output


def build_gap_rows(
    *,
    rows: list[dict[str, str]],
    trading_dates: list[date],
    fetch_errors: list[dict[str, str]],
    checked_at: str,
) -> list[dict[str, str]]:
    available = {(row["symbol"], row["date"]) for row in rows}
    by_date_url = {row["date"]: row.get("source_url", "") for row in rows}
    output: list[dict[str, str]] = []
    for symbol, ticker, name in TARGET_UNIVERSE:
        for trade_date in trading_dates:
            date_text = trade_date.isoformat()
            if (symbol, date_text) in available:
                continue
            output.append(
                {
                    "symbol": symbol,
                    "ticker": ticker,
                    "name": name,
                    "date": date_text,
                    "missing_reason": "missing_twse_twtb4u_target_symbol_row",
                    "source_url": by_date_url.get(date_text, build_twse_day_trading_url(trade_date)),
                    "blocking": "no" if symbol in ETF_SYMBOLS else "yes",
                    "checked_at": checked_at,
                }
            )
    for error in fetch_errors:
        output.append(
            {
                "symbol": "",
                "ticker": "",
                "name": "TWSE day-trading/volume source",
                "date": error.get("date", ""),
                "missing_reason": f"source_fetch_or_parse_failed: {error.get('error', '')}",
                "source_url": error.get("source_url", ""),
                "blocking": "yes",
                "checked_at": checked_at,
            }
        )
    return sorted(output, key=lambda row: (row["date"], row["symbol"], row["missing_reason"]))


def build_readiness(
    *,
    rows: list[dict[str, str]],
    gap_rows: list[dict[str, str]],
    trading_dates: list[date],
    fetch_errors: list[dict[str, str]],
    start: date,
    end: date,
) -> dict[str, object]:
    target_symbols = {symbol for symbol, _, _ in TARGET_UNIVERSE}
    stock_symbols = target_symbols - ETF_SYMBOLS
    covered_symbols = {row["symbol"] for row in rows}
    expected = len(target_symbols) * len(trading_dates)
    expected_stocks = len(stock_symbols) * len(trading_dates)
    stock_rows = [row for row in rows if row["symbol"] in stock_symbols]
    coverage_ratio = len(rows) / expected if expected else 0.0
    stock_coverage_ratio = len(stock_rows) / expected_stocks if expected_stocks else 0.0
    future_violations = sum(1 for row in rows if _parse_iso_date(row["date"]) > end)
    etf_gap_count = sum(1 for row in gap_rows if row["symbol"] in ETF_SYMBOLS)
    stock_gap_count = sum(1 for row in gap_rows if row["symbol"] and row["symbol"] not in ETF_SYMBOLS)
    missing_denominator_count = sum(1 for row in rows if not row.get("total_trading_volume"))
    blocking_issues: list[str] = []
    if not trading_dates:
        blocking_issues.append("No TWSE trading dates were available from official turnover source.")
    if fetch_errors:
        blocking_issues.append(f"{len(fetch_errors)} TWSE day-trading/volume fetch or parse errors occurred.")
    if stock_coverage_ratio < 0.95:
        blocking_issues.append(f"7-stock day-trading coverage below threshold: {stock_coverage_ratio:.4f}.")
    if future_violations:
        blocking_issues.append(f"{future_violations} rows violate future-data rule.")

    ready = not blocking_issues
    warnings = [
        "TWSE TWTB4U official source provides day-trading total volume, buy amount, and sell amount; it does not split buy/sell volume, so day_trading_buy_volume and day_trading_sell_volume are left blank instead of estimating values.",
        "day_trading_volume_ratio uses TWSE STOCK_DAY total trading volume as denominator.",
        "ETF rows are tracked and gap-reported separately; ETF gaps do not block the 7-stock overlay v1 readiness.",
    ]
    if missing_denominator_count:
        warnings.append(f"{missing_denominator_count} rows are missing STOCK_DAY total trading volume denominator; ratio fields are blank for those rows.")

    return {
        "ready": ready,
        "source_mode": "day_trading_ready" if ready else "day_trading_blocked",
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "target_symbol_count": len(target_symbols),
        "covered_symbol_count": len(covered_symbols),
        "trading_day_count": len(trading_dates),
        "expected_symbol_date_count": expected,
        "day_trading_row_count": len(rows),
        "coverage_ratio": round(coverage_ratio, 8),
        "stock_coverage_ratio": round(stock_coverage_ratio, 8),
        "etf_gap_count": etf_gap_count,
        "stock_gap_count": stock_gap_count,
        "future_data_violation_count": future_violations,
        "blocking_issues": blocking_issues,
        "warnings": warnings,
    }


def validate_day_trading_readiness(readiness_path: str | Path) -> dict[str, object]:
    readiness = json.loads(Path(readiness_path).read_text(encoding="utf-8"))
    _validate_readiness(readiness)
    return readiness


def _validate_readiness(readiness: dict[str, object]) -> None:
    missing = [field for field in REQUIRED_READINESS_FIELDS if field not in readiness]
    if missing:
        raise ValueError(f"day-trading readiness missing fields: {', '.join(missing)}")
    if readiness["source_mode"] not in {"day_trading_ready", "day_trading_blocked"}:
        raise ValueError(f"unsupported source_mode: {readiness['source_mode']}")
    if readiness["ready"] and readiness["source_mode"] != "day_trading_ready":
        raise ValueError("ready=true requires source_mode=day_trading_ready")
    if readiness["future_data_violation_count"] != 0:
        raise ValueError("future_data_violation_count must be zero")
    if readiness["ready"] and float(readiness.get("stock_coverage_ratio", 0.0)) < 0.95:
        raise ValueError("ready=true requires stock_coverage_ratio >= 0.95")


def _fetch_daily_payload(
    *,
    source_url: str,
    cache_root: Path | None,
    trade_date: date,
    force_fetch: bool,
    fetcher: JsonFetcher,
    retry_attempts: int,
    retry_sleep_seconds: float,
) -> dict[str, Any]:
    cache_path = cache_root / f"{trade_date.strftime('%Y%m%d')}.json" if cache_root else None
    return _fetch_json_with_cache(
        source_url=source_url,
        cache_path=cache_path,
        force_fetch=force_fetch,
        fetcher=fetcher,
        retry_attempts=retry_attempts,
        retry_sleep_seconds=retry_sleep_seconds,
    )


def _fetch_month_payload(
    *,
    source_url: str,
    cache_root: Path | None,
    symbol: str,
    month_start: date,
    force_fetch: bool,
    fetcher: JsonFetcher,
    retry_attempts: int,
    retry_sleep_seconds: float,
) -> dict[str, Any]:
    cache_path = cache_root / symbol / f"{month_start.strftime('%Y%m')}.json" if cache_root else None
    return _fetch_json_with_cache(
        source_url=source_url,
        cache_path=cache_path,
        force_fetch=force_fetch,
        fetcher=fetcher,
        retry_attempts=retry_attempts,
        retry_sleep_seconds=retry_sleep_seconds,
    )


def _fetch_json_with_cache(
    *,
    source_url: str,
    cache_path: Path | None,
    force_fetch: bool,
    fetcher: JsonFetcher,
    retry_attempts: int,
    retry_sleep_seconds: float,
) -> dict[str, Any]:
    if cache_path and cache_path.exists() and not force_fetch:
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


def _add_rolling_ratio_fields(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    by_symbol: dict[str, list[dict[str, str]]] = {}
    for row in sorted(rows, key=lambda item: (item["symbol"], item["date"])):
        by_symbol.setdefault(row["symbol"], []).append(dict(row))
    output: list[dict[str, str]] = []
    for symbol_rows in by_symbol.values():
        for index, row in enumerate(symbol_rows):
            ratio_5d = _rolling_average(symbol_rows, index, "day_trading_volume_ratio", 5)
            ratio_20d = _rolling_average(symbol_rows, index, "day_trading_volume_ratio", 20)
            current = _parse_float(row.get("day_trading_volume_ratio"))
            row["day_trading_ratio_5d_avg"] = _format_float(ratio_5d)
            row["day_trading_ratio_20d_avg"] = _format_float(ratio_20d)
            row["day_trading_ratio_5d_change"] = _format_float(None if ratio_5d is None or current is None else current - ratio_5d)
            row["day_trading_ratio_20d_change"] = _format_float(None if ratio_20d is None or current is None else current - ratio_20d)
            row["day_trading_overheat_flag"] = "true" if _is_overheated(current, ratio_5d, ratio_20d) else "false"
            output.append(row)
    return sorted(output, key=lambda item: (item["date"], item["symbol"]))


def _rolling_average(rows: list[dict[str, str]], index: int, field: str, lookback: int) -> float | None:
    start = index - lookback + 1
    if start < 0:
        return None
    values = [_parse_float(row.get(field)) for row in rows[start : index + 1]]
    usable = [value for value in values if value is not None]
    if len(usable) != lookback:
        return None
    return sum(usable) / lookback


def _is_overheated(current: float | None, ratio_5d: float | None, ratio_20d: float | None) -> bool:
    if current is None:
        return False
    if current >= 45.0:
        return True
    if ratio_5d is not None and current - ratio_5d >= 12.0:
        return True
    return ratio_20d is not None and current - ratio_20d >= 18.0


def _find_table(tables: Any, title_text: str) -> dict[str, Any] | None:
    if not isinstance(tables, list):
        return None
    for table in tables:
        if isinstance(table, dict) and title_text in str(table.get("title", "")):
            return table
    return None


def _field_index(fields: list[Any], target: str) -> int:
    normalized = [_normalize_field(str(field)) for field in fields]
    try:
        return normalized.index(_normalize_field(target))
    except ValueError as exc:
        raise ValueError(f"Missing field {target}") from exc


def _normalize_field(value: str) -> str:
    return value.replace(" ", "").strip()


def _read_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return [{key: (value or "").strip() for key, value in row.items()} for row in csv.DictReader(handle)]


def _dedupe_and_sort(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    by_key: dict[tuple[str, str], dict[str, str]] = {}
    for row in rows:
        by_key[(row["symbol"], row["date"])] = row
    return sorted(by_key.values(), key=lambda item: (item["date"], item["symbol"]))


def _assert_header(path: Path, expected_fields: list[str]) -> None:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        header = next(csv.reader(handle), [])
    if header != expected_fields:
        raise ValueError(f"{path} header mismatch")


def _parse_iso_date(value: str) -> date:
    return datetime.strptime(value, "%Y-%m-%d").date()


def _parse_roc_date(value: str) -> date:
    parts = value.strip().split("/")
    if len(parts) != 3:
        raise ValueError(f"Unsupported ROC date: {value}")
    return date(int(parts[0]) + 1911, int(parts[1]), int(parts[2]))


def _parse_int(value: str | None) -> int:
    stripped = (value or "").replace(",", "").replace("--", "").strip()
    if not stripped:
        return 0
    return int(float(stripped))


def _parse_float(value: str | None) -> float | None:
    stripped = (value or "").replace(",", "").strip()
    if not stripped:
        return None
    return float(stripped)


def _format_float(value: float | None) -> str:
    return "" if value is None else f"{value:.4f}"


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


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
