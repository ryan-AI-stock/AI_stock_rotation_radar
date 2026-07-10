from __future__ import annotations

import csv
import hashlib
import json
import re
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import date, datetime, timezone
from html.parser import HTMLParser
from pathlib import Path


TASK_ID = "TASK-RADAR-DATA-VNEXT-6806-SHINFOX-LONG-REVENUE-STABILITY-SOURCE-PACKAGE-001"
BASE = Path(__file__).resolve().parent
TICKER = "6806"
NAME = "森崴能源"
MARKET_CODE = "pub"
MARKET = "MOPS_PUB"
START_PERIOD = "2021-01"
END_PERIOD = "2026-06"
BASE_URL = "https://mopsov.twse.com.tw/nas/t21/{market}/t21sc03_{roc_year}_{month}_{company_type}.html"
AJAX_URL = "https://mopsov.twse.com.tw/mops/web/ajax_t05st10_ifrs"
RUN_TS = datetime.now(timezone.utc).isoformat()


class HTMLTableParser(HTMLParser):
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
            self._current_row.append(normalize_text("".join(self._current_cell)))
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


@dataclass(frozen=True)
class FetchJob:
    period: str
    company_type: int

    @property
    def url(self) -> str:
        year, month = self.period.split("-")
        return BASE_URL.format(
            market=MARKET_CODE,
            roc_year=int(year) - 1911,
            month=int(month),
            company_type=self.company_type,
        )

    @property
    def cache_id(self) -> str:
        return f"mops_t21sc03_{MARKET_CODE}_{self.period}_type{self.company_type}"


def normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", value.replace("\xa0", " ")).strip()


def periods(start: str, end: str) -> list[str]:
    year, month = [int(part) for part in start.split("-")]
    end_year, end_month = [int(part) for part in end.split("-")]
    out: list[str] = []
    while (year, month) <= (end_year, end_month):
        out.append(f"{year:04d}-{month:02d}")
        month += 1
        if month > 12:
            year += 1
            month = 1
    return out


def conservative_available_date(period: str) -> date:
    year, month = [int(part) for part in period.split("-")]
    month += 1
    if month > 12:
        year += 1
        month = 1
    available = date(year, month, 10)
    while available.weekday() >= 5:
        available = date.fromordinal(available.toordinal() + 1)
    return available


def parse_number(value: str) -> int | None:
    text = value.replace(",", "").replace("--", "").strip()
    if not text:
        return None
    try:
        return int(float(text))
    except ValueError:
        return None


def strip_tags(value: str) -> str:
    return normalize_text(re.sub(r"<[^>]+>", " ", value).replace("&nbsp;", " "))


def fetch(job: FetchJob) -> tuple[dict[str, object], bytes | None]:
    request = urllib.request.Request(
        job.url,
        headers={
            "User-Agent": "Mozilla/5.0",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=8) as response:
            raw = response.read()
            status_code = getattr(response, "status", 200)
            content_type = response.headers.get("content-type", "")
        return {
            "cache_id": job.cache_id,
            "period": job.period,
            "market": MARKET,
            "source_market_code": MARKET_CODE,
            "company_type": job.company_type,
            "source_url": job.url,
            "http_code": status_code,
            "content_type": content_type,
            "response_sha256": hashlib.sha256(raw).hexdigest(),
            "response_bytes": len(raw),
            "retrieved_at": RUN_TS,
            "status": "fetched",
            "error": "",
        }, raw
    except Exception as exc:  # noqa: BLE001
        return {
            "cache_id": job.cache_id,
            "period": job.period,
            "market": MARKET,
            "source_market_code": MARKET_CODE,
            "company_type": job.company_type,
            "source_url": job.url,
            "http_code": "",
            "content_type": "",
            "response_sha256": "",
            "response_bytes": 0,
            "retrieved_at": RUN_TS,
            "status": "fetch_failed",
            "error": repr(exc),
        }, None


def fetch_ajax(period: str) -> tuple[dict[str, object], bytes | None]:
    year, month = period.split("-")
    roc_year = str(int(year) - 1911)
    payload = {
        "step": "1",
        "firstin": "ture",
        "off": "1",
        "keyword4": "",
        "code1": "",
        "TYPEK2": "",
        "checkbtn": "",
        "queryName": "co_id",
        "inpuType": "co_id",
        "TYPEK": "all",
        "isnew": "false",
        "co_id": TICKER,
        "year": roc_year,
        "month": month,
    }
    encoded = urllib.parse.urlencode(payload).encode("utf-8")
    request = urllib.request.Request(
        AJAX_URL,
        data=encoded,
        headers={
            "User-Agent": "Mozilla/5.0",
            "Accept": "text/html, */*; q=0.01",
            "Accept-Language": "zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7",
            "Content-Type": "application/x-www-form-urlencoded",
            "Referer": "https://mopsov.twse.com.tw/mops/web/t05st10_ifrs",
        },
        method="POST",
    )
    cache_id = f"mops_ajax_t05st10_ifrs_{TICKER}_{period}"
    try:
        with urllib.request.urlopen(request, timeout=8) as response:
            raw = response.read()
            status_code = getattr(response, "status", 200)
            content_type = response.headers.get("content-type", "")
        return {
            "cache_id": cache_id,
            "period": period,
            "market": MARKET,
            "source_market_code": MARKET_CODE,
            "company_type": "company_specific",
            "source_url": AJAX_URL,
            "post_payload_sanitized": f"co_id={TICKER};year={roc_year};month={month};TYPEK=all;isnew=false",
            "http_code": status_code,
            "content_type": content_type,
            "response_sha256": hashlib.sha256(raw).hexdigest(),
            "response_bytes": len(raw),
            "retrieved_at": RUN_TS,
            "status": "fetched",
            "error": "",
        }, raw
    except Exception as exc:  # noqa: BLE001
        return {
            "cache_id": cache_id,
            "period": period,
            "market": MARKET,
            "source_market_code": MARKET_CODE,
            "company_type": "company_specific",
            "source_url": AJAX_URL,
            "post_payload_sanitized": f"co_id={TICKER};year={roc_year};month={month};TYPEK=all;isnew=false",
            "http_code": "",
            "content_type": "",
            "response_sha256": "",
            "response_bytes": 0,
            "retrieved_at": RUN_TS,
            "status": "fetch_failed",
            "error": repr(exc),
        }, None


def parse_6806(job: FetchJob, raw: bytes | None) -> tuple[list[dict[str, object]], str, str]:
    if not raw:
        return [], "no_raw_response", ""
    text = raw.decode("big5", errors="replace")
    if "營業收入統計表" not in text:
        return [], "not_monthly_revenue_html", ""
    parser = HTMLTableParser()
    parser.feed(text)
    available = conservative_available_date(job.period).isoformat()
    rows: list[dict[str, object]] = []
    matched_cells = ""
    for cells in parser.rows:
        if len(cells) < 3:
            continue
        if cells[0].strip() != TICKER:
            continue
        value_thousand_twd = parse_number(cells[2])
        if value_thousand_twd is None:
            return [], "matched_row_revenue_parse_failed", " | ".join(cells[:8])
        matched_cells = " | ".join(cells[:8])
        rows.append(
            {
                "ticker": TICKER,
                "name": cells[1].strip() or NAME,
                "market": MARKET,
                "source_market_code": MARKET_CODE,
                "revenue_year_month": job.period,
                "revenue_value": value_thousand_twd * 1000,
                "revenue_unit": "TWD",
                "source_date": available,
                "release_date": available,
                "available_date": available,
                "source_url": job.url,
                "source_route": f"mops_static_t21sc03/{MARKET_CODE}/company_type_{job.company_type}",
                "source_type": "mops_monthly_revenue_static_html_conservative_available_date",
                "formal_exact": "false",
                "pit_usable": "true",
                "source_quality": "official_higher_quality_diagnostic_pit_candidate",
                "accepted_for_formal": "false",
                "human_review_required": "false",
                "ingested_at": RUN_TS,
                "notes": "MOPS monthly revenue value converted from thousand TWD to TWD; available_date uses conservative next-month day 10 weekday-adjusted rule.",
            }
        )
    return rows, "matched" if rows else "ticker_not_in_page", matched_cells


def parse_ajax_6806(period: str, raw: bytes | None) -> tuple[list[dict[str, object]], str, str]:
    if not raw:
        return [], "no_raw_response", ""
    text = raw.decode("utf-8", errors="replace")
    if TICKER not in text and NAME not in text:
        return [], "ticker_not_in_ajax_response", ""
    parser = HTMLTableParser()
    parser.feed(text)
    value_thousand_twd: int | None = None
    note = ""
    matched_cells = ""
    note_match = re.search(r"備註\s*/\s*營收變化原因說明.*?<TD[^>]*>(.*?)</TD>", text, flags=re.S)
    if note_match:
        note = strip_tags(note_match.group(1))
    for cells in parser.rows:
        if len(cells) < 2:
            continue
        label = cells[0].strip()
        if label == "本月":
            value_thousand_twd = parse_number(cells[1])
            matched_cells = " | ".join(cells[:4])
        elif "備註" in label and len(cells) > 1:
            note = cells[1].strip()
    if value_thousand_twd is None:
        return [], "ajax_monthly_revenue_parse_failed", matched_cells
    available = conservative_available_date(period).isoformat()
    return [
        {
            "ticker": TICKER,
            "name": NAME,
            "market": MARKET,
            "source_market_code": MARKET_CODE,
            "revenue_year_month": period,
            "revenue_value": value_thousand_twd * 1000,
            "revenue_unit": "TWD",
            "source_date": available,
            "release_date": available,
            "available_date": available,
            "source_url": AJAX_URL,
            "source_route": "mops_ajax_t05st10_ifrs/pub/company_specific",
            "source_type": "mops_monthly_revenue_company_specific_ajax_conservative_available_date",
            "formal_exact": "false",
            "pit_usable": "true",
            "source_quality": "official_higher_quality_diagnostic_pit_candidate",
            "accepted_for_formal": "false",
            "human_review_required": "false",
            "ingested_at": RUN_TS,
            "notes": f"MOPS company-specific monthly revenue value converted from thousand TWD to TWD; available_date uses conservative next-month day 10 weekday-adjusted rule.; revenue_change_note={note}",
        }
    ], "matched", matched_cells


def future_data_violations(rows: list[dict[str, object]]) -> int:
    count = 0
    for row in rows:
        year, month = [int(part) for part in str(row["revenue_year_month"]).split("-")]
        next_month = month + 1
        next_year = year
        if next_month > 12:
            next_year += 1
            next_month = 1
        period_end = date.fromordinal(date(next_year, next_month, 1).toordinal() - 1)
        available = date.fromisoformat(str(row["available_date"]))
        if available <= period_end:
            count += 1
    return count


def write_csv(path: Path, rows: list[dict[str, object]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fields})


def main() -> None:
    BASE.mkdir(parents=True, exist_ok=True)
    (BASE / "raw_cache").mkdir(parents=True, exist_ok=True)
    (BASE / "raw_cache" / ".gitignore").write_text("*\n!.gitignore\n", encoding="utf-8")
    (BASE / "current_step.txt").write_text("running_6806_monthly_revenue_bounded_fetch", encoding="utf-8")

    rows: list[dict[str, object]] = []
    cache_manifest: list[dict[str, object]] = []
    attempt_rows: list[dict[str, object]] = []
    requested_periods = periods(START_PERIOD, END_PERIOD)
    for idx, period in enumerate(requested_periods, start=1):
        (BASE / "current_step.txt").write_text(
            f"fetching_period {idx}/{len(requested_periods)} {period}",
            encoding="utf-8",
        )
        period_rows: list[dict[str, object]] = []
        for company_type in (0, 1):
            job = FetchJob(period=period, company_type=company_type)
            cache_row, raw = fetch(job)
            parsed, parse_status, matched_cells = parse_6806(job, raw)
            cache_row["parse_status"] = parse_status
            cache_row["matched_cells_excerpt"] = matched_cells
            cache_manifest.append(cache_row)
            attempt_rows.append(cache_row)
            period_rows.extend(parsed)
            write_csv(
                BASE / "6806_monthly_revenue_source_manifest.partial.csv",
                cache_manifest,
                [
                    "cache_id",
                    "period",
                    "market",
                    "source_market_code",
                    "company_type",
                    "source_url",
                    "http_code",
                    "content_type",
                    "response_sha256",
                    "response_bytes",
                    "retrieved_at",
                    "status",
                    "parse_status",
                    "matched_cells_excerpt",
                    "error",
                ],
            )
        if period_rows:
            rows.append(period_rows[0])
            write_csv(
                BASE / "6806_monthly_revenue_rows.partial.csv",
                rows,
                [
                    "ticker",
                    "name",
                    "market",
                    "source_market_code",
                    "revenue_year_month",
                    "revenue_value",
                    "revenue_unit",
                    "source_date",
                    "release_date",
                    "available_date",
                    "source_url",
                    "source_route",
                    "source_type",
                    "formal_exact",
                    "pit_usable",
                    "source_quality",
                    "accepted_for_formal",
                    "human_review_required",
                    "ingested_at",
                    "notes",
                ],
            )

    static_covered = {str(row["revenue_year_month"]) for row in rows}
    for idx, period in enumerate([p for p in requested_periods if p not in static_covered], start=1):
        (BASE / "current_step.txt").write_text(
            f"fetching_ajax_gap {idx}/{len(requested_periods) - len(static_covered)} {period}",
            encoding="utf-8",
        )
        cache_row, raw = fetch_ajax(period)
        parsed, parse_status, matched_cells = parse_ajax_6806(period, raw)
        cache_row["parse_status"] = parse_status
        cache_row["matched_cells_excerpt"] = matched_cells
        cache_manifest.append(cache_row)
        attempt_rows.append(cache_row)
        if parsed:
            rows.extend(parsed)
            rows = sorted(rows, key=lambda row: str(row["revenue_year_month"]))
            write_csv(
                BASE / "6806_monthly_revenue_rows.partial.csv",
                rows,
                [
                    "ticker",
                    "name",
                    "market",
                    "source_market_code",
                    "revenue_year_month",
                    "revenue_value",
                    "revenue_unit",
                    "source_date",
                    "release_date",
                    "available_date",
                    "source_url",
                    "source_route",
                    "source_type",
                    "formal_exact",
                    "pit_usable",
                    "source_quality",
                    "accepted_for_formal",
                    "human_review_required",
                    "ingested_at",
                    "notes",
                ],
            )
        write_csv(
            BASE / "6806_monthly_revenue_source_manifest.partial.csv",
            cache_manifest,
            [
                "cache_id",
                "period",
                "market",
                "source_market_code",
                "company_type",
                "source_url",
                "post_payload_sanitized",
                "http_code",
                "content_type",
                "response_sha256",
                "response_bytes",
                "retrieved_at",
                "status",
                "parse_status",
                "matched_cells_excerpt",
                "error",
            ],
        )

    expected = requested_periods
    covered = {str(row["revenue_year_month"]) for row in rows}
    missing_rows = [
        {
            "ticker": TICKER,
            "name": NAME,
            "market": MARKET,
            "source_market_code": MARKET_CODE,
            "revenue_year_month": period,
            "missing_reason": "ticker_not_found_in_bounded_static_or_company_specific_ajax_mops_routes",
            "source_route_checked": "mops_static_t21sc03/pub/company_type_0_and_1; mops_ajax_t05st10_ifrs/pub/company_specific; sample route probe found 6806 in pub not sii/otc/rotc for 2026-05",
        }
        for period in expected
        if period not in covered
    ]
    future_count = future_data_violations(rows)

    revenue_fields = [
        "ticker",
        "name",
        "market",
        "source_market_code",
        "revenue_year_month",
        "revenue_value",
        "revenue_unit",
        "source_date",
        "release_date",
        "available_date",
        "source_url",
        "source_route",
        "source_type",
        "formal_exact",
        "pit_usable",
        "source_quality",
        "accepted_for_formal",
        "human_review_required",
        "ingested_at",
        "notes",
    ]
    write_csv(BASE / "6806_monthly_revenue_rows.csv", rows, revenue_fields)
    write_csv(
        BASE / "6806_monthly_revenue_source_manifest.csv",
        cache_manifest,
        [
            "cache_id",
            "period",
            "market",
            "source_market_code",
            "company_type",
            "source_url",
            "post_payload_sanitized",
            "http_code",
            "content_type",
            "response_sha256",
            "response_bytes",
            "retrieved_at",
            "status",
            "parse_status",
            "matched_cells_excerpt",
            "error",
        ],
    )
    write_csv(
        BASE / "6806_monthly_revenue_missing_months.csv",
        missing_rows,
        ["ticker", "name", "market", "source_market_code", "revenue_year_month", "missing_reason", "source_route_checked"],
    )
    coverage = [
        {
            "ticker": TICKER,
            "name": NAME,
            "market": MARKET,
            "source_market_code": MARKET_CODE,
            "coverage_start": min(covered) if covered else "",
            "coverage_end": max(covered) if covered else "",
            "requested_start": START_PERIOD,
            "requested_end": END_PERIOD,
            "accepted_rows": len(rows),
            "requested_months": len(expected),
            "missing_months": len(missing_rows),
            "source": "MOPS t21sc03 official static monthly revenue HTML pub route plus ajax_t05st10_ifrs company-specific gap fill",
            "source_quality": "official_higher_quality_diagnostic_pit_candidate",
            "formal_exact": "false",
            "accepted_for_formal": "false",
            "future_data_violation_count": future_count,
        }
    ]
    write_csv(
        BASE / "6806_monthly_revenue_coverage_audit.csv",
        coverage,
        [
            "ticker",
            "name",
            "market",
            "source_market_code",
            "coverage_start",
            "coverage_end",
            "requested_start",
            "requested_end",
            "accepted_rows",
            "requested_months",
            "missing_months",
            "source",
            "source_quality",
            "formal_exact",
            "accepted_for_formal",
            "future_data_violation_count",
        ],
    )
    future_audit = [
        {
            "dataset": "6806_monthly_revenue",
            "future_data_violation_count": future_count,
            "asof_policy": "conservative next-month day 10 weekday-adjusted available_date; not per-company exact filing timestamp",
            "period_end_as_available_date": "prohibited",
            "query_response_datetime_as_available_date": "prohibited",
        }
    ]
    write_csv(
        BASE / "6806_monthly_revenue_future_data_audit.csv",
        future_audit,
        [
            "dataset",
            "future_data_violation_count",
            "asof_policy",
            "period_end_as_available_date",
            "query_response_datetime_as_available_date",
        ],
    )
    blocked = []
    if missing_rows:
        blocked.append(
            {
                "blocked_item": "missing_months",
                "blocked_count": len(missing_rows),
                "blocked_reason": "6806 not present in requested MOPS static pub monthly page or company-specific ajax route for remaining month(s)",
                "next_source_route": "If Core requires the latest missing month, wait for official MOPS monthly revenue publication or probe MOPS material-information announcement route; do not use query time as available date.",
            }
        )
    write_csv(
        BASE / "6806_monthly_revenue_blocked_ledger.csv",
        blocked,
        ["blocked_item", "blocked_count", "blocked_reason", "next_source_route"],
    )

    ready = bool(rows) and future_count == 0
    readiness = {
        "task_id": TASK_ID,
        "status": "completed_source_package_ready_for_core_ingest" if ready else "blocked_no_official_monthly_revenue_rows",
        "ticker": TICKER,
        "name": NAME,
        "source": "MOPS official t21sc03 monthly revenue static HTML pub route plus ajax_t05st10_ifrs company-specific gap fill",
        "source_market_code": MARKET_CODE,
        "coverage_start": min(covered) if covered else "",
        "coverage_end": max(covered) if covered else "",
        "accepted_rows": len(rows),
        "requested_months": len(expected),
        "missing_months": len(missing_rows),
        "future_data_violation_count": future_count,
        "ready_for_core_6806_long_revenue_stability_ingest": ready,
        "ready_for_core_rerun": ready,
        "ready_for_strategy_replay": False,
        "ready_for_formal": False,
        "formal_model_changed": False,
        "trade_decision_changed": False,
        "active_in_trade_decision": False,
        "report_changed": False,
        "portfolio_replay_executed": False,
        "not_live_rule": True,
        "forward_returns_live_rule_usage": False,
        "source_type_boundary": "diagnostic PIT candidate; conservative available_date only, not per-company exact filing timestamp; accepted_for_formal=false",
        "blocked_reason": "" if ready else "no official 6806 rows parsed from bounded MOPS t21sc03 pub route",
    }
    (BASE / "readiness_for_core_6806_long_revenue_stability_ingest.json").write_text(
        json.dumps(readiness, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    artifacts = [
        "6806_monthly_revenue_rows.csv",
        "6806_monthly_revenue_source_manifest.csv",
        "6806_monthly_revenue_missing_months.csv",
        "6806_monthly_revenue_coverage_audit.csv",
        "6806_monthly_revenue_blocked_ledger.csv",
        "6806_monthly_revenue_future_data_audit.csv",
        "readiness_for_core_6806_long_revenue_stability_ingest.json",
        "manifest.json",
        "final_summary_zh.md",
    ]
    manifest = {
        "task_id": TASK_ID,
        "generated_at": RUN_TS,
        "output_path": str(BASE),
        "artifacts": artifacts,
        "flags": {
            "formal_model_changed": False,
            "trade_decision_changed": False,
            "active_in_trade_decision": False,
            "report_changed": False,
            "portfolio_replay_executed": False,
            "ready_for_strategy_replay": False,
            "ready_for_formal": False,
            "not_live_rule": True,
            "forward_returns_live_rule_usage": False,
        },
    }
    (BASE / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    summary = f"""# 6806 森崴能源 long revenue source package

## 結論

- 已完成 bounded source package，只針對 6806 森崴能源。
- source: MOPS official t21sc03 monthly revenue static HTML `pub` route + `ajax_t05st10_ifrs` company-specific gap fill。
- coverage: {min(covered) if covered else ''} 到 {max(covered) if covered else ''}。
- accepted rows: {len(rows)}。
- missing months: {len(missing_rows)}。
- future_data_violation_count={future_count}。
- ready_for_core_6806_long_revenue_stability_ingest={str(ready).lower()}。

## PIT / asof policy

- available_date 使用保守口徑：營收月份次月 10 日，遇週末順延。
- 不使用 revenue period end date 當 available_date。
- 不使用 retrieval time / query response datetime 當 available_date。
- 這是 official higher-quality diagnostic PIT candidate，不是 formal exact filing timestamp。

## 邊界

- formal_model_changed=false
- trade_decision_changed=false
- active_in_trade_decision=false
- report_changed=false
- portfolio_replay_executed=false
- ready_for_strategy_replay=false
- ready_for_formal=false
- not_live_rule=true
- forward_returns_live_rule_usage=false

## 下一棒

交 Core/Data absorb 6806 monthly revenue rows，刷新 6806 sanity check：long revenue stability / revenue lumpiness / project-based risk proxy。注意 source_market_code=pub，不可假裝成 TWSE listed-company t21sc03 route。
完成後如果下一棒明確，請直接指派下一個 thread；如果下一棒不明確，請回報 Strategy Center 判斷。不要完成後停住不回報。
"""
    (BASE / "final_summary_zh.md").write_text(summary, encoding="utf-8")
    (BASE / "current_step.txt").write_text("completed", encoding="utf-8")


if __name__ == "__main__":
    main()
