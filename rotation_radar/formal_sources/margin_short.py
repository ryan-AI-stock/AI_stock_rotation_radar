from __future__ import annotations

import csv
import json
import time
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Callable
from urllib.parse import urlencode

from rotation_radar.formal_sources.chip_flow_overlay import TARGET_UNIVERSE
from rotation_radar.formal_sources.institutional_flows import load_twse_trading_dates
from rotation_radar.public_sources import SourceFetchError, fetch_public_text


MARGIN_SHORT_FIELDS = [
    "date",
    "symbol",
    "ticker",
    "name",
    "margin_buy",
    "margin_sell",
    "margin_balance",
    "margin_balance_change",
    "short_sell",
    "short_cover",
    "short_balance",
    "short_balance_change",
    "securities_lending_balance",
    "securities_lending_balance_change",
    "margin_balance_5d_change_pct",
    "margin_balance_20d_change_pct",
    "short_balance_5d_change_pct",
    "short_balance_20d_change_pct",
    "lending_balance_5d_change_pct",
    "lending_balance_20d_change_pct",
    "margin_overheat_flag",
    "short_lending_pressure_flag",
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
    "margin_short_row_count",
    "coverage_ratio",
    "stock_coverage_ratio",
    "etf_gap_count",
    "stock_gap_count",
    "future_data_violation_count",
    "blocking_issues",
    "warnings",
]

ETF_SYMBOLS = {"0050", "00631L"}
DATA_SOURCE = "twse_mi_margn_margin_short_shares"
DATA_QUALITY_STATUS = "official_twse_mi_margn_margin_short_lending_unavailable"


@dataclass(frozen=True)
class MarginShortBuildResult:
    output_path: Path
    gap_report_path: Path
    readiness_path: Path
    readiness: dict[str, object]


TextFetcher = Callable[[str], str]


def build_margin_short_dataset(
    *,
    output_path: str | Path,
    gap_report_path: str | Path,
    readiness_output_path: str | Path,
    trading_dates_source: str | Path = "data/formal_sources/official_turnover_20211201_20231231.csv",
    start_date: str = "2021-12-01",
    end_date: str = "2023-12-29",
    raw_cache_dir: str | Path | None = "data/formal_sources/chip_flow_overlay_2021_2023/raw_twse_margin_cache",
    force_fetch: bool = False,
    sleep_seconds: float = 0.0,
    retry_attempts: int = 3,
    retry_sleep_seconds: float = 1.0,
    fetcher: TextFetcher | None = None,
    progress_every: int = 50,
) -> MarginShortBuildResult:
    start = _parse_iso_date(start_date)
    end = _parse_iso_date(end_date)
    trading_dates = load_twse_trading_dates(trading_dates_source, start, end)
    fetch_text = fetcher or fetch_public_text
    cache_root = Path(raw_cache_dir) if raw_cache_dir else None
    checked_at = _utc_now_iso()

    rows: list[dict[str, str]] = []
    fetch_errors: list[dict[str, str]] = []
    target_symbols = {symbol for symbol, _, _ in TARGET_UNIVERSE}
    for index, trade_date in enumerate(trading_dates, start=1):
        source_url = build_twse_margin_url(trade_date)
        try:
            payload = _fetch_daily_payload(
                source_url=source_url,
                cache_root=cache_root,
                trade_date=trade_date,
                force_fetch=force_fetch,
                fetcher=fetch_text,
                retry_attempts=retry_attempts,
                retry_sleep_seconds=retry_sleep_seconds,
            )
            rows.extend(parse_twse_margin_csv(payload=payload, trade_date=trade_date, source_url=source_url))
        except (SourceFetchError, ValueError, KeyError, TypeError) as exc:
            fetch_errors.append({"date": trade_date.isoformat(), "source_url": source_url, "error": str(exc)})
        if sleep_seconds > 0:
            time.sleep(sleep_seconds)
        if progress_every > 0 and index % progress_every == 0:
            print(f"Fetched TWSE MI_MARGN margin/short source {index}/{len(trading_dates)}", flush=True)

    rows = _dedupe_and_sort([row for row in rows if row["symbol"] in target_symbols])
    rows = _add_rolling_change_fields(rows)
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
    _write_rows(output, MARGIN_SHORT_FIELDS, rows)
    _write_rows(gap_output, GAP_FIELDS, gap_rows)
    _write_json(readiness_output, readiness)
    return MarginShortBuildResult(
        output_path=output,
        gap_report_path=gap_output,
        readiness_path=readiness_output,
        readiness=readiness,
    )


def validate_margin_short_dataset(
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
    _assert_header(Path(input_path), MARGIN_SHORT_FIELDS)
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


def build_twse_margin_url(trade_date: date) -> str:
    return _url(
        "https://www.twse.com.tw/exchangeReport/MI_MARGN",
        date=trade_date.strftime("%Y%m%d"),
        selectType="ALL",
        response="open_data",
    )


def parse_twse_margin_csv(*, payload: str, trade_date: date, source_url: str) -> list[dict[str, str]]:
    if not _looks_like_twse_margin_csv(payload):
        raise ValueError("TWSE MI_MARGN source did not return the stock-level CSV")
    target_meta = {symbol: (ticker, name) for symbol, ticker, name in TARGET_UNIVERSE}
    output: list[dict[str, str]] = []
    for row in csv.DictReader(payload.splitlines()):
        symbol = (row.get("股票代號") or "").strip()
        if symbol not in target_meta:
            continue
        ticker, fallback_name = target_meta[symbol]
        margin_balance = _parse_int(row.get("融資今日餘額"))
        previous_margin_balance = _parse_int(row.get("融資前日餘額"))
        short_balance = _parse_int(row.get("融券今日餘額"))
        previous_short_balance = _parse_int(row.get("融券前日餘額"))
        short_cover = _parse_int(row.get("融券買進")) + _parse_int(row.get("融券現券償還"))
        output.append(
            {
                "date": trade_date.isoformat(),
                "symbol": symbol,
                "ticker": ticker,
                "name": (row.get("股票名稱") or "").strip() or fallback_name,
                "margin_buy": str(_parse_int(row.get("融資買進"))),
                "margin_sell": str(_parse_int(row.get("融資賣出"))),
                "margin_balance": str(margin_balance),
                "margin_balance_change": str(margin_balance - previous_margin_balance),
                "short_sell": str(_parse_int(row.get("融券賣出"))),
                "short_cover": str(short_cover),
                "short_balance": str(short_balance),
                "short_balance_change": str(short_balance - previous_short_balance),
                "securities_lending_balance": "",
                "securities_lending_balance_change": "",
                "margin_balance_5d_change_pct": "",
                "margin_balance_20d_change_pct": "",
                "short_balance_5d_change_pct": "",
                "short_balance_20d_change_pct": "",
                "lending_balance_5d_change_pct": "",
                "lending_balance_20d_change_pct": "",
                "margin_overheat_flag": "false",
                "short_lending_pressure_flag": "false",
                "data_source": DATA_SOURCE,
                "source_url": source_url,
                "data_quality_status": DATA_QUALITY_STATUS,
            }
        )
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
                    "missing_reason": "missing_twse_mi_margn_target_symbol_row",
                    "source_url": by_date_url.get(date_text, build_twse_margin_url(trade_date)),
                    "blocking": "no" if symbol in ETF_SYMBOLS else "yes",
                    "checked_at": checked_at,
                }
            )
    for error in fetch_errors:
        output.append(
            {
                "symbol": "",
                "ticker": "",
                "name": "TWSE MI_MARGN daily source",
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
    blocking_issues: list[str] = []
    if not trading_dates:
        blocking_issues.append("No TWSE trading dates were available from official turnover source.")
    if fetch_errors:
        blocking_issues.append(f"{len(fetch_errors)} TWSE MI_MARGN fetch/parse errors occurred.")
    if stock_coverage_ratio < 0.95:
        blocking_issues.append(f"7-stock margin/short coverage below threshold: {stock_coverage_ratio:.4f}.")
    if future_violations:
        blocking_issues.append(f"{future_violations} rows violate future-data rule.")

    ready = not blocking_issues
    return {
        "ready": ready,
        "source_mode": "margin_short_ready" if ready else "margin_short_blocked",
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "target_symbol_count": len(target_symbols),
        "covered_symbol_count": len(covered_symbols),
        "trading_day_count": len(trading_dates),
        "expected_symbol_date_count": expected,
        "margin_short_row_count": len(rows),
        "coverage_ratio": round(coverage_ratio, 8),
        "stock_coverage_ratio": round(stock_coverage_ratio, 8),
        "etf_gap_count": etf_gap_count,
        "stock_gap_count": stock_gap_count,
        "future_data_violation_count": future_violations,
        "blocking_issues": blocking_issues,
        "warnings": [
            "TWSE MI_MARGN official source provides margin and short-selling balances in shares/lots, not securities lending balance; securities_lending_* fields are left blank instead of estimating or fabricating values.",
            "ETF rows are tracked and gap-reported separately; ETF gaps do not block the 7-stock overlay v1 readiness.",
        ],
    }


def validate_margin_short_readiness(readiness_path: str | Path) -> dict[str, object]:
    readiness = json.loads(Path(readiness_path).read_text(encoding="utf-8"))
    _validate_readiness(readiness)
    return readiness


def _validate_readiness(readiness: dict[str, object]) -> None:
    missing = [field for field in REQUIRED_READINESS_FIELDS if field not in readiness]
    if missing:
        raise ValueError(f"margin/short readiness missing fields: {', '.join(missing)}")
    if readiness["source_mode"] not in {"margin_short_ready", "margin_short_blocked"}:
        raise ValueError(f"unsupported source_mode: {readiness['source_mode']}")
    if readiness["ready"] and readiness["source_mode"] != "margin_short_ready":
        raise ValueError("ready=true requires source_mode=margin_short_ready")
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
    fetcher: TextFetcher,
    retry_attempts: int,
    retry_sleep_seconds: float,
) -> str:
    cache_path = cache_root / f"{trade_date.strftime('%Y%m%d')}.csv" if cache_root else None
    if cache_path and cache_path.exists() and not force_fetch:
        return cache_path.read_text(encoding="utf-8-sig")
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
        cache_path.write_text(payload, encoding="utf-8")
    return payload


def _add_rolling_change_fields(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    by_symbol: dict[str, list[dict[str, str]]] = {}
    for row in sorted(rows, key=lambda item: (item["symbol"], item["date"])):
        by_symbol.setdefault(row["symbol"], []).append(dict(row))

    output: list[dict[str, str]] = []
    for symbol_rows in by_symbol.values():
        for index, row in enumerate(symbol_rows):
            margin_5d = _rolling_pct(symbol_rows, index, "margin_balance", 5)
            margin_20d = _rolling_pct(symbol_rows, index, "margin_balance", 20)
            short_5d = _rolling_pct(symbol_rows, index, "short_balance", 5)
            short_20d = _rolling_pct(symbol_rows, index, "short_balance", 20)
            row["margin_balance_5d_change_pct"] = _format_pct(margin_5d)
            row["margin_balance_20d_change_pct"] = _format_pct(margin_20d)
            row["short_balance_5d_change_pct"] = _format_pct(short_5d)
            row["short_balance_20d_change_pct"] = _format_pct(short_20d)
            row["margin_overheat_flag"] = "true" if _is_margin_overheated(margin_5d, margin_20d) else "false"
            row["short_lending_pressure_flag"] = "true" if _is_short_pressure(short_5d, short_20d) else "false"
            output.append(row)
    return sorted(output, key=lambda item: (item["date"], item["symbol"]))


def _rolling_pct(rows: list[dict[str, str]], index: int, field: str, lookback: int) -> float | None:
    previous_index = index - lookback
    if previous_index < 0:
        return None
    current = _parse_int(rows[index].get(field))
    previous = _parse_int(rows[previous_index].get(field))
    if previous == 0:
        return None
    return (current - previous) / abs(previous) * 100


def _is_margin_overheated(change_5d: float | None, change_20d: float | None) -> bool:
    return (change_5d is not None and change_5d >= 12.0) or (change_20d is not None and change_20d >= 25.0)


def _is_short_pressure(change_5d: float | None, change_20d: float | None) -> bool:
    return (change_5d is not None and change_5d >= 20.0) or (change_20d is not None and change_20d >= 50.0)


def _format_pct(value: float | None) -> str:
    return "" if value is None else f"{value:.4f}"


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


def _looks_like_twse_margin_csv(payload: str) -> bool:
    first_line = payload.lstrip("\ufeff\r\n ").splitlines()[0] if payload.strip() else ""
    return "股票代號" in first_line and "融資今日餘額" in first_line and "融券今日餘額" in first_line


def _parse_iso_date(value: str) -> date:
    return datetime.strptime(value, "%Y-%m-%d").date()


def _parse_int(value: str | None) -> int:
    stripped = (value or "").replace(",", "").replace("--", "").strip()
    if not stripped:
        return 0
    return int(float(stripped))


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
