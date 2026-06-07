from __future__ import annotations

import csv
import json
import re
import time
from dataclasses import dataclass
from datetime import date, datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Callable
from urllib.request import Request, urlopen

from rotation_radar.public_sources import SourceFetchError


REVENUE_FIELDS = [
    "symbol",
    "name",
    "metric_name",
    "metric_value",
    "period",
    "announcement_date",
    "available_date",
    "source_type",
    "source_url",
    "ingested_at",
]

GAP_FIELDS = [
    "symbol",
    "name",
    "period",
    "missing_reason",
    "source_url",
    "checked_at",
]

MOPS_MARKET_BY_EXCHANGE = {
    "TWSE": "sii",
    "TPEx": "otc",
}


@dataclass(frozen=True)
class FormalSymbol:
    symbol: str
    name: str
    exchange: str


@dataclass(frozen=True)
class RevenueBuildResult:
    revenue_path: Path
    gap_report_path: Path
    readiness_path: Path
    readiness: dict[str, Any]


TextFetcher = Callable[[str], str]


class _HTMLTableParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.rows: list[list[str]] = []
        self._in_row = False
        self._in_cell = False
        self._current_row: list[str] = []
        self._current_cell: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() == "tr":
            self._in_row = True
            self._current_row = []
        elif self._in_row and tag.lower() in {"td", "th"}:
            self._in_cell = True
            self._current_cell = []

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in {"td", "th"} and self._in_cell:
            self._current_row.append(_normalize_text("".join(self._current_cell)))
            self._current_cell = []
            self._in_cell = False
        elif tag.lower() == "tr" and self._in_row:
            if any(cell for cell in self._current_row):
                self.rows.append(self._current_row)
            self._current_row = []
            self._in_row = False

    def handle_data(self, data: str) -> None:
        if self._in_cell:
            self._current_cell.append(data)


def build_point_in_time_revenue_dataset(
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
    sleep_seconds: float = 0.2,
    retry_attempts: int = 3,
    retry_sleep_seconds: float = 1.0,
    fetcher: TextFetcher | None = None,
    progress_every: int = 10,
) -> RevenueBuildResult:
    start = _parse_iso_date(start_date)
    end = _parse_iso_date(end_date)
    if end < start:
        raise ValueError("end_date must be on or after start_date")

    symbols = load_formal_universe_symbols(formal_universe_path, market_universe_path)
    periods = periods_needed_for_snapshot_window(start, end)
    ingested_at = _utc_now_iso()
    checked_at = ingested_at
    fetch_text = fetcher or fetch_mops_text
    cache_root = Path(raw_cache_dir) if raw_cache_dir else None

    revenue_rows: list[dict[str, str]] = []
    fetch_errors: list[dict[str, str]] = []
    source_urls_by_period_market: dict[tuple[str, str], set[str]] = {}
    symbol_lookup = {item.symbol: item for item in symbols}

    request_count = 0
    total_requests = len(periods) * len(MOPS_MARKET_BY_EXCHANGE) * 2
    for period in periods:
        for exchange, market in MOPS_MARKET_BY_EXCHANGE.items():
            for company_type in (0, 1):
                request_count += 1
                source_url = build_mops_revenue_url(market=market, period=period, company_type=company_type)
                source_urls_by_period_market.setdefault((period, exchange), set()).add(source_url)
                try:
                    html = _fetch_period_html(
                        source_url=source_url,
                        cache_root=cache_root,
                        period=period,
                        market=market,
                        company_type=company_type,
                        force_fetch=force_fetch,
                        fetcher=fetch_text,
                        retry_attempts=retry_attempts,
                        retry_sleep_seconds=retry_sleep_seconds,
                    )
                    rows = parse_mops_revenue_html(
                        html=html,
                        period=period,
                        exchange=exchange,
                        source_url=source_url,
                        ingested_at=ingested_at,
                        symbol_lookup=symbol_lookup,
                    )
                    revenue_rows.extend(rows)
                except (SourceFetchError, ValueError, OSError) as exc:
                    fetch_errors.append(
                        {
                            "period": period,
                            "exchange": exchange,
                            "market": market,
                            "company_type": str(company_type),
                            "source_url": source_url,
                            "error": str(exc),
                        }
                    )
                if sleep_seconds > 0:
                    time.sleep(sleep_seconds)
                if progress_every > 0 and request_count % progress_every == 0:
                    print(f"Fetched point-in-time revenue source {request_count}/{total_requests}", flush=True)

    revenue_rows = _dedupe_and_sort_revenue_rows(revenue_rows)
    gap_rows = build_gap_rows(
        symbols=symbols,
        periods=periods,
        revenue_rows=revenue_rows,
        source_urls_by_period_market=source_urls_by_period_market,
        fetch_errors=fetch_errors,
        checked_at=checked_at,
    )
    readiness = build_readiness(
        symbols=symbols,
        periods=periods,
        revenue_rows=revenue_rows,
        gap_rows=gap_rows,
        fetch_errors=fetch_errors,
        start=start,
        end=end,
    )

    revenue_output = Path(output_path)
    gap_output = Path(gap_report_path)
    readiness_output = Path(readiness_output_path)
    _write_rows(revenue_output, REVENUE_FIELDS, revenue_rows)
    _write_rows(gap_output, GAP_FIELDS, gap_rows)
    _write_json(readiness_output, readiness)

    return RevenueBuildResult(
        revenue_path=revenue_output,
        gap_report_path=gap_output,
        readiness_path=readiness_output,
        readiness=readiness,
    )


def validate_point_in_time_revenue(
    *,
    revenue_file: str | Path,
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
    periods = periods_needed_for_snapshot_window(start, end)
    revenue_rows = _read_revenue_rows(Path(revenue_file), periods)
    checked_at = _utc_now_iso()
    source_urls_by_period_market = _source_urls_from_revenue_rows(revenue_rows, symbols)
    gap_rows = build_gap_rows(
        symbols=symbols,
        periods=periods,
        revenue_rows=revenue_rows,
        source_urls_by_period_market=source_urls_by_period_market,
        fetch_errors=[],
        checked_at=checked_at,
    )
    readiness = build_readiness(
        symbols=symbols,
        periods=periods,
        revenue_rows=revenue_rows,
        gap_rows=gap_rows,
        fetch_errors=[],
        start=start,
        end=end,
    )
    _write_json(Path(output_path), readiness)
    if gap_report_path:
        _write_rows(Path(gap_report_path), GAP_FIELDS, gap_rows)
    return readiness


def load_formal_universe_symbols(
    formal_universe_path: str | Path,
    market_universe_path: str | Path,
) -> list[FormalSymbol]:
    market_by_symbol: dict[str, str] = {}
    with Path(market_universe_path).open("r", encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            symbol = str(row.get("symbol", "")).strip()
            market = str(row.get("market", "")).strip()
            if symbol and market in {"TWSE", "TPEx"}:
                market_by_symbol[symbol] = market

    output: list[FormalSymbol] = []
    with Path(formal_universe_path).open("r", encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            symbol = str(row.get("symbol", "")).strip()
            name = str(row.get("name", "")).strip()
            if not symbol:
                continue
            exchange = market_by_symbol.get(symbol, "")
            if exchange in MOPS_MARKET_BY_EXCHANGE:
                output.append(FormalSymbol(symbol=symbol, name=name, exchange=exchange))

    output.sort(key=lambda item: item.symbol)
    return output


def periods_needed_for_snapshot_window(start: date, end: date) -> list[str]:
    first = _add_months(date(start.year, start.month, 1), -2)
    last = _add_months(date(end.year, end.month, 1), -1)
    periods: list[str] = []
    current = first
    while current <= last:
        periods.append(current.strftime("%Y-%m"))
        current = _add_months(current, 1)
    return periods


def build_mops_revenue_url(*, market: str, period: str, company_type: int) -> str:
    year, month = period.split("-")
    roc_year = int(year) - 1911
    return f"https://mopsov.twse.com.tw/nas/t21/{market}/t21sc03_{roc_year}_{int(month)}_{company_type}.html"


def fetch_mops_text(url: str, timeout: int = 30) -> str:
    request = Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7",
        },
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            payload = response.read()
    except OSError as exc:
        raise SourceFetchError(f"Failed to fetch {url}: {exc}") from exc
    return payload.decode("big5", errors="replace")


def parse_mops_revenue_html(
    *,
    html: str,
    period: str,
    exchange: str,
    source_url: str,
    ingested_at: str,
    symbol_lookup: dict[str, FormalSymbol],
) -> list[dict[str, str]]:
    parser = _HTMLTableParser()
    parser.feed(html)
    available = conservative_available_date_for_period(period)
    output: list[dict[str, str]] = []
    for cells in parser.rows:
        if len(cells) < 3:
            continue
        symbol = cells[0].strip()
        if not re.fullmatch(r"\d{4}", symbol):
            continue
        symbol_info = symbol_lookup.get(symbol)
        if not symbol_info or symbol_info.exchange != exchange:
            continue
        revenue_thousand_twd = _parse_number(cells[2])
        if revenue_thousand_twd is None:
            continue
        output.append(
            {
                "symbol": symbol,
                "name": symbol_info.name or cells[1].strip(),
                "metric_name": "monthly_revenue",
                "metric_value": str(revenue_thousand_twd * 1000),
                "period": period,
                "announcement_date": available.isoformat(),
                "available_date": available.isoformat(),
                "source_type": "mops_monthly_revenue_static_html_conservative_available_date",
                "source_url": source_url,
                "ingested_at": ingested_at,
            }
        )
    return output


def conservative_available_date_for_period(period: str) -> date:
    year, month = [int(part) for part in period.split("-")]
    first_next_month = _add_months(date(year, month, 1), 1)
    available = first_next_month.replace(day=10)
    while available.weekday() >= 5:
        available = available.fromordinal(available.toordinal() + 1)
    return available


def build_gap_rows(
    *,
    symbols: list[FormalSymbol],
    periods: list[str],
    revenue_rows: list[dict[str, str]],
    source_urls_by_period_market: dict[tuple[str, str], set[str]],
    fetch_errors: list[dict[str, str]],
    checked_at: str,
) -> list[dict[str, str]]:
    present = {(row["symbol"], row["period"]) for row in revenue_rows}
    error_urls_by_period_exchange: dict[tuple[str, str], set[str]] = {}
    for error in fetch_errors:
        error_urls_by_period_exchange.setdefault((error["period"], error["exchange"]), set()).add(error["source_url"])

    gaps: list[dict[str, str]] = []
    for symbol in symbols:
        for period in periods:
            if (symbol.symbol, period) in present:
                continue
            key = (period, symbol.exchange)
            source_urls = sorted(source_urls_by_period_market.get(key) or error_urls_by_period_exchange.get(key) or [])
            reason = "missing_from_mops_monthly_revenue_static_html"
            if key in error_urls_by_period_exchange:
                reason = "source_fetch_or_parse_error"
            gaps.append(
                {
                    "symbol": symbol.symbol,
                    "name": symbol.name,
                    "period": period,
                    "missing_reason": reason,
                    "source_url": " | ".join(source_urls),
                    "checked_at": checked_at,
                }
            )
    gaps.sort(key=lambda row: (row["symbol"], row["period"]))
    return gaps


def build_readiness(
    *,
    symbols: list[FormalSymbol],
    periods: list[str],
    revenue_rows: list[dict[str, str]],
    gap_rows: list[dict[str, str]],
    fetch_errors: list[dict[str, str]],
    start: date,
    end: date,
) -> dict[str, Any]:
    expected = len(symbols) * len(periods)
    row_count = len({(row["symbol"], row["period"]) for row in revenue_rows})
    future_data_violations = count_future_data_violations(revenue_rows)
    coverage_ratio = row_count / expected if expected else 0.0
    blocking_issues: list[str] = []
    if not revenue_rows:
        blocking_issues.append("no_monthly_revenue_rows")
    if future_data_violations:
        blocking_issues.append("future_data_violation_detected")
    if coverage_ratio < 0.95:
        blocking_issues.append("coverage_below_95_percent")

    return {
        "ready": not blocking_issues,
        "source_mode": "point_in_time_limited",
        "date_start": start.isoformat(),
        "date_end": end.isoformat(),
        "period_start": periods[0] if periods else "",
        "period_end": periods[-1] if periods else "",
        "formal_universe_symbol_count": len(symbols),
        "expected_symbol_period_count": expected,
        "monthly_revenue_row_count": row_count,
        "coverage_ratio": round(coverage_ratio, 8),
        "missing_symbol_period_count": len(gap_rows),
        "future_data_violation_count": future_data_violations,
        "fetch_error_count": len(fetch_errors),
        "blocking_issues": blocking_issues,
        "source_notes": [
            "Revenue values come from MOPS static monthly revenue HTML and are converted from thousand TWD to TWD.",
            "MOPS historical static pages expose current render date, so v1 uses conservative market-available date: next month day 10, moved to the next weekday if needed.",
            "Rows are point-in-time usable only when available_date is on or before the replay snapshot date.",
        ],
    }


def count_future_data_violations(rows: list[dict[str, str]]) -> int:
    count = 0
    for row in rows:
        period_end = _period_end(row["period"])
        available = _parse_iso_date(row["available_date"])
        if available <= period_end:
            count += 1
    return count


def _fetch_period_html(
    *,
    source_url: str,
    cache_root: Path | None,
    period: str,
    market: str,
    company_type: int,
    force_fetch: bool,
    fetcher: TextFetcher,
    retry_attempts: int,
    retry_sleep_seconds: float,
) -> str:
    cache_path = None
    if cache_root:
        cache_path = cache_root / market / period / f"company_type_{company_type}.html"
        if cache_path.exists() and not force_fetch:
            return cache_path.read_text(encoding="utf-8")

    last_error: Exception | None = None
    for attempt in range(max(1, retry_attempts)):
        try:
            html = fetcher(source_url)
            if "營業收入統計表" not in html:
                raise SourceFetchError(f"MOPS response does not look like monthly revenue HTML: {source_url}")
            if cache_path:
                cache_path.parent.mkdir(parents=True, exist_ok=True)
                cache_path.write_text(html, encoding="utf-8")
            return html
        except (SourceFetchError, OSError) as exc:
            last_error = exc
            if attempt < retry_attempts - 1:
                time.sleep(retry_sleep_seconds)
                continue
    raise SourceFetchError(str(last_error) if last_error else f"Failed to fetch {source_url}")


def _read_revenue_rows(path: Path, periods: list[str]) -> list[dict[str, str]]:
    period_set = set(periods)
    rows: list[dict[str, str]] = []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            if row.get("period") in period_set:
                rows.append({key: str(row.get(key, "")).strip() for key in REVENUE_FIELDS})
    return rows


def _source_urls_from_revenue_rows(
    revenue_rows: list[dict[str, str]],
    symbols: list[FormalSymbol],
) -> dict[tuple[str, str], set[str]]:
    exchange_by_symbol = {symbol.symbol: symbol.exchange for symbol in symbols}
    output: dict[tuple[str, str], set[str]] = {}
    for row in revenue_rows:
        exchange = exchange_by_symbol.get(row["symbol"], "")
        if not exchange:
            continue
        output.setdefault((row["period"], exchange), set()).add(row["source_url"])
    return output


def _dedupe_and_sort_revenue_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    by_key: dict[tuple[str, str], dict[str, str]] = {}
    for row in rows:
        by_key[(row["symbol"], row["period"])] = row
    output = list(by_key.values())
    output.sort(key=lambda row: (row["symbol"], row["period"]))
    return output


def _write_rows(path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _parse_number(value: str) -> int | None:
    normalized = str(value).strip().replace(",", "")
    if normalized in {"", "-", "--", "nan", "None"}:
        return None
    try:
        return int(float(normalized))
    except ValueError:
        return None


def _parse_iso_date(value: str) -> date:
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError as exc:
        raise ValueError(f"Date must use YYYY-MM-DD format: {value}") from exc


def _period_end(period: str) -> date:
    year, month = [int(part) for part in period.split("-")]
    first_next = _add_months(date(year, month, 1), 1)
    return date.fromordinal(first_next.toordinal() - 1)


def _add_months(value: date, months: int) -> date:
    month_index = value.year * 12 + value.month - 1 + months
    year = month_index // 12
    month = month_index % 12 + 1
    return date(year, month, 1)


def _normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", value.replace("\xa0", " ")).strip()


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()
