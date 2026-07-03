from __future__ import annotations

import csv
import json
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import date, datetime, timezone
from html.parser import HTMLParser
from pathlib import Path

try:
    import requests
except Exception:  # pragma: no cover
    requests = None


TASK_ID = "TASK-RADAR-DATA-DYNAMIC-POOL1-MOPS-MONTHLY-REVENUE-FULL-UNIVERSE-PIT-20260703"
BASE = Path("outputs/radar_dynamic_pool1_mops_monthly_revenue_full_universe_pit_20260703")
CORE_READINESS = Path(
    r"C:\Users\zergv\Documents\Codex\2026-05-30\ep05-chat-ai-stock-backtest-lab\outputs\dynamic_pool1_pit_readiness_after_tpex_transition_candidates_20260703"
)
PREVIOUS_SOURCE_PACKAGE = Path("outputs/radar_dynamic_pool1_pit_source_acquisition_20260703")
RUN_TS = datetime.now(timezone.utc).isoformat()
START_PERIOD = "2015-01"
END_PERIOD = "2026-05"
BASE_URL = "https://mopsov.twse.com.tw/nas/t21/{market}/t21sc03_{roc_year}_{month}_{company_type}.html"
MARKETS = {"sii": "TWSE", "otc": "TPEx"}
COMPANY_TYPES = (0, 1)
MAX_WORKERS = 8

ATTEMPT_FIELDS = [
    "attempt_id",
    "market",
    "company_type",
    "period",
    "url",
    "http_code",
    "content_type",
    "status",
    "row_count",
    "error",
]

REVENUE_FIELDS = [
    "ticker",
    "name",
    "market",
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
    "ingested_at",
    "notes",
]


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
    market_code: str
    company_type: int

    @property
    def market(self) -> str:
        return MARKETS[self.market_code]

    @property
    def url(self) -> str:
        year, month = self.period.split("-")
        return BASE_URL.format(
            market=self.market_code,
            roc_year=int(year) - 1911,
            month=int(month),
            company_type=self.company_type,
        )

    @property
    def attempt_id(self) -> str:
        return f"{self.market_code}_{self.period}_{self.company_type}"


def ensure_base() -> None:
    BASE.mkdir(parents=True, exist_ok=True)


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


def fetch_job(job: FetchJob) -> tuple[dict[str, object], list[dict[str, object]]]:
    if requests is None:
        return attempt_row(job, "failed", error="requests_unavailable"), []
    try:
        response = requests.get(
            job.url,
            headers={
                "User-Agent": "Mozilla/5.0",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7",
            },
            timeout=30,
        )
        raw = response.content
        text = raw.decode("big5", errors="replace")
        content_type = response.headers.get("content-type", "")
        if response.status_code != 200:
            return attempt_row(job, "failed", response.status_code, content_type, error=f"http_{response.status_code}"), []
        if "營業收入統計表" not in text:
            return attempt_row(job, "empty", response.status_code, content_type, error="not_monthly_revenue_html"), []
        rows = parse_revenue_html(text, job)
        return attempt_row(job, "ok" if rows else "empty", response.status_code, content_type, len(rows)), rows
    except Exception as exc:  # noqa: BLE001
        return attempt_row(job, "failed", error=repr(exc)), []


def attempt_row(
    job: FetchJob,
    status: str,
    http_code: int | str = "",
    content_type: str = "",
    row_count: int = 0,
    error: str = "",
) -> dict[str, object]:
    return {
        "attempt_id": job.attempt_id,
        "market": job.market,
        "company_type": job.company_type,
        "period": job.period,
        "url": job.url,
        "http_code": http_code,
        "content_type": content_type,
        "status": status,
        "row_count": row_count,
        "error": error,
    }


def parse_revenue_html(html: str, job: FetchJob) -> list[dict[str, object]]:
    parser = HTMLTableParser()
    parser.feed(html)
    available = conservative_available_date(job.period).isoformat()
    rows: list[dict[str, object]] = []
    for cells in parser.rows:
        if len(cells) < 3:
            continue
        ticker = cells[0].strip()
        if not re.fullmatch(r"\d{4}", ticker):
            continue
        value_thousand_twd = parse_number(cells[2])
        if value_thousand_twd is None:
            continue
        rows.append(
            {
                "ticker": ticker,
                "name": cells[1].strip(),
                "market": job.market,
                "revenue_year_month": job.period,
                "revenue_value": value_thousand_twd * 1000,
                "revenue_unit": "TWD",
                "source_date": available,
                "release_date": available,
                "available_date": available,
                "source_url": job.url,
                "source_route": f"mops_static_t21sc03/{job.market_code}/company_type_{job.company_type}",
                "source_type": "mops_monthly_revenue_static_html_conservative_available_date",
                "formal_exact": "false",
                "pit_usable": "true",
                "ingested_at": RUN_TS,
                "notes": "MOPS monthly revenue value converted from thousand TWD to TWD; available_date uses conservative next-month day 10 weekday-adjusted rule.",
            }
        )
    return rows


def write_csv(path: Path, rows: list[dict[str, object]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fields})


def write_revenue_shards(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    shard_dir = BASE / "accepted_monthly_revenue_rows_shards"
    shard_dir.mkdir(parents=True, exist_ok=True)
    for stale in shard_dir.glob("accepted_monthly_revenue_rows_*.csv"):
        stale.unlink()
    by_year: dict[str, list[dict[str, object]]] = {}
    for row in rows:
        year = str(row["revenue_year_month"])[:4]
        by_year.setdefault(year, []).append(row)
    manifest: list[dict[str, object]] = []
    for year in sorted(by_year):
        shard_rows = by_year[year]
        shard_path = shard_dir / f"accepted_monthly_revenue_rows_{year}.csv"
        write_csv(shard_path, shard_rows, REVENUE_FIELDS)
        manifest.append(
            {
                "shard_file": str(shard_path.relative_to(BASE)).replace("\\", "/"),
                "year": year,
                "rows": len(shard_rows),
                "symbol_count": len({row["ticker"] for row in shard_rows}),
                "period_start": min(row["revenue_year_month"] for row in shard_rows),
                "period_end": max(row["revenue_year_month"] for row in shard_rows),
            }
        )
    write_csv(BASE / "accepted_monthly_revenue_rows.csv", manifest, ["shard_file", "year", "rows", "symbol_count", "period_start", "period_end"])
    write_csv(BASE / "accepted_monthly_revenue_rows_manifest.csv", manifest, ["shard_file", "year", "rows", "symbol_count", "period_start", "period_end"])
    write_csv(BASE / "accepted_monthly_revenue_rows_sample.csv", rows[:1000], REVENUE_FIELDS)
    return manifest


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def dedupe_rows(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    deduped: dict[tuple[str, str, str], dict[str, object]] = {}
    for row in rows:
        key = (str(row["ticker"]), str(row["market"]), str(row["revenue_year_month"]))
        deduped[key] = row
    return sorted(deduped.values(), key=lambda r: (str(r["revenue_year_month"]), str(r["market"]), str(r["ticker"])))


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


def build_coverage(rows: list[dict[str, object]], attempts: list[dict[str, object]]) -> tuple[list[dict[str, object]], list[dict[str, object]], list[dict[str, object]]]:
    by_period_market: dict[tuple[str, str], set[str]] = defaultdict_set()
    for row in rows:
        by_period_market[(str(row["revenue_year_month"]), str(row["market"]))].add(str(row["ticker"]))
    attempt_by_period_market: dict[tuple[str, str], list[dict[str, object]]] = defaultdict_list()
    for row in attempts:
        attempt_by_period_market[(str(row["period"]), str(row["market"]))].append(row)

    coverage_month: list[dict[str, object]] = []
    blocked: list[dict[str, object]] = []
    for period in periods(START_PERIOD, END_PERIOD):
        for market in ("TWSE", "TPEx"):
            attempt_rows = attempt_by_period_market.get((period, market), [])
            failed = sum(1 for row in attempt_rows if row.get("status") == "failed")
            ok = sum(1 for row in attempt_rows if row.get("status") == "ok")
            ticker_count = len(by_period_market.get((period, market), set()))
            coverage_status = "accepted" if ticker_count > 0 and failed == 0 else "partial_or_blocked"
            coverage_month.append(
                {
                    "revenue_year_month": period,
                    "market": market,
                    "ticker_count": ticker_count,
                    "route_attempts": len(attempt_rows),
                    "ok_attempts": ok,
                    "failed_attempts": failed,
                    "coverage_status": coverage_status,
                }
            )
            if failed or ticker_count == 0:
                blocked.append(
                    {
                        "dataset": "monthly_revenue_pit",
                        "revenue_year_month": period,
                        "market": market,
                        "blocked_reason": "route_failed_or_zero_rows",
                        "attempt_count": len(attempt_rows),
                        "failed_attempts": failed,
                        "next_programmatic_source": "Retry MOPS t21sc03 static route or probe ajax_t21sc03 if static HTML unavailable.",
                    }
                )
    market_rows: list[dict[str, object]] = []
    for market in ("TWSE", "TPEx"):
        market_source_rows = [row for row in rows if row["market"] == market]
        market_rows.append(
            {
                "market": market,
                "accepted_rows": len(market_source_rows),
                "symbol_count": len({row["ticker"] for row in market_source_rows}),
                "period_start": min((row["revenue_year_month"] for row in market_source_rows), default=""),
                "period_end": max((row["revenue_year_month"] for row in market_source_rows), default=""),
            }
        )
    return coverage_month, market_rows, blocked


def defaultdict_set():
    from collections import defaultdict

    return defaultdict(set)


def defaultdict_list():
    from collections import defaultdict

    return defaultdict(list)


def append_log(status: str, details: str) -> None:
    path = BASE / "run_log.csv"
    if not path.exists():
        write_csv(path, [], ["timestamp", "status", "details"])
    with path.open("a", encoding="utf-8", newline="") as handle:
        csv.writer(handle).writerow([datetime.now(timezone.utc).isoformat(), status, details])


def run() -> dict[str, object]:
    ensure = BASE
    ensure.mkdir(parents=True, exist_ok=True)
    (BASE / "current_step.txt").write_text("running_mops_t21sc03_full_universe_sweep", encoding="utf-8")
    append_log("running", f"period={START_PERIOD}..{END_PERIOD}; markets=TWSE,TPEx; company_types=0,1")

    jobs = [FetchJob(period=p, market_code=m, company_type=t) for p in periods(START_PERIOD, END_PERIOD) for m in MARKETS for t in COMPANY_TYPES]
    attempts: list[dict[str, object]] = []
    revenue_rows: list[dict[str, object]] = []
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures = {pool.submit(fetch_job, job): job for job in jobs}
        done = 0
        for future in as_completed(futures):
            attempt, rows = future.result()
            attempts.append(attempt)
            revenue_rows.extend(rows)
            done += 1
            if done % 50 == 0:
                append_log("progress", f"completed_requests={done}/{len(jobs)}")
                time.sleep(0.1)

    revenue_rows = dedupe_rows(revenue_rows)
    attempts = sorted(attempts, key=lambda r: (str(r["period"]), str(r["market"]), str(r["company_type"])))
    coverage_month, coverage_market, blocked_rows = build_coverage(revenue_rows, attempts)
    future_count = future_data_violations(revenue_rows)
    failed_attempts = sum(1 for row in attempts if row["status"] == "failed")
    accepted_month_market = sum(1 for row in coverage_month if row["coverage_status"] == "accepted")
    expected_month_market = len(coverage_month)
    full_ready = bool(revenue_rows) and failed_attempts == 0 and accepted_month_market == expected_month_market and future_count == 0
    partial_ready = bool(revenue_rows) and future_count == 0

    write_csv(BASE / "download_attempts.csv", attempts, ATTEMPT_FIELDS)
    revenue_shards = write_revenue_shards(revenue_rows)
    write_csv(
        BASE / "rejected_or_blocked_rows.csv",
        blocked_rows,
        ["dataset", "revenue_year_month", "market", "blocked_reason", "attempt_count", "failed_attempts", "next_programmatic_source"],
    )
    write_csv(
        BASE / "coverage_by_year_month.csv",
        coverage_month,
        ["revenue_year_month", "market", "ticker_count", "route_attempts", "ok_attempts", "failed_attempts", "coverage_status"],
    )
    write_csv(BASE / "coverage_by_market.csv", coverage_market, ["market", "accepted_rows", "symbol_count", "period_start", "period_end"])
    write_csv(
        BASE / "source_manifest.csv",
        [
            {
                "source_id": "mops_static_t21sc03_sii",
                "source_name": "MOPS TWSE monthly revenue static HTML",
                "source_url_pattern": "https://mopsov.twse.com.tw/nas/t21/sii/t21sc03_{roc_year}_{month}_{company_type}.html",
                "market": "TWSE",
                "source_type": "official_static_html_conservative_available_date",
                "coverage": f"{START_PERIOD}..{END_PERIOD}",
                "release_date_available": "conservative_available_date_next_month_10_weekday_adjusted",
                "formal_exact": "false",
            },
            {
                "source_id": "mops_static_t21sc03_otc",
                "source_name": "MOPS TPEx monthly revenue static HTML",
                "source_url_pattern": "https://mopsov.twse.com.tw/nas/t21/otc/t21sc03_{roc_year}_{month}_{company_type}.html",
                "market": "TPEx",
                "source_type": "official_static_html_conservative_available_date",
                "coverage": f"{START_PERIOD}..{END_PERIOD}",
                "release_date_available": "conservative_available_date_next_month_10_weekday_adjusted",
                "formal_exact": "false",
            },
        ],
        ["source_id", "source_name", "source_url_pattern", "market", "source_type", "coverage", "release_date_available", "formal_exact"],
    )
    (BASE / "source_manifest.json").write_text(json.dumps(read_csv(BASE / "source_manifest.csv"), ensure_ascii=False, indent=2), encoding="utf-8")
    write_csv(
        BASE / "future_data_violation_audit.csv",
        [
            {
                "audit_item": "available_date_after_revenue_month",
                "result": "pass" if future_count == 0 else "fail",
                "future_data_violation_count": future_count,
                "evidence": "available_date/source_date/release_date use conservative next-month day 10 weekday-adjusted rule, never revenue-month end or current snapshot.",
            },
            {
                "audit_item": "current_snapshot_backfill",
                "result": "pass",
                "future_data_violation_count": 0,
                "evidence": "Rows are parsed from MOPS static historical monthly pages by period and market; no current company profile used.",
            },
            {
                "audit_item": "model_boundary",
                "result": "pass",
                "future_data_violation_count": 0,
                "evidence": "No BACKTEST_LAB formal model, selector, report, or trade decision changed.",
            },
        ],
        ["audit_item", "result", "future_data_violation_count", "evidence"],
    )

    readiness = {
        "task_id": TASK_ID,
        "status": "completed_full_universe_candidate" if full_ready else ("completed_partial_ready" if partial_ready else "blocked_no_accepted_rows"),
        "monthly_revenue_pit_full_universe_ready": full_ready,
        "monthly_revenue_pit_partial_ready": partial_ready,
        "output_path": str(BASE.resolve()),
        "core_readiness_input": str(CORE_READINESS),
        "previous_source_package": str(PREVIOUS_SOURCE_PACKAGE),
        "period_start": START_PERIOD,
        "period_end": END_PERIOD,
        "route_request_attempts": len(attempts),
        "failed_attempts": failed_attempts,
        "accepted_rows": len(revenue_rows),
        "symbol_count": len({row["ticker"] for row in revenue_rows}),
        "accepted_month_market": accepted_month_market,
        "expected_month_market": expected_month_market,
        "coverage_ratio_month_market": round(accepted_month_market / expected_month_market, 8) if expected_month_market else 0,
        "future_data_violation_count": future_count,
        "ready_for_core_rerun": partial_ready,
        "ready_for_strategy_replay": False,
        "formal_model_changed": False,
        "trade_decision_changed": False,
        "active_in_trade_decision": False,
        "source_type_boundary": "release/source dates are conservative available dates, not per-company actual filing timestamps; formal_exact=false",
        "remaining_blockers": [
            "Core must decide whether conservative next-month day 10 available_date is sufficient for Dynamic Pool1 PIT use.",
            "If exact per-company filing timestamps are required, next route is MOPS material information/announcement crawler by company/month.",
        ],
    }
    (BASE / "readiness_for_core.json").write_text(json.dumps(readiness, ensure_ascii=False, indent=2), encoding="utf-8")
    (BASE / "manifest.json").write_text(
        json.dumps(
            {
                "task_id": TASK_ID,
                "created_at_utc": RUN_TS,
                "status": readiness["status"],
                "outputs": [
                    "source_manifest.csv",
                    "source_manifest.json",
                    "download_attempts.csv",
                    "accepted_monthly_revenue_rows.csv",
                    "accepted_monthly_revenue_rows_manifest.csv",
                    "accepted_monthly_revenue_rows_sample.csv",
                    "accepted_monthly_revenue_rows_shards/",
                    "rejected_or_blocked_rows.csv",
                    "coverage_by_year_month.csv",
                    "coverage_by_market.csv",
                    "future_data_violation_audit.csv",
                    "readiness_for_core.json",
                    "final_summary_zh.md",
                ],
                "formal_model_changed": False,
                "trade_decision_changed": False,
                "active_in_trade_decision": False,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    write_csv(
        BASE / "completed.csv",
        [
            {"step": "mops_static_route_sweep", "status": "completed", "evidence": "download_attempts.csv"},
            {"step": "monthly_revenue_parse", "status": "completed", "evidence": f"accepted_monthly_revenue_rows_manifest.csv; shard_count={len(revenue_shards)}"},
            {"step": "coverage_and_readiness", "status": "completed", "evidence": "coverage_by_year_month.csv; readiness_for_core.json"},
        ],
        ["step", "status", "evidence"],
    )
    write_csv(
        BASE / "failed.csv",
        [
            {
                "step": "exact_per_company_release_timestamp",
                "status": "not_available_in_static_route",
                "reason": "Static historical monthly revenue pages do not expose exact per-company filing timestamp; using conservative available_date.",
            }
        ],
        ["step", "status", "reason"],
    )
    (BASE / "current_step.txt").write_text(str(readiness["status"]), encoding="utf-8")
    (BASE / "final_summary_zh.md").write_text(
        f"""# Dynamic Pool1 MOPS monthly revenue full-universe PIT

## 結論

狀態：`{readiness['status']}`。

本棒使用 MOPS official static monthly revenue route `t21sc03` 擴成 2015-01～2026-05 全市場候選資料包。accepted rows 以年度 shards 保存，`accepted_monthly_revenue_rows.csv` 是 shard index，避免單檔超過 GitHub 上限。

- accepted rows：{len(revenue_rows)}
- symbol count：{readiness['symbol_count']}
- route attempts：{len(attempts)}
- failed attempts：{failed_attempts}
- month-market coverage：{accepted_month_market}/{expected_month_market}
- `future_data_violation_count={future_count}`

## PIT 邊界

每筆 row 具 `source_date/release_date/available_date`，但日期是保守可用日：次月 10 日，若遇週末順延到下一個 weekday。這避免 future-data leakage，但不是逐公司精確申報時間；因此 `formal_exact=false`。

## Readiness

- `monthly_revenue_pit_full_universe_ready={str(full_ready).lower()}`
- `monthly_revenue_pit_partial_ready={str(partial_ready).lower()}`
- `ready_for_core_rerun={str(partial_ready).lower()}`
- `ready_for_strategy_replay=false`
- `formal_model_changed=false`
- `trade_decision_changed=false`
- `active_in_trade_decision=false`

## 下一步

交 Core 重跑 Dynamic Pool1 readiness。若 Core 要求 exact per-company filing timestamp，下一棒 Radar/Data 需走 MOPS material information / announcement crawler by company-month。
""",
        encoding="utf-8",
    )
    append_log("completed", json.dumps(readiness, ensure_ascii=False))
    return readiness


if __name__ == "__main__":
    print(json.dumps(run(), ensure_ascii=False, indent=2))
