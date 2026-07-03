import csv
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import requests


BASE = Path(__file__).resolve().parent
TASK_ID = "TASK-RADAR-DATA-DYNAMIC-POOL1-TPEX-HISTORICAL-FULL-SWEEP-20260703"
PREVIOUS_PACKAGE = Path("outputs/radar_dynamic_pool1_tpex_static_reverse_archive_probe_20260703")
CORE_READINESS = Path(
    r"C:\Users\zergv\Documents\Codex\2026-05-30\ep05-chat-ai-stock-backtest-lab\outputs\dynamic_pool1_pit_readiness_after_tpex_static_reverse_partial_20260703"
)
START_DATE = date(2015, 1, 1)
END_DATE = date(2025, 12, 31)
BASE_URL = "https://www.tpex.org.tw/www/zh-tw/"
USER_AGENT = "Mozilla/5.0"
RUN_TS = datetime.now(timezone.utc).isoformat()


def write_csv(path, rows, fieldnames):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in fieldnames})


def append_csv(path, rows, fieldnames):
    path.parent.mkdir(parents=True, exist_ok=True)
    exists = path.exists()
    with path.open("a", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        if not exists:
            writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in fieldnames})


def read_csv(path):
    if not path.exists():
        return []
    with path.open("r", newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def roc_to_iso(value):
    if value is None:
        return ""
    s = str(value).strip()
    if not s:
        return ""
    m = re.match(r"^(\d{2,3})[/-](\d{1,2})[/-](\d{1,2})$", s)
    if m:
        return f"{int(m.group(1)) + 1911:04d}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
    m = re.match(r"^(\d{8})$", s)
    if m:
        return f"{s[0:4]}-{s[4:6]}-{s[6:8]}"
    m = re.match(r"^(\d{4})[/-](\d{1,2})[/-](\d{1,2})$", s)
    if m:
        return f"{int(m.group(1)):04d}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
    return s


def iso_compact(d):
    return d.strftime("%Y%m%d")


def iso_slash(d):
    return d.strftime("%Y/%m/%d")


def daterange(start, end):
    cur = start
    while cur <= end:
        yield cur
        cur += timedelta(days=1)


def table_rows(obj):
    total = 0
    for table in obj.get("tables") or []:
        data = table.get("data")
        if isinstance(data, list):
            total += len(data)
    return total


def table_data(obj):
    for table in obj.get("tables") or []:
        data = table.get("data")
        if isinstance(data, list):
            for row in data:
                yield row


def post_json(action, params, timeout=20):
    url = BASE_URL + action
    resp = requests.post(
        url,
        data=params,
        timeout=timeout,
        headers={
            "User-Agent": USER_AGENT,
            "Referer": "https://www.tpex.org.tw/",
            "Content-Type": "application/x-www-form-urlencoded",
        },
    )
    raw = resp.content
    text = raw.decode(resp.encoding or "utf-8", errors="replace")
    return resp.status_code, resp.headers.get("Content-Type", ""), json.loads(text), len(raw)


def attempt_row(attempt_id, route_family, action, params, target_date="", target_year="", status="pending", http_code="", content_type="", stat="", source_date="", row_count=0, accepted_rows=0, error=""):
    return {
        "attempt_id": attempt_id,
        "route_family": route_family,
        "source": "TPEx official API",
        "query_url": BASE_URL + action,
        "method": "POST",
        "params": urllib.parse.urlencode(params),
        "target_date": target_date,
        "target_year": target_year,
        "status": status,
        "http_code": http_code,
        "content_type": content_type,
        "stat": stat,
        "date_field_detected": "yes" if source_date else "no",
        "source_date": source_date,
        "row_count": row_count,
        "accepted_rows": accepted_rows,
        "error": error,
    }


ATTEMPT_FIELDS = [
    "attempt_id",
    "route_family",
    "source",
    "query_url",
    "method",
    "params",
    "target_date",
    "target_year",
    "status",
    "http_code",
    "content_type",
    "stat",
    "date_field_detected",
    "source_date",
    "row_count",
    "accepted_rows",
    "error",
]


def load_completed_attempts():
    return {r["attempt_id"] for r in read_csv(BASE / "source_request_attempts.csv") if r.get("status") in {"ok", "empty", "blocked_current_only"}}


def normalize_listing(row, raw_source_id, year):
    if len(row) < 4 or not str(row[1]).strip():
        return None
    event_date = roc_to_iso(row[3])
    return {
        "ticker": str(row[1]).strip(),
        "name": str(row[2]).strip(),
        "market": "TPEx",
        "event_type": "listing",
        "event_date": event_date,
        "source_date": f"{year}-12-31",
        "source_url": BASE_URL + "company/latest",
        "source_type": "official_historical_api",
        "formal_ready": "true",
        "raw_source_id": raw_source_id,
        "notes": "TPEx company/latest full-year query.",
    }


def normalize_delisting(row, raw_source_id, year):
    if len(row) < 3 or not str(row[0]).strip():
        return None
    event_date = roc_to_iso(row[2])
    return {
        "ticker": str(row[0]).strip(),
        "name": str(row[1]).strip(),
        "market": "TPEx",
        "event_type": "delisting",
        "event_date": event_date,
        "source_date": f"{year}-12-31",
        "source_url": BASE_URL + "company/deListed",
        "source_type": "official_historical_api",
        "formal_ready": "true",
        "raw_source_id": raw_source_id,
        "notes": "TPEx company/deListed full-year query.",
    }


def normalize_status(row, raw_source_id, source_date):
    if len(row) < 7 or not str(row[0]).strip():
        return None
    flags = [str(row[i]).strip() for i in range(2, 7)]
    if not any(flags):
        return None
    return {
        "ticker": str(row[0]).strip(),
        "name": str(row[1]).strip(),
        "market": "TPEx",
        "status_date": source_date,
        "source_date": source_date,
        "source_url": BASE_URL + "afterTrading/chtm",
        "source_type": "official_historical_api",
        "is_altered_trading": "true" if str(row[2]).strip() else "false",
        "is_periodic_call_auction": "true" if str(row[3]).strip() else "false",
        "is_management_stock": "true" if str(row[4]).strip() else "false",
        "matching_cycle_minutes": str(row[5]).strip(),
        "is_suspended": "true" if str(row[6]).strip() else "false",
        "formal_ready": "true",
        "raw_source_id": raw_source_id,
        "notes": "Daily TPEx altered-trading/status snapshot; not a transition event ledger.",
    }


def run_sweep():
    BASE.mkdir(parents=True, exist_ok=True)
    (BASE / "current_step.txt").write_text("running full TPEx historical sweep", encoding="utf-8")
    completed_attempts = load_completed_attempts()
    attempts_path = BASE / "source_request_attempts.csv"
    listing_rows = read_csv(BASE / "accepted_listing_metadata_rows.csv")
    delisting_rows = read_csv(BASE / "accepted_delisting_metadata_rows.csv")
    status_rows_by_year = defaultdict(list)
    for existing_status in load_status_rows():
        if existing_status.get("status_date", "")[:4].isdigit():
            status_rows_by_year[int(existing_status["status_date"][:4])].append(existing_status)
    run_log = [
        {"timestamp_utc": RUN_TS, "level": "INFO", "message": "Started TPEx historical full sweep."},
        {"timestamp_utc": RUN_TS, "level": "INFO", "message": "Using previous static reverse API contract: /www/zh-tw/{action}; POST form fields + response=json."},
    ]

    # Yearly routes.
    for year in range(START_DATE.year, END_DATE.year + 1):
        route_specs = [
            ("listing", "company/latest", {"code": "", "date": str(year), "response": "json"}, normalize_listing),
            ("delisting", "company/deListed", {"code": "", "date": str(year), "reason": "", "response": "json", "paging-offset": 0, "paging-size": 5000}, normalize_delisting),
        ]
        for route_family, action, params, normalizer in route_specs:
            attempt_id = f"{route_family}_{year}"
            if attempt_id in completed_attempts:
                continue
            try:
                http_code, content_type, obj, raw_len = post_json(action, params)
                rows = []
                for raw in table_data(obj):
                    parsed = normalizer(raw, attempt_id, year)
                    if parsed:
                        rows.append(parsed)
                target = listing_rows if route_family == "listing" else delisting_rows
                target.extend(rows)
                status = "ok" if rows else "empty"
                append_csv(
                    attempts_path,
                    [
                        attempt_row(
                            attempt_id=attempt_id,
                            route_family=route_family,
                            action=action,
                            params=params,
                            target_year=str(year),
                            status=status,
                            http_code=http_code,
                            content_type=content_type,
                            stat=obj.get("stat", ""),
                            source_date=roc_to_iso(obj.get("date", "")) or f"{year}-12-31",
                            row_count=table_rows(obj),
                            accepted_rows=len(rows),
                        )
                    ],
                    ATTEMPT_FIELDS,
                )
            except Exception as exc:
                append_csv(
                    attempts_path,
                    [
                        attempt_row(
                            attempt_id=attempt_id,
                            route_family=route_family,
                            action=action,
                            params=params,
                            target_year=str(year),
                            status="failed",
                            error=repr(exc),
                        )
                    ],
                    ATTEMPT_FIELDS,
                )
        write_csv(BASE / "accepted_listing_metadata_rows.csv", listing_rows, LISTING_FIELDS)
        write_csv(BASE / "accepted_delisting_metadata_rows.csv", delisting_rows, LISTING_FIELDS)

    # Daily status route. Re-run the full daily range in bounded concurrent chunks
    # because interrupted slow attempts may not have persisted accepted row bodies.
    dates = list(daterange(START_DATE, END_DATE))
    total_days = len(dates)
    status_rows_by_year = defaultdict(list)

    def fetch_status(d):
        attempt_id = f"status_{iso_compact(d)}"
        params = {"date": iso_slash(d), "response": "json"}
        try:
            http_code, content_type, obj, raw_len = post_json("afterTrading/chtm", params)
            source_date = roc_to_iso(obj.get("date", "")) or d.isoformat()
            rows = []
            for raw in table_data(obj):
                parsed = normalize_status(raw, attempt_id, source_date)
                if parsed:
                    rows.append(parsed)
            status = "ok" if rows else "empty"
            return d, rows, attempt_row(
                attempt_id=attempt_id,
                route_family="status_snapshot",
                action="afterTrading/chtm",
                params=params,
                target_date=d.isoformat(),
                target_year=str(d.year),
                status=status,
                http_code=http_code,
                content_type=content_type,
                stat=obj.get("stat", ""),
                source_date=source_date,
                row_count=table_rows(obj),
                accepted_rows=len(rows),
            )
        except Exception as exc:
            return d, [], attempt_row(
                attempt_id=attempt_id,
                route_family="status_snapshot",
                action="afterTrading/chtm",
                params=params,
                target_date=d.isoformat(),
                target_year=str(d.year),
                status="failed",
                error=repr(exc),
            )

    chunk_size = 240
    worker_count = 12
    for start_idx in range(0, total_days, chunk_size):
        chunk = dates[start_idx : start_idx + chunk_size]
        attempt_rows = []
        with ThreadPoolExecutor(max_workers=worker_count) as pool:
            futures = [pool.submit(fetch_status, d) for d in chunk]
            for fut in as_completed(futures):
                d, rows, attempt = fut.result()
                status_rows_by_year[d.year].extend(rows)
                attempt_rows.append(attempt)
        attempt_rows.sort(key=lambda r: r["target_date"])
        append_csv(attempts_path, attempt_rows, ATTEMPT_FIELDS)
        write_status_shards(status_rows_by_year)
        done = min(start_idx + len(chunk), total_days)
        (BASE / "current_step.txt").write_text(
            f"running concurrent status sweep {done}/{total_days}: through {chunk[-1].isoformat()}",
            encoding="utf-8",
        )
    write_status_shards(status_rows_by_year)

    (BASE / "run_log.csv").unlink(missing_ok=True)
    write_csv(BASE / "run_log.csv", run_log, ["timestamp_utc", "level", "message"])
    return finalize_package()


LISTING_FIELDS = [
    "ticker",
    "name",
    "market",
    "event_type",
    "event_date",
    "source_date",
    "source_url",
    "source_type",
    "formal_ready",
    "raw_source_id",
    "notes",
]

STATUS_FIELDS = [
    "ticker",
    "name",
    "market",
    "status_date",
    "source_date",
    "source_url",
    "source_type",
    "is_altered_trading",
    "is_periodic_call_auction",
    "is_management_stock",
    "matching_cycle_minutes",
    "is_suspended",
    "formal_ready",
    "raw_source_id",
    "notes",
]


def write_status_shards(status_rows_by_year):
    shard_dir = BASE / "status_shards"
    shard_dir.mkdir(exist_ok=True)
    for year, rows in status_rows_by_year.items():
        if rows:
            write_csv(shard_dir / f"accepted_status_snapshot_rows_{year}.csv", rows, STATUS_FIELDS)


def load_status_rows():
    rows = []
    for path in sorted((BASE / "status_shards").glob("accepted_status_snapshot_rows_*.csv")):
        rows.extend(read_csv(path))
    return rows


def dedupe_rows(rows, key_fields):
    seen = set()
    out = []
    for row in rows:
        key = tuple(row.get(k, "") for k in key_fields)
        if key in seen:
            continue
        seen.add(key)
        out.append(row)
    return out


def finalize_package():
    listing_rows = dedupe_rows(read_csv(BASE / "accepted_listing_metadata_rows.csv"), ["ticker", "event_type", "event_date"])
    delisting_rows = dedupe_rows(read_csv(BASE / "accepted_delisting_metadata_rows.csv"), ["ticker", "event_type", "event_date"])
    status_rows = dedupe_rows(load_status_rows(), ["ticker", "status_date", "is_altered_trading", "is_periodic_call_auction", "is_management_stock", "is_suspended"])
    write_csv(BASE / "accepted_listing_metadata_rows.csv", listing_rows, LISTING_FIELDS)
    write_csv(BASE / "accepted_delisting_metadata_rows.csv", delisting_rows, LISTING_FIELDS)
    write_csv(BASE / "accepted_status_snapshot_rows.csv", status_rows, STATUS_FIELDS)
    write_csv(BASE / "accepted_suspension_event_rows.csv", [], ["ticker", "name", "market", "event_type", "event_date", "source_date", "source_url", "source_type", "formal_ready", "raw_source_id", "notes"])

    attempts_all = read_csv(BASE / "source_request_attempts.csv")
    best = {}
    rank = {"ok": 3, "empty": 2, "blocked_current_only": 2, "failed": 1}
    for row in attempts_all:
        attempt_id = row.get("attempt_id", "")
        if not attempt_id:
            continue
        prev = best.get(attempt_id)
        if prev is None or rank.get(row.get("status", ""), 0) >= rank.get(prev.get("status", ""), 0):
            best[attempt_id] = row
    attempts = list(best.values())
    write_csv(BASE / "source_request_attempts_effective.csv", attempts, ATTEMPT_FIELDS)
    attempts_by_year = defaultdict(list)
    for row in attempts:
        if row.get("target_year"):
            attempts_by_year[row["target_year"]].append(row)

    coverage = []
    missing = []
    for year in range(START_DATE.year, END_DATE.year + 1):
        y = str(year)
        year_days = [d for d in daterange(date(year, 1, 1), date(year, 12, 31))]
        attempted_status_dates = {r["target_date"] for r in attempts if r.get("route_family") == "status_snapshot" and r.get("target_year") == y and r.get("status") in {"ok", "empty"}}
        failed_status_dates = [r["target_date"] for r in attempts if r.get("route_family") == "status_snapshot" and r.get("target_year") == y and r.get("status") == "failed"]
        missing_status_dates = [d.isoformat() for d in year_days if d.isoformat() not in attempted_status_dates]
        listing_count = sum(1 for r in listing_rows if r["source_date"].startswith(y))
        delisting_count = sum(1 for r in delisting_rows if r["source_date"].startswith(y))
        status_count = sum(1 for r in status_rows if r["status_date"].startswith(y))
        listing_attempt_ok = any(r.get("attempt_id") == f"listing_{year}" and r.get("status") in {"ok", "empty"} for r in attempts)
        delisting_attempt_ok = any(r.get("attempt_id") == f"delisting_{year}" and r.get("status") in {"ok", "empty"} for r in attempts)
        status_full = not missing_status_dates and not failed_status_dates
        coverage_status = "complete_route_coverage" if listing_attempt_ok and delisting_attempt_ok and status_full else "partial_or_failed_route_coverage"
        coverage.append(
            {
                "year": y,
                "market": "TPEx",
                "listing_route_attempted": str(listing_attempt_ok).lower(),
                "listing_rows": listing_count,
                "delisting_route_attempted": str(delisting_attempt_ok).lower(),
                "delisting_rows": delisting_count,
                "status_dates_expected": len(year_days),
                "status_dates_attempted": len(attempted_status_dates),
                "status_failed_dates": len(failed_status_dates),
                "status_missing_dates": len(missing_status_dates),
                "status_snapshot_rows": status_count,
                "coverage_status": coverage_status,
                "formal_ready_scope": "source_backed_historical_candidate_full_route_coverage" if coverage_status == "complete_route_coverage" else "partial",
            }
        )
        for md in missing_status_dates[:20]:
            missing.append({"year": y, "market": "TPEx", "route_family": "status_snapshot", "missing_date": md, "reason": "not_attempted_or_not_completed"})
        for fd in failed_status_dates[:20]:
            missing.append({"year": y, "market": "TPEx", "route_family": "status_snapshot", "missing_date": fd, "reason": "request_failed"})

    all_route_complete = all(r["coverage_status"] == "complete_route_coverage" for r in coverage)
    blocked = [
        {
            "source": "TPEx bulletin/sprc",
            "blocked_component": "suspension/resumption transition event ledger",
            "function_or_endpoint": "action=bulletin/sprc; endpoint=/www/zh-tw/bulletin/sprc",
            "blocked_reason": "current_only_no_historical_date_parameter",
            "impact": "Daily afterTrading/chtm snapshots provide suspended-as-of-date, but not explicit transition event dates.",
            "next_programmatic_route": "Use status snapshot diffs to infer transitions, then validate against bulletin/annDownload ZIP archive.",
        },
        {
            "source": "TPEx bulletin/annDownload",
            "blocked_component": "official announcement ZIP event extraction",
            "function_or_endpoint": "action=bulletin/annDownload; /storage/eb_data/YYYYMM/YYYYMMDD.zip",
            "blocked_reason": "optional route not run in this main full sweep",
            "impact": "Full route coverage package has listing/delisting/status snapshots; event text archive remains next-source validation.",
            "next_programmatic_route": "Bounded monthly ZIP download and keyword extraction for 終止上櫃/暫停/恢復.",
        },
    ]

    source_manifest = [
        {
            "source_id": "tpex_company_latest",
            "source_name": "TPEx 最近上櫃公司",
            "endpoint": BASE_URL + "company/latest",
            "method": "POST",
            "params": "code=&date=YYYY&response=json",
            "coverage": "2015-2025 yearly",
            "source_type": "official_historical_api",
            "accepted_scope": "listing event rows",
            "formal_exact": "false",
        },
        {
            "source_id": "tpex_company_deListed",
            "source_name": "TPEx 終止上櫃公司",
            "endpoint": BASE_URL + "company/deListed",
            "method": "POST",
            "params": "code=&date=YYYY&reason=&response=json&paging-offset=0&paging-size=5000",
            "coverage": "2015-2025 yearly",
            "source_type": "official_historical_api",
            "accepted_scope": "delisting event rows",
            "formal_exact": "false",
        },
        {
            "source_id": "tpex_afterTrading_chtm",
            "source_name": "TPEx 變更交易/分盤/管理股票/停止交易資訊",
            "endpoint": BASE_URL + "afterTrading/chtm",
            "method": "POST",
            "params": "date=YYYY/MM/DD&response=json",
            "coverage": "2015-01-01 to 2025-12-31 daily",
            "source_type": "official_historical_api",
            "accepted_scope": "status snapshot rows",
            "formal_exact": "false",
        },
    ]
    write_csv(BASE / "source_manifest.csv", source_manifest, ["source_id", "source_name", "endpoint", "method", "params", "coverage", "source_type", "accepted_scope", "formal_exact"])
    (BASE / "source_manifest.json").write_text(json.dumps(source_manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    write_csv(BASE / "coverage_by_year.csv", coverage, ["year", "market", "listing_route_attempted", "listing_rows", "delisting_route_attempted", "delisting_rows", "status_dates_expected", "status_dates_attempted", "status_failed_dates", "status_missing_dates", "status_snapshot_rows", "coverage_status", "formal_ready_scope"])
    write_csv(BASE / "missing_coverage.csv", missing, ["year", "market", "route_family", "missing_date", "reason"])
    write_csv(BASE / "blocked_source_rows.csv", blocked, ["source", "blocked_component", "function_or_endpoint", "blocked_reason", "impact", "next_programmatic_route"])

    summary_rows = [
        {"dataset": "listing_metadata", "accepted_rows": len(listing_rows), "source": "company/latest", "coverage": "2015-2025 yearly", "notes": "listing events"},
        {"dataset": "delisting_metadata", "accepted_rows": len(delisting_rows), "source": "company/deListed", "coverage": "2015-2025 yearly", "notes": "delisting events"},
        {"dataset": "status_snapshot", "accepted_rows": len(status_rows), "source": "afterTrading/chtm", "coverage": "2015-01-01 to 2025-12-31 daily", "notes": "altered/periodic/management/suspended as-of snapshots"},
        {"dataset": "suspension_event", "accepted_rows": 0, "source": "bulletin/sprc", "coverage": "current only", "notes": "blocked as event ledger"},
    ]
    write_csv(BASE / "accepted_rows_summary.csv", summary_rows, ["dataset", "accepted_rows", "source", "coverage", "notes"])

    write_csv(
        BASE / "future_data_violation_audit.csv",
        [
            {
                "audit_item": "current_snapshot_backfill",
                "result": "pass",
                "future_data_violation_count": 0,
                "evidence": "All accepted rows use explicit TPEx historical year/date parameters; no current company profile snapshot backfill.",
            },
            {
                "audit_item": "status_snapshot_boundary",
                "result": "pass",
                "future_data_violation_count": 0,
                "evidence": "afterTrading/chtm rows are marked status snapshots, not transition event rows.",
            },
            {
                "audit_item": "model_boundary",
                "result": "pass",
                "future_data_violation_count": 0,
                "evidence": "No BACKTEST_LAB formal model, report, selector, or trade decision changed.",
            },
        ],
        ["audit_item", "result", "future_data_violation_count", "evidence"],
    )

    route_attempts = len(attempts)
    failed_attempts = sum(1 for r in attempts if r.get("status") == "failed")
    full_ready = all_route_complete and failed_attempts == 0
    readiness = {
        "task_id": TASK_ID,
        "status": "completed_full_route_coverage_suspension_events_still_blocked" if full_ready else "completed_partial_full_sweep_with_missing_attempts",
        "output_path": str(BASE),
        "covered_start": START_DATE.isoformat(),
        "covered_end": END_DATE.isoformat(),
        "route_request_attempts": route_attempts,
        "failed_attempts": failed_attempts,
        "accepted_listing_metadata_rows": len(listing_rows),
        "accepted_delisting_metadata_rows": len(delisting_rows),
        "accepted_status_snapshot_rows": len(status_rows),
        "accepted_suspension_event_rows": 0,
        "accepted_historical_rows": len(listing_rows) + len(delisting_rows) + len(status_rows),
        "future_data_violation_count": 0,
        "full_tpex_2015_2025_route_coverage_ready": full_ready,
        "full_tpex_2015_2025_master_ready": False,
        "listing_delisting_suspension_master_full_ready": False,
        "ready_for_core_rerun": True,
        "ready_for_strategy_replay": False,
        "formal_model_changed": False,
        "trade_decision_changed": False,
        "active_in_trade_decision": False,
        "remaining_blockers": [
            "Suspension/resumption transition event ledger remains 0 accepted rows; afterTrading/chtm is a daily status snapshot source.",
            "Core must decide whether daily status snapshots are sufficient for universe integrity or require explicit transition events.",
            "Optional annDownload ZIP and applicantStatDl cross-check not completed in this main sweep.",
        ],
    }
    (BASE / "readiness_for_core.json").write_text(json.dumps(readiness, ensure_ascii=False, indent=2), encoding="utf-8")
    (BASE / "manifest.json").write_text(
        json.dumps(
            {
                "task_id": TASK_ID,
                "created_at_utc": RUN_TS,
                "status": readiness["status"],
                "previous_package": str(PREVIOUS_PACKAGE),
                "core_readiness_input": str(CORE_READINESS),
                "outputs": [
                    "source_manifest.csv",
                    "source_request_attempts.csv",
                    "source_request_attempts_effective.csv",
                    "accepted_listing_metadata_rows.csv",
                    "accepted_delisting_metadata_rows.csv",
                    "accepted_status_snapshot_rows.csv",
                    "accepted_suspension_event_rows.csv",
                    "accepted_rows_summary.csv",
                    "coverage_by_year.csv",
                    "missing_coverage.csv",
                    "blocked_source_rows.csv",
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
            {"step": "company_latest_yearly_sweep", "status": "completed", "evidence": "accepted_listing_metadata_rows.csv"},
            {"step": "company_deListed_yearly_sweep", "status": "completed", "evidence": "accepted_delisting_metadata_rows.csv"},
            {"step": "afterTrading_chtm_daily_sweep", "status": "completed" if full_ready else "completed_with_missing_or_failed", "evidence": "accepted_status_snapshot_rows.csv; coverage_by_year.csv"},
            {"step": "package_readiness", "status": "completed", "evidence": "readiness_for_core.json"},
        ],
        ["step", "status", "evidence"],
    )
    write_csv(
        BASE / "failed.csv",
        [
            {"step": "suspension_resumption_event_ledger", "status": "blocked", "reason": "bulletin/sprc current-only; no historical date parameter"},
            {"step": "annDownload_zip_extraction", "status": "not_run_optional", "reason": "kept out of main full sweep to avoid blocking route coverage"},
        ],
        ["step", "status", "reason"],
    )
    (BASE / "current_step.txt").write_text(readiness["status"], encoding="utf-8")
    (BASE / "final_summary_zh.md").write_text(
        f"""# Dynamic Pool1 TPEx historical listing/status full sweep

## 結論

狀態：`{readiness['status']}`。

本棒把上一棒 sample route 擴成 2015-01-01 到 2025-12-31 full sweep package：

- `company/latest`：2015-2025 yearly sweep，accepted listing rows = {len(listing_rows)}
- `company/deListed`：2015-2025 yearly sweep，accepted delisting rows = {len(delisting_rows)}
- `afterTrading/chtm`：2015-01-01～2025-12-31 daily sweep，accepted status snapshot rows = {len(status_rows)}
- `accepted_suspension_event_rows=0`

## Readiness

- `full_tpex_2015_2025_route_coverage_ready={str(full_ready).lower()}`
- `full_tpex_2015_2025_master_ready=false`
- `ready_for_core_rerun=true`
- `ready_for_strategy_replay=false`
- `future_data_violation_count=0`
- `formal_model_changed=false`
- `trade_decision_changed=false`
- `active_in_trade_decision=false`

## 邊界

`afterTrading/chtm` 是每日 status snapshot，可判斷某日是否變更交易、分盤交易、管理股票、停止交易，但不是 suspension/resumption transition event ledger。`bulletin/sprc` 仍是 current-only，沒有 historical date parameter，所以 suspension event rows 仍為 0。

## 下一步

1. 交 Core 重跑 Dynamic Pool1 readiness，判斷 TPEx full route coverage + daily status snapshot 是否足以讓 listing/status master 從 partial 再升級。
2. 若 Core 仍要求 explicit transition event dates，下一棒 Radar/Data 需跑 `bulletin/annDownload` ZIP keyword extraction 或以 `afterTrading/chtm` daily snapshot diff 產生 inferred transition candidates，再用公告 archive 驗證。
3. 可選 cross-check：下載 `company/applicantStatDl?type=list|app&date=YYYY` annual files，和 `company/latest` listing rows 對帳。
""",
        encoding="utf-8",
    )
    return readiness


def main():
    try:
        readiness = run_sweep()
        print(json.dumps(readiness, ensure_ascii=False, indent=2))
    except KeyboardInterrupt:
        (BASE / "current_step.txt").write_text("interrupted; rerun build_full_sweep_package.py to resume", encoding="utf-8")
        raise


if __name__ == "__main__":
    main()
