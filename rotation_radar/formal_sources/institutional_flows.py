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
from rotation_radar.public_sources import SourceFetchError, fetch_public_json


INSTITUTIONAL_FLOW_FIELDS = [
    "date",
    "symbol",
    "ticker",
    "name",
    "foreign_net_buy_shares",
    "foreign_net_buy_twd",
    "investment_trust_net_buy_shares",
    "investment_trust_net_buy_twd",
    "dealer_net_buy_shares",
    "dealer_net_buy_twd",
    "total_institutional_net_buy_twd",
    "foreign_consecutive_buy_days",
    "foreign_consecutive_sell_days",
    "trust_consecutive_buy_days",
    "trust_consecutive_sell_days",
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
    "institutional_flow_row_count",
    "coverage_ratio",
    "etf_gap_count",
    "stock_gap_count",
    "future_data_violation_count",
    "blocking_issues",
    "warnings",
]

ETF_SYMBOLS = {"0050", "00631L"}


@dataclass(frozen=True)
class InstitutionalFlowBuildResult:
    output_path: Path
    gap_report_path: Path
    readiness_path: Path
    readiness: dict[str, Any]


JsonFetcher = Callable[[str], dict[str, Any]]


def build_institutional_flows_dataset(
    *,
    output_path: str | Path,
    gap_report_path: str | Path,
    readiness_output_path: str | Path,
    trading_dates_source: str | Path = "data/formal_sources/official_turnover_20211201_20231231.csv",
    start_date: str = "2021-12-01",
    end_date: str = "2023-12-29",
    raw_cache_dir: str | Path | None = "data/formal_sources/chip_flow_overlay_2021_2023/raw_twse_t86_cache",
    force_fetch: bool = False,
    sleep_seconds: float = 0.0,
    retry_attempts: int = 3,
    retry_sleep_seconds: float = 1.0,
    fetcher: JsonFetcher | None = None,
    progress_every: int = 50,
) -> InstitutionalFlowBuildResult:
    start = _parse_iso_date(start_date)
    end = _parse_iso_date(end_date)
    trading_dates = load_twse_trading_dates(trading_dates_source, start, end)
    fetch_json = fetcher or fetch_public_json
    cache_root = Path(raw_cache_dir) if raw_cache_dir else None
    checked_at = _utc_now_iso()

    rows: list[dict[str, str]] = []
    fetch_errors: list[dict[str, str]] = []
    target_symbols = {symbol for symbol, _, _ in TARGET_UNIVERSE}
    for index, trade_date in enumerate(trading_dates, start=1):
        source_url = build_twse_t86_url(trade_date)
        try:
            payload = _fetch_daily_payload(
                source_url=source_url,
                cache_root=cache_root,
                trade_date=trade_date,
                force_fetch=force_fetch,
                fetcher=fetch_json,
                retry_attempts=retry_attempts,
                retry_sleep_seconds=retry_sleep_seconds,
            )
            rows.extend(parse_twse_t86_payload(payload=payload, trade_date=trade_date, source_url=source_url))
        except (SourceFetchError, ValueError, KeyError, TypeError) as exc:
            fetch_errors.append(
                {
                    "date": trade_date.isoformat(),
                    "source_url": source_url,
                    "error": str(exc),
                }
            )
        if sleep_seconds > 0:
            time.sleep(sleep_seconds)
        if progress_every > 0 and index % progress_every == 0:
            print(f"Fetched TWSE T86 institutional source {index}/{len(trading_dates)}", flush=True)

    rows = _dedupe_and_sort([row for row in rows if row["symbol"] in target_symbols])
    rows = _add_consecutive_flow_counts(rows)
    gap_rows = build_gap_rows(
        rows=rows,
        trading_dates=trading_dates,
        fetch_errors=fetch_errors,
        checked_at=checked_at,
    )
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
    _write_rows(output, INSTITUTIONAL_FLOW_FIELDS, rows)
    _write_rows(gap_output, GAP_FIELDS, gap_rows)
    _write_json(readiness_output, readiness)
    return InstitutionalFlowBuildResult(
        output_path=output,
        gap_report_path=gap_output,
        readiness_path=readiness_output,
        readiness=readiness,
    )


def validate_institutional_flows_dataset(
    *,
    input_path: str | Path,
    gap_report_path: str | Path,
    readiness_output_path: str | Path,
    trading_dates_source: str | Path = "data/formal_sources/official_turnover_20211201_20231231.csv",
    start_date: str = "2021-12-01",
    end_date: str = "2023-12-29",
) -> dict[str, Any]:
    start = _parse_iso_date(start_date)
    end = _parse_iso_date(end_date)
    trading_dates = load_twse_trading_dates(trading_dates_source, start, end)
    rows = _read_rows(Path(input_path))
    _assert_header(Path(input_path), INSTITUTIONAL_FLOW_FIELDS)
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


def load_twse_trading_dates(source_path: str | Path, start: date, end: date) -> list[date]:
    dates: set[date] = set()
    with Path(source_path).open("r", encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            if row.get("exchange") != "TWSE":
                continue
            trade_date = _parse_iso_date(row["date"])
            if start <= trade_date <= end:
                dates.add(trade_date)
    return sorted(dates)


def build_twse_t86_url(trade_date: date) -> str:
    return _url(
        "https://www.twse.com.tw/rwd/zh/fund/T86",
        date=trade_date.strftime("%Y%m%d"),
        selectType="ALLBUT0999",
        response="json",
    )


def parse_twse_t86_payload(*, payload: dict[str, Any], trade_date: date, source_url: str) -> list[dict[str, str]]:
    if payload.get("stat") != "OK":
        return []
    fields = payload.get("fields", [])
    raw_rows = payload.get("data", [])
    symbol_index = _field_index(fields, "證券代號")
    name_index = _field_index(fields, "證券名稱")
    foreign_index = _field_index(fields, "外陸資買賣超股數(不含外資自營商)")
    foreign_dealer_index = _field_index(fields, "外資自營商買賣超股數")
    trust_index = _field_index(fields, "投信買賣超股數")
    dealer_index = _field_index(fields, "自營商買賣超股數")

    target_meta = {symbol: (ticker, name) for symbol, ticker, name in TARGET_UNIVERSE}
    output: list[dict[str, str]] = []
    for raw_row in raw_rows:
        if not isinstance(raw_row, list) or max(symbol_index, name_index, dealer_index) >= len(raw_row):
            continue
        symbol = str(raw_row[symbol_index]).strip()
        if symbol not in target_meta:
            continue
        ticker, fallback_name = target_meta[symbol]
        foreign = _parse_int(str(raw_row[foreign_index])) + _parse_int(str(raw_row[foreign_dealer_index]))
        trust = _parse_int(str(raw_row[trust_index]))
        dealer = _parse_int(str(raw_row[dealer_index]))
        output.append(
            {
                "date": trade_date.isoformat(),
                "symbol": symbol,
                "ticker": ticker,
                "name": str(raw_row[name_index]).strip() or fallback_name,
                "foreign_net_buy_shares": str(foreign),
                "foreign_net_buy_twd": "",
                "investment_trust_net_buy_shares": str(trust),
                "investment_trust_net_buy_twd": "",
                "dealer_net_buy_shares": str(dealer),
                "dealer_net_buy_twd": "",
                "total_institutional_net_buy_twd": "",
                "foreign_consecutive_buy_days": "0",
                "foreign_consecutive_sell_days": "0",
                "trust_consecutive_buy_days": "0",
                "trust_consecutive_sell_days": "0",
                "data_source": "twse_t86_shares_only",
                "source_url": source_url,
                "data_quality_status": "official_twse_t86_shares_only_twd_unavailable",
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
                    "missing_reason": "missing_twse_t86_target_symbol_row",
                    "source_url": by_date_url.get(date_text, build_twse_t86_url(trade_date)),
                    "blocking": "no" if symbol in ETF_SYMBOLS else "yes",
                    "checked_at": checked_at,
                }
            )
    for error in fetch_errors:
        output.append(
            {
                "symbol": "",
                "ticker": "",
                "name": "TWSE T86 daily source",
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
) -> dict[str, Any]:
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
        blocking_issues.append(f"{len(fetch_errors)} TWSE T86 fetch/parse errors occurred.")
    if stock_coverage_ratio < 0.95:
        blocking_issues.append(f"7-stock institutional-flow coverage below threshold: {stock_coverage_ratio:.4f}.")
    if future_violations:
        blocking_issues.append(f"{future_violations} rows violate future-data rule.")

    ready = not blocking_issues
    return {
        "ready": ready,
        "source_mode": "institutional_flow_ready" if ready else "institutional_flow_blocked",
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "target_symbol_count": len(target_symbols),
        "covered_symbol_count": len(covered_symbols),
        "trading_day_count": len(trading_dates),
        "expected_symbol_date_count": expected,
        "institutional_flow_row_count": len(rows),
        "coverage_ratio": round(coverage_ratio, 8),
        "stock_coverage_ratio": round(stock_coverage_ratio, 8),
        "etf_gap_count": etf_gap_count,
        "stock_gap_count": stock_gap_count,
        "future_data_violation_count": future_violations,
        "blocking_issues": blocking_issues,
        "warnings": [
            "TWSE T86 official source provides institutional net buy/sell shares, not TWD amounts; *_twd fields are left blank instead of estimating or fabricating values.",
            "ETF rows are tracked and gap-reported separately; ETF gaps do not block the 7-stock overlay v1 readiness.",
        ],
    }


def validate_institutional_flows_readiness(readiness_path: str | Path) -> dict[str, Any]:
    readiness = json.loads(Path(readiness_path).read_text(encoding="utf-8"))
    _validate_readiness(readiness)
    return readiness


def _validate_readiness(readiness: dict[str, Any]) -> None:
    missing = [field for field in REQUIRED_READINESS_FIELDS if field not in readiness]
    if missing:
        raise ValueError(f"institutional flow readiness missing fields: {', '.join(missing)}")
    if readiness["source_mode"] not in {"institutional_flow_ready", "institutional_flow_blocked"}:
        raise ValueError(f"unsupported source_mode: {readiness['source_mode']}")
    if readiness["ready"] and readiness["source_mode"] != "institutional_flow_ready":
        raise ValueError("ready=true requires source_mode=institutional_flow_ready")
    if readiness["future_data_violation_count"] != 0:
        raise ValueError("future_data_violation_count must be zero")
    if readiness["ready"] and readiness.get("stock_coverage_ratio", 0.0) < 0.95:
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


def _add_consecutive_flow_counts(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    state: dict[str, dict[str, int]] = {}
    output: list[dict[str, str]] = []
    for row in sorted(rows, key=lambda item: (item["symbol"], item["date"])):
        symbol_state = state.setdefault(
            row["symbol"],
            {"foreign_buy": 0, "foreign_sell": 0, "trust_buy": 0, "trust_sell": 0},
        )
        foreign = _parse_int(row["foreign_net_buy_shares"])
        trust = _parse_int(row["investment_trust_net_buy_shares"])
        symbol_state["foreign_buy"] = symbol_state["foreign_buy"] + 1 if foreign > 0 else 0
        symbol_state["foreign_sell"] = symbol_state["foreign_sell"] + 1 if foreign < 0 else 0
        symbol_state["trust_buy"] = symbol_state["trust_buy"] + 1 if trust > 0 else 0
        symbol_state["trust_sell"] = symbol_state["trust_sell"] + 1 if trust < 0 else 0
        updated = dict(row)
        updated["foreign_consecutive_buy_days"] = str(symbol_state["foreign_buy"])
        updated["foreign_consecutive_sell_days"] = str(symbol_state["foreign_sell"])
        updated["trust_consecutive_buy_days"] = str(symbol_state["trust_buy"])
        updated["trust_consecutive_sell_days"] = str(symbol_state["trust_sell"])
        output.append(updated)
    return sorted(output, key=lambda item: (item["date"], item["symbol"]))


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


def _field_index(fields: list[Any], target: str) -> int:
    normalized = [_normalize_field(str(field)) for field in fields]
    try:
        return normalized.index(_normalize_field(target))
    except ValueError as exc:
        raise ValueError(f"Missing field {target}") from exc


def _normalize_field(value: str) -> str:
    return value.replace(" ", "").strip()


def _parse_iso_date(value: str) -> date:
    return datetime.strptime(value, "%Y-%m-%d").date()


def _parse_int(value: str) -> int:
    stripped = value.replace(",", "").replace("--", "").strip()
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


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
