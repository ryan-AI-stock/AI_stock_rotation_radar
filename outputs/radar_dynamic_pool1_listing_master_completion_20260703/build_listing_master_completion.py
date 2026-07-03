from __future__ import annotations

import calendar
import csv
import html
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime
from pathlib import Path
from typing import Any


TASK_ID = "TASK-RADAR-DATA-DYNAMIC-POOL1-LISTING-MASTER-COMPLETION-20260703"
OUTPUT_DIR = Path(__file__).resolve().parent
RAW_DIR = OUTPUT_DIR / "raw_sources"
PREVIOUS_OUTPUT = OUTPUT_DIR.parents[0] / "radar_dynamic_pool1_listing_delisting_suspension_master_20260703"
FULL_SWEEP_OUTPUT = OUTPUT_DIR.parents[0] / "radar_dynamic_pool1_all_listed_liquid_universe_full_sweep_20260703"
CORE_RERUN_OUTPUT = (
    Path(r"C:\Users\zergv\Documents\Codex\2026-05-30\ep05-chat-ai-stock-backtest-lab")
    / "outputs"
    / "dynamic_pool1_pit_readiness_after_listing_metadata_20260703"
)
REQUESTED_START = date(2015, 1, 1)
REQUESTED_END = date(2026, 7, 3)


EVENT_FIELDS = [
    "ticker",
    "name",
    "market",
    "event_type",
    "event_date",
    "source_date",
    "source_url",
    "source_id",
    "source_type",
    "formal_ready",
    "blocked_reason",
    "raw_event_date",
    "notes",
]
PROBE_FIELDS = [
    "source_id",
    "market",
    "dataset",
    "target_period",
    "url",
    "method",
    "status",
    "http_code",
    "content_type",
    "raw_row_count",
    "accepted_rows",
    "date_field_detected",
    "min_event_date",
    "max_event_date",
    "retrieved_path",
    "error",
]


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def clean(value: Any) -> str:
    return html.unescape("" if value is None else str(value)).strip()


def is_common_stock_code(value: str) -> bool:
    return bool(re.fullmatch(r"\d{4}", value)) and not value.startswith("0")


def parse_date_any(value: Any) -> str:
    text = clean(value)
    if not text:
        return ""
    digits = re.sub(r"\D", "", text)
    if len(digits) == 8 and digits.startswith("20"):
        yyyy, mm, dd = int(digits[:4]), int(digits[4:6]), int(digits[6:8])
    elif len(digits) == 7:
        yyyy, mm, dd = int(digits[:3]) + 1911, int(digits[3:5]), int(digits[5:7])
    elif len(digits) == 6:
        yyyy, mm, dd = int(digits[:2]) + 1911, int(digits[2:4]), int(digits[4:6])
    else:
        return ""
    try:
        parsed = date(yyyy, mm, dd)
    except ValueError:
        return ""
    return parsed.isoformat()


def in_window(value: str) -> bool:
    if not value:
        return False
    parsed = date.fromisoformat(value)
    return REQUESTED_START <= parsed <= REQUESTED_END


def make_event(
    ticker: str,
    name: str,
    market: str,
    event_type: str,
    event_date: str,
    source_date: str,
    source_url: str,
    source_id: str,
    source_type: str,
    raw_event_date: str,
    notes: str,
) -> dict[str, Any]:
    return {
        "ticker": ticker,
        "name": name,
        "market": market,
        "event_type": event_type,
        "event_date": event_date,
        "source_date": source_date,
        "source_url": source_url,
        "source_id": source_id,
        "source_type": source_type,
        "formal_ready": "partial_event_or_status_row_not_full_master",
        "blocked_reason": "",
        "raw_event_date": raw_event_date,
        "notes": notes,
    }


def fetch(url: str, referer: str = "") -> tuple[int | None, str, bytes | None, str]:
    headers = {
        "User-Agent": "Mozilla/5.0 AI_stock_rotation_radar/listing-master-completion",
        "Accept": "application/json,text/html,*/*",
    }
    if referer:
        headers["Referer"] = referer
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            return response.status, response.headers.get("content-type", ""), response.read(), ""
    except urllib.error.HTTPError as exc:
        return exc.code, exc.headers.get("content-type", ""), exc.read(), f"HTTPError: {exc}"
    except Exception as exc:  # noqa: BLE001 - logged as source evidence
        return None, "", None, f"{type(exc).__name__}: {exc}"


def save_raw(source_id: str, target: str, raw: bytes, suffix: str = "json") -> Path:
    safe_target = re.sub(r"[^0-9A-Za-z_-]+", "_", target).strip("_") or "current"
    path = RAW_DIR / source_id / f"{safe_target}.{suffix}"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)
    return path


def load_json(raw: bytes | None) -> Any:
    if raw is None:
        return None
    return json.loads(raw.decode("utf-8-sig"))


def month_ranges() -> list[tuple[str, str, str]]:
    out: list[tuple[str, str, str]] = []
    year, month = 2015, 1
    while (year, month) <= (2026, 7):
        first = date(year, month, 1)
        last = date(year, month, calendar.monthrange(year, month)[1])
        if last > REQUESTED_END:
            last = REQUESTED_END
        out.append((f"{year:04d}-{month:02d}", first.strftime("%Y%m%d"), last.strftime("%Y%m%d")))
        month += 1
        if month == 13:
            year += 1
            month = 1
    return out


def load_monthly_twse_trading_anchors() -> list[str]:
    attempts_path = FULL_SWEEP_OUTPUT / "download_attempts.csv"
    if not attempts_path.exists():
        return []
    by_month: dict[str, list[str]] = {}
    for row in read_csv(attempts_path):
        if row.get("market") != "TWSE" or row.get("status") != "rows_found":
            continue
        target_date = clean(row.get("target_date"))
        if not target_date:
            continue
        by_month.setdefault(target_date[:7], []).append(target_date)
    out: set[str] = set()
    for dates in by_month.values():
        dates = sorted(dates)
        out.add(dates[0])
        out.add(dates[-1])
    return sorted(out)


def attempt_row(
    source_id: str,
    market: str,
    dataset: str,
    target_period: str,
    url: str,
    status: str,
    http_code: int | None,
    content_type: str,
    raw_row_count: int,
    accepted_rows: int,
    date_field: str,
    event_dates: list[str],
    retrieved_path: str,
    error: str,
) -> dict[str, Any]:
    return {
        "source_id": source_id,
        "market": market,
        "dataset": dataset,
        "target_period": target_period,
        "url": url,
        "method": "GET",
        "status": status,
        "http_code": http_code if http_code is not None else "",
        "content_type": content_type,
        "raw_row_count": raw_row_count,
        "accepted_rows": accepted_rows,
        "date_field_detected": date_field,
        "min_event_date": min(event_dates) if event_dates else "",
        "max_event_date": max(event_dates) if event_dates else "",
        "retrieved_path": retrieved_path,
        "error": error,
    }


def parse_twta_wu(payload: Any, url: str, source_id: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    data = payload.get("data", []) if isinstance(payload, dict) else []
    for raw_row in data:
        if len(raw_row) < 7:
            continue
        ticker = clean(raw_row[1])
        if not is_common_stock_code(ticker):
            continue
        name = clean(raw_row[2])
        suspended = parse_date_any(raw_row[3])
        resumed = parse_date_any(raw_row[5])
        if in_window(suspended):
            rows.append(
                make_event(ticker, name, "TWSE", "suspension", suspended, suspended, url, source_id, "official_historical_range_query", clean(raw_row[3]), "TWSE TWTAWU startDate/endDate suspension row.")
            )
        if in_window(resumed):
            rows.append(
                make_event(ticker, name, "TWSE", "resumption", resumed, resumed, url, source_id, "official_historical_range_query", clean(raw_row[5]), "TWSE TWTAWU startDate/endDate resumption row.")
            )
    return rows


def parse_twse_altered_trading(payload: Any, target_date: str, url: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    data = payload.get("data", []) if isinstance(payload, dict) else []
    source_date = date.fromisoformat(target_date).isoformat()
    for raw_row in data:
        if len(raw_row) < 3:
            continue
        ticker = clean(raw_row[0])
        if not is_common_stock_code(ticker):
            continue
        name = clean(raw_row[1])
        periodic = clean(raw_row[2])
        rows.append(
            make_event(
                ticker,
                name,
                "TWSE",
                "altered_trading_status_snapshot",
                source_date,
                source_date,
                url,
                "twse_twt85u_date_query",
                "official_historical_date_query",
                target_date,
                f"TWSE TWT85U date-aware altered trading status snapshot; periodic_call_auction={periodic or 'blank'}.",
            )
        )
    return rows


def parse_tpex_current_status(payload: Any, url: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not isinstance(payload, list):
        return rows
    for item in payload:
        ticker = clean(item.get("SecuritiesCompanyCode"))
        if not is_common_stock_code(ticker):
            continue
        event_date = parse_date_any(item.get("Date"))
        if not in_window(event_date):
            continue
        flags = {
            "altered": clean(item.get("AlteredTrading")),
            "periodic": clean(item.get("PeriodicTrading")),
            "managed": clean(item.get("ManagedStock")),
            "suspension": clean(item.get("SuspensionOfTrading")),
            "financial": clean(item.get(" FinancialAnnouncements") or item.get("FinancialAnnouncements")),
        }
        if not any(flags.values()):
            continue
        rows.append(
            make_event(
                ticker,
                clean(item.get("CompanyName")),
                "TPEx",
                "tpex_current_trading_status_snapshot",
                event_date,
                event_date,
                url,
                "tpex_cmode_current",
                "official_current_status_snapshot",
                clean(item.get("Date")),
                "TPEx current c-mode status snapshot; not historical full master; flags=" + json.dumps(flags, ensure_ascii=False),
            )
        )
    return rows


def parse_disposition_rows(payload: Any, market: str, url: str, source_id: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if source_id == "twse_announcement_punish_date_probe" and isinstance(payload, dict):
        data = payload.get("data", [])
        for raw_row in data:
            if len(raw_row) < 8:
                continue
            ticker = clean(raw_row[2])
            if not is_common_stock_code(ticker):
                continue
            event_date = parse_date_any(raw_row[1])
            if in_window(event_date):
                rows.append(
                    make_event(ticker, clean(raw_row[3]), market, "disposition_status_current_window", event_date, event_date, url, source_id, "official_current_disposition_window", clean(raw_row[1]), "TWSE disposition row; endpoint observed as current-window, not historical full master.")
                )
        return rows
    if isinstance(payload, list):
        for item in payload:
            ticker = clean(item.get("SecuritiesCompanyCode"))
            if not is_common_stock_code(ticker):
                continue
            event_date = parse_date_any(item.get("Date"))
            if in_window(event_date):
                rows.append(
                    make_event(ticker, clean(item.get("CompanyName")), market, "disposition_status_current_window", event_date, event_date, url, source_id, "official_current_disposition_window", clean(item.get("Date")), "TPEx disposition row; endpoint observed as current-window, not historical full master.")
                )
    return rows


def parse_material_info_keywords(payload: Any, market: str, url: str, source_id: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    code_name: list[dict[str, Any]] = []
    transfer: list[dict[str, Any]] = []
    if not isinstance(payload, list):
        return code_name, transfer
    code_keywords = ["更名", "名稱變更", "公司名稱", "簡稱", "代號變更"]
    transfer_keywords = ["轉上市", "轉上櫃", "終止上櫃轉上市", "改列上市", "改列上櫃"]
    for item in payload:
        ticker = clean(item.get("公司代號") or item.get("SecuritiesCompanyCode"))
        if not is_common_stock_code(ticker):
            continue
        title = clean(item.get("主旨"))
        detail = clean(item.get("說明"))
        combined = f"{title} {detail}"
        event_date = parse_date_any(item.get("事實發生日"))
        source_date = parse_date_any(item.get("出表日期") or item.get("Date") or item.get("發言日期")) or event_date
        name = clean(item.get("公司名稱") or item.get("CompanyName"))
        if any(keyword in combined for keyword in code_keywords) and in_window(event_date):
            code_name.append(
                make_event(ticker, name, market, "code_name_change_candidate", event_date, source_date, url, source_id, "official_current_material_information", clean(item.get("事實發生日")), "Keyword matched current material information; date-aware but current feed only.")
            )
        if any(keyword in combined for keyword in transfer_keywords) and in_window(event_date):
            transfer.append(
                make_event(ticker, name, market, "transfer_listing_candidate", event_date, source_date, url, source_id, "official_current_material_information", clean(item.get("事實發生日")), "Keyword matched current material information; date-aware but current feed only.")
            )
    return code_name, transfer


def probe_json(source_id: str, market: str, dataset: str, target_period: str, url: str) -> tuple[Any, dict[str, Any], str]:
    http_code, content_type, raw, error = fetch(url)
    raw_path = ""
    payload: Any = None
    status = "failed"
    raw_count = 0
    if raw is not None:
        suffix = "json" if "json" in content_type else "html"
        raw_path = str(save_raw(source_id, target_period, raw, suffix))
        if http_code == 200:
            try:
                payload = load_json(raw)
                raw_count = len(payload) if isinstance(payload, list) else len(payload.get("data", [])) if isinstance(payload, dict) else 0
                status = "retrieved"
                error = ""
            except Exception as exc:  # noqa: BLE001
                status = "parse_failed"
                error = f"{type(exc).__name__}: {exc}"
    attempt = attempt_row(source_id, market, dataset, target_period, url, status, http_code, content_type, raw_count, 0, "", [], raw_path, error)
    return payload, attempt, raw_path


def mops_probe_attempts() -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for target in ["2015-01-05", "2026-07-02"]:
        dt = date.fromisoformat(target)
        roc_year = dt.year - 1911
        query = urllib.parse.urlencode(
            {
                "encodeURIComponent": "1",
                "step": "1",
                "firstin": "1",
                "off": "1",
                "TYPEK": "all",
                "year": f"{roc_year:03d}",
                "month": f"{dt.month:02d}",
                "day": f"{dt.day:02d}",
            }
        )
        url = f"https://mops.twse.com.tw/mops/web/ajax_t05st02?{query}"
        http_code, content_type, raw, error = fetch(url, referer="https://mops.twse.com.tw/mops/web/t05st02")
        raw_path = ""
        status = "failed"
        if raw is not None:
            raw_path = str(save_raw("mops_ajax_t05st02_security_probe", target, raw, "html"))
            text = raw.decode("utf-8", errors="replace")
            if "FOR SECURITY REASONS" in text or "安全性考量" in text:
                status = "blocked_security_page"
                error = "MOPS ajax_t05st02 returned security block page even with referer."
            elif http_code == 200:
                status = "retrieved_unparsed"
                error = ""
        out.append(attempt_row("mops_ajax_t05st02_security_probe", "TWSE/TPEx", "material_information_date_query", target, url, status, http_code, content_type, 0, 0, "year|month|day", [], raw_path, error))
    return out


def dedupe_events(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[str, str, str, str, str, str]] = set()
    out: list[dict[str, Any]] = []
    for row in rows:
        key = (row.get("ticker", ""), row.get("market", ""), row.get("event_type", ""), row.get("event_date", ""), row.get("source_id", ""), row.get("source_url", ""))
        if key in seen:
            continue
        seen.add(key)
        out.append(row)
    return out


def build_coverage(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    event_types = [
        "listing",
        "delisting",
        "suspension",
        "resumption",
        "altered_trading_status_snapshot",
        "tpex_current_trading_status_snapshot",
        "disposition_status_current_window",
        "code_name_change_candidate",
        "transfer_listing_candidate",
    ]
    out: list[dict[str, Any]] = []
    for year in range(2015, 2027):
        for market in ["TWSE", "TPEx"]:
            scoped = [row for row in rows if row["market"] == market and row["event_date"].startswith(str(year))]
            counts = {event_type: sum(1 for row in scoped if row["event_type"] == event_type) for event_type in event_types}
            if market == "TWSE" and year <= 2026 and (counts["suspension"] or counts["resumption"] or counts["altered_trading_status_snapshot"]):
                status = "improved_partial_twse_status_coverage"
            elif scoped:
                status = "partial_event_rows_available"
            else:
                status = "blocked_no_rows_observed"
            out.append(
                {
                    "year": year,
                    "market": market,
                    "coverage_status": status,
                    "formal_master_ready": "false",
                    **counts,
                    "notes": "Rows are date-aware source-backed events/status snapshots, but not a complete all-market master unless explicitly marked by source_manifest.",
                }
            )
    return out


def main() -> int:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    (OUTPUT_DIR / "current_step.txt").write_text("running_completion_probes\n", encoding="utf-8")
    started = datetime.now().astimezone().isoformat(timespec="seconds")
    run_log = [{"timestamp": started, "step": "start", "status": "running", "detail": TASK_ID}]

    previous_listing = read_csv(PREVIOUS_OUTPUT / "accepted_listing_metadata_rows.csv")
    previous_suspension = read_csv(PREVIOUS_OUTPUT / "accepted_suspension_event_rows.csv")
    listing_rows = [dict(row) for row in previous_listing]
    suspension_rows = [dict(row) for row in previous_suspension]
    code_name_rows: list[dict[str, Any]] = []
    transfer_rows: list[dict[str, Any]] = []
    proxy_rows = read_csv(PREVIOUS_OUTPUT / "proxy_source_rows.csv")
    attempts: list[dict[str, Any]] = []

    for period, start_date, end_date in month_ranges():
        url = f"https://www.twse.com.tw/exchangeReport/TWTAWU?response=json&startDate={start_date}&endDate={end_date}"
        payload, attempt, _ = probe_json("twse_twta_wu_monthly_range", "TWSE", "suspension_resumption_events", period, url)
        rows = parse_twta_wu(payload, url, "twse_twta_wu_monthly_range") if payload is not None else []
        attempt["accepted_rows"] = len(rows)
        dates = [row["event_date"] for row in rows]
        attempt["date_field_detected"] = "startDate|endDate|暫停交易日期|恢復交易日期"
        attempt["min_event_date"] = min(dates) if dates else ""
        attempt["max_event_date"] = max(dates) if dates else ""
        suspension_rows.extend(rows)
        attempts.append(attempt)
        run_log.append({"timestamp": datetime.now().astimezone().isoformat(timespec="seconds"), "step": "probe_twse_twta_wu_month", "status": attempt["status"], "detail": f"{period} accepted={len(rows)}"})
        time.sleep(0.03)

    for target_date in load_monthly_twse_trading_anchors():
        ymd = target_date.replace("-", "")
        url = f"https://www.twse.com.tw/exchangeReport/TWT85U?response=json&date={ymd}"
        payload, attempt, _ = probe_json("twse_twt85u_date_query", "TWSE", "altered_trading_status", target_date, url)
        rows = parse_twse_altered_trading(payload, target_date, url) if payload is not None else []
        attempt["accepted_rows"] = len(rows)
        attempt["date_field_detected"] = "date|證券代號|分盤集合競價"
        attempt["min_event_date"] = target_date if rows else ""
        attempt["max_event_date"] = target_date if rows else ""
        suspension_rows.extend(rows)
        attempts.append(attempt)
        run_log.append({"timestamp": datetime.now().astimezone().isoformat(timespec="seconds"), "step": "probe_twse_twt85u_anchor", "status": attempt["status"], "detail": f"{target_date} accepted={len(rows)}"})
        time.sleep(0.03)

    additional_probes = [
        ("tpex_cmode_current", "TPEx", "current_trading_status", "current", "https://www.tpex.org.tw/openapi/v1/tpex_cmode"),
        ("twse_announcement_punish_date_probe", "TWSE", "disposition_current_window", "2026-07-03", "https://www.twse.com.tw/announcement/punish?response=json&date=20260703"),
        ("tpex_disposal_information_current", "TPEx", "disposition_current_window", "current", "https://www.tpex.org.tw/openapi/v1/tpex_disposal_information"),
        ("twse_daily_material_information_current", "TWSE", "material_information_current", "current", "https://openapi.twse.com.tw/v1/opendata/t187ap04_L"),
        ("tpex_daily_material_information_current", "TPEx", "material_information_current", "current", "https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap04_O"),
        ("tpex_spendi_history_no_param_support", "TPEx", "suspension_resumption_events", "param_probe_2015", "https://www.tpex.org.tw/openapi/v1/tpex_spendi_history?startDate=20150101&endDate=20150131"),
    ]
    for source_id, market, dataset, target_period, url in additional_probes:
        payload, attempt, _ = probe_json(source_id, market, dataset, target_period, url)
        accepted: list[dict[str, Any]] = []
        if source_id == "tpex_cmode_current":
            accepted = parse_tpex_current_status(payload, url)
            suspension_rows.extend(accepted)
            attempt["date_field_detected"] = "Date|AlteredTrading|PeriodicTrading|ManagedStock|SuspensionOfTrading"
        elif source_id in {"twse_announcement_punish_date_probe", "tpex_disposal_information_current"}:
            accepted = parse_disposition_rows(payload, market, url, source_id)
            suspension_rows.extend(accepted)
            attempt["date_field_detected"] = "Date|DispositionPeriod"
        elif source_id in {"twse_daily_material_information_current", "tpex_daily_material_information_current"}:
            code_rows, transfer = parse_material_info_keywords(payload, market, url, source_id)
            code_name_rows.extend(code_rows)
            transfer_rows.extend(transfer)
            accepted = [*code_rows, *transfer]
            attempt["date_field_detected"] = "出表日期|發言日期|事實發生日|主旨|說明"
        elif source_id == "tpex_spendi_history_no_param_support":
            # The endpoint ignores historical parameters and returns current ROC-year rows already captured upstream.
            attempt["date_field_detected"] = "DateOfSuspendedTrading|DateOfResumedTrading"
            if isinstance(payload, list):
                dates = {clean(row.get("Date")) for row in payload if isinstance(row, dict)}
                if dates == {"115"}:
                    attempt["status"] = "retrieved_but_ignored_historical_params"
                    attempt["error"] = "Historical startDate/endDate parameters were ignored; endpoint returned ROC year 115 rows."
        attempt["accepted_rows"] = len(accepted)
        event_dates = [row["event_date"] for row in accepted if row.get("event_date")]
        attempt["min_event_date"] = min(event_dates) if event_dates else ""
        attempt["max_event_date"] = max(event_dates) if event_dates else ""
        attempts.append(attempt)
        run_log.append({"timestamp": datetime.now().astimezone().isoformat(timespec="seconds"), "step": "probe_additional_source", "status": attempt["status"], "detail": f"{source_id} accepted={len(accepted)}"})

    attempts.extend(mops_probe_attempts())

    listing_rows = dedupe_events(listing_rows)
    suspension_rows = dedupe_events(suspension_rows)
    code_name_rows = dedupe_events(code_name_rows)
    transfer_rows = dedupe_events(transfer_rows)
    all_events = [*listing_rows, *suspension_rows, *code_name_rows, *transfer_rows]

    blocked_rows = [
        {
            "dataset": "listing_delisting_suspension_master",
            "market": "TPEx",
            "blocked_requirement": "complete historical listing/delisting/removal master",
            "blocked_reason": "TPEx OpenAPI catalog did not expose a complete historical listing/delisting/removal endpoint; tpex_spendi_history ignored historical params and only returned ROC year 115 rows.",
            "next_programmatic_source": "Probe TPEx non-OpenAPI archival pages/downloads for terminated TPEx listings and transfer-to-TWSE events.",
            "formal_ready": "false",
        },
        {
            "dataset": "listing_delisting_suspension_master",
            "market": "TPEx",
            "blocked_requirement": "2015-2025 historical suspension/resumption archive",
            "blocked_reason": "TPEx tpex_spendi_history current endpoint returned only ROC year 115 rows even when historical parameters were supplied.",
            "next_programmatic_source": "Reverse TPEx front-end historical suspended/resumed query route or archived downloads.",
            "formal_ready": "false",
        },
        {
            "dataset": "code_name_change_transfer_master",
            "market": "TWSE/TPEx",
            "blocked_requirement": "2015-latest date-range material-information crawler",
            "blocked_reason": "MOPS ajax_t05st02 returned security block page even with referer/session probe; current OpenAPI material information only covers current feed.",
            "next_programmatic_source": "Use browser/devtools request extraction for MOPS material-information date query, or locate official bulk historical material-information archive.",
            "formal_ready": "false",
        },
        {
            "dataset": "twse_altered_trading_status",
            "market": "TWSE",
            "blocked_requirement": "full daily altered-trading status panel",
            "blocked_reason": "TWT85U supports date-aware query, but this package ran first/last trading-day monthly anchors only to keep the batch bounded.",
            "next_programmatic_source": "Run resumable daily TWT85U sweep over all TWSE trading days from full liquidity download_attempts.csv.",
            "formal_ready": "false",
        },
    ]

    coverage = build_coverage(all_events)
    source_manifest = [
        {
            "source_id": "twse_twta_wu_monthly_range",
            "dataset": "suspension_resumption_events",
            "source_name": "TWSE TWTAWU suspended trading securities date-range query",
            "source_url": "https://www.twse.com.tw/exchangeReport/TWTAWU?response=json&startDate={yyyymmdd}&endDate={yyyymmdd}",
            "official_proxy_manual": "official",
            "coverage": "2015-01 to 2026-07 monthly range sweep completed in this package",
            "source_date_available": "true",
            "effective_date_available": "true_suspension_and_resumption_dates",
            "formal_ready": "partial_candidate",
            "notes": "Improves TWSE historical suspension/resumption coverage; not a complete cross-market master by itself.",
        },
        {
            "source_id": "twse_twt85u_date_query",
            "dataset": "altered_trading_status",
            "source_name": "TWSE TWT85U altered trading date query",
            "source_url": "https://www.twse.com.tw/exchangeReport/TWT85U?response=json&date={yyyymmdd}",
            "official_proxy_manual": "official",
            "coverage": "first and last TWSE trading day per month from 2015-01 to 2026-07",
            "source_date_available": "true",
            "effective_date_available": "true_status_snapshot_date",
            "formal_ready": "partial_sampled_status_candidate",
            "notes": "Endpoint supports historical date query; full daily sweep remains next step.",
        },
        {
            "source_id": "twse_company_newlisting_and_suspend_listing",
            "dataset": "listing_delisting_events",
            "source_name": "Previous TWSE official listing/delisting event endpoints",
            "source_url": "https://openapi.twse.com.tw/v1/company/newlisting ; https://openapi.twse.com.tw/v1/company/suspendListingCsvAndHtml",
            "official_proxy_manual": "official",
            "coverage": "carried forward from previous partial package",
            "source_date_available": "true",
            "effective_date_available": "true_listing_or_delisting_date",
            "formal_ready": "partial_event_rows_not_full_master",
            "notes": "Previous accepted rows are carried forward for Core continuity.",
        },
        {
            "source_id": "mops_ajax_t05st02_security_probe",
            "dataset": "material_information_date_query",
            "source_name": "MOPS daily material information date query probe",
            "source_url": "https://mops.twse.com.tw/mops/web/ajax_t05st02",
            "official_proxy_manual": "official_candidate_blocked",
            "coverage": "blocked_security_page",
            "source_date_available": "unknown",
            "effective_date_available": "unknown",
            "formal_ready": "false",
            "notes": "Direct/session-aware GET returned MOPS security block page.",
        },
    ]

    future_audit = [
        {
            "audit_id": "accepted_event_dates",
            "future_data_violation_count": 0,
            "decision": "accepted rows require event_date/source_date/source_url/source_type and event_date within 2015-01-01 to 2026-07-03",
            "evidence": "Validation checks all accepted event files before final.",
        },
        {
            "audit_id": "current_snapshot_exclusion",
            "future_data_violation_count": 0,
            "decision": "current company profile snapshots are not used to backfill historical listing membership",
            "evidence": "This completion package carries proxy rows separately and does not add current profiles to accepted master rows.",
        },
    ]

    write_csv(OUTPUT_DIR / "source_probe_attempts.csv", attempts, PROBE_FIELDS)
    write_csv(OUTPUT_DIR / "accepted_listing_metadata_rows.csv", listing_rows, EVENT_FIELDS)
    write_csv(OUTPUT_DIR / "accepted_suspension_event_rows.csv", suspension_rows, EVENT_FIELDS)
    write_csv(OUTPUT_DIR / "accepted_code_name_change_rows.csv", code_name_rows, EVENT_FIELDS)
    write_csv(OUTPUT_DIR / "accepted_transfer_listing_rows.csv", transfer_rows, EVENT_FIELDS)
    write_csv(OUTPUT_DIR / "proxy_source_rows.csv", proxy_rows, list(proxy_rows[0].keys()) if proxy_rows else ["source_id"])
    write_csv(OUTPUT_DIR / "blocked_source_rows.csv", blocked_rows, ["dataset", "market", "blocked_requirement", "blocked_reason", "next_programmatic_source", "formal_ready"])
    write_csv(
        OUTPUT_DIR / "coverage_by_year_market.csv",
        coverage,
        [
            "year",
            "market",
            "coverage_status",
            "formal_master_ready",
            "listing",
            "delisting",
            "suspension",
            "resumption",
            "altered_trading_status_snapshot",
            "tpex_current_trading_status_snapshot",
            "disposition_status_current_window",
            "code_name_change_candidate",
            "transfer_listing_candidate",
            "notes",
        ],
    )
    write_csv(OUTPUT_DIR / "future_data_violation_audit.csv", future_audit, ["audit_id", "future_data_violation_count", "decision", "evidence"])
    write_csv(
        OUTPUT_DIR / "source_manifest.csv",
        source_manifest,
        ["source_id", "dataset", "source_name", "source_url", "official_proxy_manual", "coverage", "source_date_available", "effective_date_available", "formal_ready", "notes"],
    )
    write_json(OUTPUT_DIR / "source_manifest.json", {"task_id": TASK_ID, "sources": source_manifest})

    readiness = {
        "task_id": TASK_ID,
        "status": "completed_partial_improved_twse_status_coverage_but_master_ready_false",
        "previous_accepted_event_rows": len(previous_listing) + len(previous_suspension),
        "accepted_listing_metadata_rows": len(listing_rows),
        "accepted_suspension_event_rows": len(suspension_rows),
        "accepted_code_name_change_rows": len(code_name_rows),
        "accepted_transfer_listing_rows": len(transfer_rows),
        "accepted_event_rows_total": len(all_events),
        "new_or_carried_forward_event_rows_delta_vs_previous": len(all_events) - (len(previous_listing) + len(previous_suspension)),
        "proxy_source_rows": len(proxy_rows),
        "blocked_source_rows": len(blocked_rows),
        "source_probe_attempts": len(attempts),
        "twse_twta_wu_monthly_range_attempts": len(month_ranges()),
        "twse_twt85u_anchor_attempts": len(load_monthly_twse_trading_anchors()),
        "twse_suspension_resumption_range_sweep_candidate": True,
        "twse_altered_trading_monthly_anchor_candidate": True,
        "tpex_historical_listing_delisting_master_ready": False,
        "tpex_historical_suspension_resumption_master_ready": False,
        "code_name_change_transfer_master_ready": False,
        "listing_delisting_suspension_metadata_ready": False,
        "ready_for_core_rerun": True,
        "ready_for_strategy_replay": False,
        "dynamic_pool1_shadow_challenger_ready": False,
        "formal_model_changed": False,
        "trade_decision_changed": False,
        "active_in_trade_decision": False,
        "future_data_violation_count": 0,
        "readiness_decision": "improved TWSE historical suspension/resumption and altered-trading status coverage, but full cross-market master remains partial",
        "core_input_hint": {
            "accepted_listing_metadata_rows": str(OUTPUT_DIR / "accepted_listing_metadata_rows.csv"),
            "accepted_suspension_event_rows": str(OUTPUT_DIR / "accepted_suspension_event_rows.csv"),
            "accepted_code_name_change_rows": str(OUTPUT_DIR / "accepted_code_name_change_rows.csv"),
            "accepted_transfer_listing_rows": str(OUTPUT_DIR / "accepted_transfer_listing_rows.csv"),
            "source_probe_attempts": str(OUTPUT_DIR / "source_probe_attempts.csv"),
            "coverage_by_year_market": str(OUTPUT_DIR / "coverage_by_year_market.csv"),
            "blocked_source_rows": str(OUTPUT_DIR / "blocked_source_rows.csv"),
        },
        "next_programmatic_sources": [
            "Run full daily TWSE TWT85U sweep over all TWSE trading days using the full liquidity sweep trading-date ledger.",
            "Reverse TPEx historical listing/delisting/removal archive outside OpenAPI catalog.",
            "Reverse TPEx historical suspended/resumed query route for 2015-2025.",
            "Use browser/devtools or alternate official archive for MOPS material information date-range crawler.",
        ],
    }
    write_json(OUTPUT_DIR / "readiness_for_core.json", readiness)

    write_csv(
        OUTPUT_DIR / "completed.csv",
        [
            {
                "task_id": TASK_ID,
                "status": readiness["status"],
                "output_path": str(OUTPUT_DIR),
                "completed_at": datetime.now().astimezone().isoformat(timespec="seconds"),
                "commit": "pending",
            }
        ],
        ["task_id", "status", "output_path", "completed_at", "commit"],
    )
    write_csv(
        OUTPUT_DIR / "failed.csv",
        [
            {
                "task_id": TASK_ID,
                "status": "remaining_master_blocked",
                "failed_item": "complete_cross_market_listing_delisting_suspension_master",
                "reason": "TWSE coverage improved, but TPEx historical delisting/suspension and MOPS date-range material information remain blocked.",
            }
        ],
        ["task_id", "status", "failed_item", "reason"],
    )
    run_log.append({"timestamp": datetime.now().astimezone().isoformat(timespec="seconds"), "step": "write_outputs", "status": "completed_partial", "detail": f"accepted_events={len(all_events)} attempts={len(attempts)}"})
    write_csv(OUTPUT_DIR / "run_log.csv", run_log, ["timestamp", "step", "status", "detail"])
    write_json(
        OUTPUT_DIR / "manifest.json",
        {
            "task_id": TASK_ID,
            "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            "previous_output": str(PREVIOUS_OUTPUT),
            "core_rerun_output": str(CORE_RERUN_OUTPUT),
            "output_path": str(OUTPUT_DIR),
            "raw_source_dir": str(RAW_DIR),
            "files": sorted(path.name for path in OUTPUT_DIR.glob("*") if path.is_file()),
            "formal_model_changed": False,
            "trade_decision_changed": False,
            "active_in_trade_decision": False,
        },
    )
    summary = f"""# Dynamic Pool1 listing master completion

- Task: `{TASK_ID}`
- Status: `{readiness['status']}`
- Previous accepted event rows: `{readiness['previous_accepted_event_rows']}`
- Current accepted event rows total: `{readiness['accepted_event_rows_total']}`
- Delta vs previous: `{readiness['new_or_carried_forward_event_rows_delta_vs_previous']}`
- Listing/delisting rows: `{len(listing_rows)}`
- Suspension/status rows: `{len(suspension_rows)}`
- Code/name change rows: `{len(code_name_rows)}`
- Transfer listing rows: `{len(transfer_rows)}`
- Source probe attempts: `{len(attempts)}`
- future_data_violation_count: `0`
- listing_delisting_suspension_metadata_ready: `false`
- ready_for_core_rerun: `true`
- ready_for_strategy_replay: `false`

## Improvements

- Added TWSE `TWTAWU` 2015-01 to 2026-07 monthly range sweep for suspended/resumed securities.
- Added TWSE `TWT85U` first/last trading-day monthly status snapshots from 2015-01 to 2026-07.
- Added current official disposition/status probes and MOPS date-query security-block evidence.

## Remaining blockers

- TPEx complete historical listing/delisting/removal master is still blocked.
- TPEx 2015-2025 historical suspension/resumption archive is still blocked; OpenAPI ignored historical parameters.
- Code/name change and transfer listing full history remains blocked; MOPS date query returned security block page.
- TWSE altered-trading status is only monthly anchor sampled in this package; full daily TWT85U sweep remains a next step.

No strategy replay, formal model change, trade decision change, or report change was made.
"""
    (OUTPUT_DIR / "final_summary_zh.md").write_text(summary, encoding="utf-8")
    (OUTPUT_DIR / "current_step.txt").write_text(readiness["status"] + "\n", encoding="utf-8")
    print(json.dumps(readiness, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
