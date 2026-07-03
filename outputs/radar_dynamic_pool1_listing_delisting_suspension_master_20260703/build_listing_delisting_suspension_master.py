from __future__ import annotations

import csv
import json
import re
import urllib.error
import urllib.request
from datetime import date, datetime
from pathlib import Path
from typing import Any


TASK_ID = "TASK-RADAR-DATA-DYNAMIC-POOL1-LISTING-DELISTING-SUSPENSION-MASTER-20260703"
OUTPUT_DIR = Path(__file__).resolve().parent
RAW_DIR = OUTPUT_DIR / "raw_sources"
UPSTREAM_FULL_SWEEP = (
    Path(__file__).resolve().parents[1]
    / "radar_dynamic_pool1_all_listed_liquid_universe_full_sweep_20260703"
)
REQUESTED_START = date(2015, 1, 1)
CURRENT_DATE = date(2026, 7, 3)


PROBES = [
    {
        "source_id": "twse_swagger",
        "market": "TWSE",
        "dataset": "endpoint_catalog",
        "url": "https://openapi.twse.com.tw/v1/swagger.json",
        "source_type": "official_endpoint_catalog",
        "acceptance_scope": "inventory",
    },
    {
        "source_id": "twse_company_newlisting",
        "market": "TWSE",
        "dataset": "listing_metadata",
        "url": "https://openapi.twse.com.tw/v1/company/newlisting",
        "source_type": "official_recent_listing_events",
        "acceptance_scope": "accepted_dated_rows_when_listing_date_present",
    },
    {
        "source_id": "twse_company_suspend_listing",
        "market": "TWSE",
        "dataset": "delisting_metadata",
        "url": "https://openapi.twse.com.tw/v1/company/suspendListingCsvAndHtml",
        "source_type": "official_delisting_events",
        "acceptance_scope": "accepted_dated_delisting_rows",
    },
    {
        "source_id": "twse_current_company_profile",
        "market": "TWSE",
        "dataset": "current_company_profile",
        "url": "https://openapi.twse.com.tw/v1/opendata/t187ap03_L",
        "source_type": "official_current_snapshot",
        "acceptance_scope": "proxy_only_not_used_for_2015_pit",
    },
    {
        "source_id": "twse_daily_material_information_current",
        "market": "TWSE",
        "dataset": "material_information_current",
        "url": "https://openapi.twse.com.tw/v1/opendata/t187ap04_L",
        "source_type": "official_current_daily_material_information",
        "acceptance_scope": "proxy_only_current_daily",
    },
    {
        "source_id": "tpex_swagger",
        "market": "TPEx",
        "dataset": "endpoint_catalog",
        "url": "https://www.tpex.org.tw/openapi/swagger.json",
        "source_type": "official_endpoint_catalog",
        "acceptance_scope": "inventory",
    },
    {
        "source_id": "tpex_spendi_history",
        "market": "TPEx",
        "dataset": "suspension_resumption_events",
        "url": "https://www.tpex.org.tw/openapi/v1/tpex_spendi_history",
        "source_type": "official_suspension_resumption_events",
        "acceptance_scope": "accepted_dated_suspension_resumption_rows",
    },
    {
        "source_id": "tpex_spendi_today",
        "market": "TPEx",
        "dataset": "suspension_resumption_events",
        "url": "https://www.tpex.org.tw/openapi/v1/tpex_spendi_today",
        "source_type": "official_current_suspension_resumption_events",
        "acceptance_scope": "accepted_dated_rows_if_event_fields_present",
    },
    {
        "source_id": "tpex_cmode_current",
        "market": "TPEx",
        "dataset": "current_trading_status",
        "url": "https://www.tpex.org.tw/openapi/v1/tpex_cmode",
        "source_type": "official_current_status_snapshot",
        "acceptance_scope": "proxy_only_current_status",
    },
    {
        "source_id": "tpex_current_company_profile",
        "market": "TPEx",
        "dataset": "current_company_profile",
        "url": "https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap03_O",
        "source_type": "official_current_snapshot",
        "acceptance_scope": "proxy_only_not_used_for_2015_pit",
    },
    {
        "source_id": "tpex_daily_material_information_current",
        "market": "TPEx",
        "dataset": "material_information_current",
        "url": "https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap04_O",
        "source_type": "official_current_daily_material_information",
        "acceptance_scope": "proxy_only_current_daily",
    },
    {
        "source_id": "tpex_operation_scope_stop_trading",
        "market": "TPEx",
        "dataset": "stop_trading_special_case",
        "url": "https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap26_O",
        "source_type": "official_current_special_case",
        "acceptance_scope": "candidate_empty_or_current_only",
    },
]


CSV_FIELDS_ATTEMPT = [
    "source_id",
    "market",
    "dataset",
    "url",
    "method",
    "status",
    "http_code",
    "content_type",
    "raw_row_count",
    "accepted_listing_rows",
    "accepted_suspension_rows",
    "proxy_rows",
    "date_field_detected",
    "min_event_date",
    "max_event_date",
    "retrieved_path",
    "error",
]

CSV_FIELDS_EVENT = [
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

CSV_FIELDS_PROXY = [
    "ticker",
    "name",
    "market",
    "source_id",
    "source_type",
    "source_date",
    "source_url",
    "proxy_reason",
    "formal_ready",
    "field_detected",
    "notes",
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


def fetch(url: str) -> tuple[int | None, str, bytes | None, str]:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 AI_stock_rotation_radar/metadata-probe",
            "Accept": "application/json,text/plain,*/*",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            return response.status, response.headers.get("content-type", ""), response.read(), ""
    except urllib.error.HTTPError as exc:
        return exc.code, exc.headers.get("content-type", ""), exc.read(), f"HTTPError: {exc}"
    except Exception as exc:  # noqa: BLE001 - source audit evidence
        return None, "", None, f"{type(exc).__name__}: {exc}"


def load_json(raw: bytes | None) -> Any:
    if raw is None:
        return None
    return json.loads(raw.decode("utf-8-sig"))


def save_raw(source_id: str, raw: bytes) -> Path:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    path = RAW_DIR / f"{source_id}.json"
    path.write_bytes(raw)
    return path


def clean(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def parse_roc_date(value: Any) -> str:
    text = clean(value)
    if not text:
        return ""
    digits = re.sub(r"\D", "", text)
    if len(digits) == 8 and digits.startswith("20"):
        yyyy = int(digits[:4])
        mm = int(digits[4:6])
        dd = int(digits[6:8])
    elif len(digits) == 7:
        yyyy = int(digits[:3]) + 1911
        mm = int(digits[3:5])
        dd = int(digits[5:7])
    elif len(digits) == 6:
        yyyy = int(digits[:2]) + 1911
        mm = int(digits[2:4])
        dd = int(digits[4:6])
    else:
        return ""
    try:
        parsed = date(yyyy, mm, dd)
    except ValueError:
        return ""
    return parsed.isoformat()


def in_requested_window(iso_date: str) -> bool:
    if not iso_date:
        return False
    parsed = date.fromisoformat(iso_date)
    return REQUESTED_START <= parsed <= CURRENT_DATE


def event_row(
    ticker: str,
    name: str,
    market: str,
    event_type: str,
    event_date: str,
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
        "source_date": CURRENT_DATE.isoformat(),
        "source_url": source_url,
        "source_id": source_id,
        "source_type": source_type,
        "formal_ready": "partial_event_row_not_full_master",
        "blocked_reason": "",
        "raw_event_date": raw_event_date,
        "notes": notes,
    }


def proxy_row(
    ticker: str,
    name: str,
    market: str,
    source_id: str,
    source_type: str,
    source_url: str,
    reason: str,
    field_detected: str,
    notes: str,
) -> dict[str, Any]:
    return {
        "ticker": ticker,
        "name": name,
        "market": market,
        "source_id": source_id,
        "source_type": source_type,
        "source_date": CURRENT_DATE.isoformat(),
        "source_url": source_url,
        "proxy_reason": reason,
        "formal_ready": "false",
        "field_detected": field_detected,
        "notes": notes,
    }


def parse_payload(probe: dict[str, str], payload: Any) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], str]:
    listing_rows: list[dict[str, Any]] = []
    suspension_rows: list[dict[str, Any]] = []
    proxy_rows: list[dict[str, Any]] = []
    source_id = probe["source_id"]
    market = probe["market"]
    url = probe["url"]
    source_type = probe["source_type"]

    if not isinstance(payload, list):
        return listing_rows, suspension_rows, proxy_rows, ""

    if source_id == "twse_company_newlisting":
        for item in payload:
            event_date = parse_roc_date(item.get("ListingDate") or item.get("ApprovedListingDate"))
            if in_requested_window(event_date):
                listing_rows.append(
                    event_row(
                        clean(item.get("Code")),
                        clean(item.get("Company")),
                        market,
                        "listing",
                        event_date,
                        url,
                        source_id,
                        source_type,
                        clean(item.get("ListingDate") or item.get("ApprovedListingDate")),
                        "TWSE recent listing endpoint; dated rows accepted, coverage remains incomplete.",
                    )
                )
        return listing_rows, suspension_rows, proxy_rows, "ListingDate|ApprovedListingDate"

    if source_id == "twse_company_suspend_listing":
        for item in payload:
            event_date = parse_roc_date(item.get("DelistingDate"))
            if in_requested_window(event_date):
                listing_rows.append(
                    event_row(
                        clean(item.get("Code")),
                        clean(item.get("Company")),
                        market,
                        "delisting",
                        event_date,
                        url,
                        source_id,
                        source_type,
                        clean(item.get("DelistingDate")),
                        "TWSE official terminated listing company endpoint.",
                    )
                )
        return listing_rows, suspension_rows, proxy_rows, "DelistingDate"

    if source_id in {"twse_current_company_profile", "tpex_current_company_profile"}:
        for item in payload[:5000]:
            ticker = clean(item.get("公司代號") or item.get("SecuritiesCompanyCode"))
            name = clean(item.get("公司簡稱") or item.get("公司名稱") or item.get("CompanyAbbreviation") or item.get("CompanyName"))
            fields = ",".join(sorted(str(key) for key in item.keys())[:20])
            proxy_rows.append(
                proxy_row(
                    ticker,
                    name,
                    market,
                    source_id,
                    source_type,
                    url,
                    "current_company_profile_snapshot_not_historical_master",
                    fields,
                    "Inventory only; not used to backfill historical listing membership.",
                )
            )
        return listing_rows, suspension_rows, proxy_rows, "current_snapshot_fields"

    if source_id == "tpex_spendi_history":
        for item in payload:
            ticker = clean(item.get("SecuritiesCompanyCode"))
            name = clean(item.get("CompanyName"))
            suspended = parse_roc_date(item.get("DateOfSuspendedTrading"))
            resumed = parse_roc_date(item.get("DateOfResumedTrading"))
            if in_requested_window(suspended):
                suspension_rows.append(
                    event_row(
                        ticker,
                        name,
                        market,
                        "suspension",
                        suspended,
                        url,
                        source_id,
                        source_type,
                        clean(item.get("DateOfSuspendedTrading")),
                        "TPEx historical suspended/resumed trading endpoint.",
                    )
                )
            if in_requested_window(resumed):
                suspension_rows.append(
                    event_row(
                        ticker,
                        name,
                        market,
                        "resumption",
                        resumed,
                        url,
                        source_id,
                        source_type,
                        clean(item.get("DateOfResumedTrading")),
                        "TPEx historical suspended/resumed trading endpoint.",
                    )
                )
        return listing_rows, suspension_rows, proxy_rows, "DateOfSuspendedTrading|DateOfResumedTrading"

    if source_id == "tpex_spendi_today":
        for item in payload:
            ticker = clean(item.get("SecuritiesCompanyCode"))
            name = clean(item.get("CompanyName"))
            source_date = parse_roc_date(item.get("Date")) or parse_roc_date(item.get("日期"))
            if ticker and clean(item.get("暫停交易")) and in_requested_window(source_date):
                suspension_rows.append(
                    event_row(ticker, name, market, "suspension", source_date, url, source_id, source_type, clean(item.get("Date")), "TPEx current-day suspension event.")
                )
            if ticker and clean(item.get("恢復交易")) and in_requested_window(source_date):
                suspension_rows.append(
                    event_row(ticker, name, market, "resumption", source_date, url, source_id, source_type, clean(item.get("Date")), "TPEx current-day resumption event.")
                )
        return listing_rows, suspension_rows, proxy_rows, "Date|暫停交易|恢復交易"

    if source_id in {"tpex_cmode_current", "twse_daily_material_information_current", "tpex_daily_material_information_current", "tpex_operation_scope_stop_trading"}:
        for item in payload[:5000]:
            ticker = clean(item.get("公司代號") or item.get("SecuritiesCompanyCode") or item.get("Code"))
            name = clean(item.get("公司名稱") or item.get("CompanyName") or item.get("Company"))
            fields = ",".join(sorted(str(key) for key in item.keys())[:20])
            proxy_rows.append(
                proxy_row(
                    ticker,
                    name,
                    market,
                    source_id,
                    source_type,
                    url,
                    "current_or_special_case_snapshot_not_full_historical_master",
                    fields,
                    "Recorded for endpoint contract only; not accepted as full 2015-latest master.",
                )
            )
        return listing_rows, suspension_rows, proxy_rows, "current_or_special_case_fields"

    return listing_rows, suspension_rows, proxy_rows, ""


def source_manifest() -> list[dict[str, Any]]:
    return [
        {
            "source_id": "twse_company_suspend_listing",
            "dataset": "listing_delisting_suspension_master",
            "source_name": "TWSE terminated listing companies",
            "source_url": "https://openapi.twse.com.tw/v1/company/suspendListingCsvAndHtml",
            "official_proxy_manual": "official",
            "coverage": "dated delisting rows available; coverage audit required before full formal master",
            "source_date_available": "true",
            "effective_date_available": "true_DelistingDate",
            "formal_ready": "partial_event_rows_not_full_master",
            "notes": "Accepted for dated TWSE delisting events only.",
        },
        {
            "source_id": "twse_company_newlisting",
            "dataset": "listing_delisting_suspension_master",
            "source_name": "TWSE recent listed companies",
            "source_url": "https://openapi.twse.com.tw/v1/company/newlisting",
            "official_proxy_manual": "official",
            "coverage": "recent listing rows only, not complete 2015-latest history",
            "source_date_available": "true",
            "effective_date_available": "true_ListingDate_or_ApprovedListingDate",
            "formal_ready": "partial_event_rows_not_full_master",
            "notes": "Accepted only for explicitly dated rows in requested window; not used as complete historical listing archive.",
        },
        {
            "source_id": "tpex_spendi_history",
            "dataset": "listing_delisting_suspension_master",
            "source_name": "TPEx historical suspended/resumed trading stocks",
            "source_url": "https://www.tpex.org.tw/openapi/v1/tpex_spendi_history",
            "official_proxy_manual": "official",
            "coverage": "endpoint returns dated suspension/resumption rows; observed coverage is not full 2015-latest",
            "source_date_available": "true",
            "effective_date_available": "true_DateOfSuspendedTrading_or_DateOfResumedTrading",
            "formal_ready": "partial_event_rows_not_full_master",
            "notes": "Accepted for dated TPEx suspension/resumption events only.",
        },
        {
            "source_id": "twse_current_company_profile",
            "dataset": "listing_delisting_suspension_master",
            "source_name": "TWSE current listed company profile",
            "source_url": "https://openapi.twse.com.tw/v1/opendata/t187ap03_L",
            "official_proxy_manual": "official_current_snapshot",
            "coverage": "current snapshot only",
            "source_date_available": "true",
            "effective_date_available": "current only",
            "formal_ready": "false",
            "notes": "Proxy inventory only; not used to backfill 2015 PIT membership.",
        },
        {
            "source_id": "tpex_current_company_profile",
            "dataset": "listing_delisting_suspension_master",
            "source_name": "TPEx current company profile",
            "source_url": "https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap03_O",
            "official_proxy_manual": "official_current_snapshot",
            "coverage": "current snapshot only",
            "source_date_available": "true",
            "effective_date_available": "current only",
            "formal_ready": "false",
            "notes": "Proxy inventory only; not used to backfill 2015 PIT membership.",
        },
    ]


def build_coverage(listing_rows: list[dict[str, Any]], suspension_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for year in range(2015, 2027):
        for market in ["TWSE", "TPEx"]:
            market_listing = [row for row in listing_rows if row["market"] == market and row["event_date"].startswith(str(year))]
            market_suspension = [row for row in suspension_rows if row["market"] == market and row["event_date"].startswith(str(year))]
            if market_listing or market_suspension:
                status = "partial_event_rows_available"
            else:
                status = "no_accepted_master_rows_observed"
            out.append(
                {
                    "year": year,
                    "market": market,
                    "listing_delisting_event_rows": len(market_listing),
                    "suspension_resumption_event_rows": len(market_suspension),
                    "coverage_status": status,
                    "formal_master_ready": "false",
                    "notes": "Event rows are source-backed but not a complete listing/delisting/suspension master.",
                }
            )
    return out


def main() -> int:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    (OUTPUT_DIR / "current_step.txt").write_text("running_official_metadata_probes\n", encoding="utf-8")
    started = datetime.now().astimezone().isoformat(timespec="seconds")

    attempts: list[dict[str, Any]] = []
    listing_rows: list[dict[str, Any]] = []
    suspension_rows: list[dict[str, Any]] = []
    proxy_rows: list[dict[str, Any]] = []
    run_log: list[dict[str, Any]] = [{"timestamp": started, "step": "start", "status": "running", "detail": TASK_ID}]

    for probe in PROBES:
        http_code, content_type, raw, error = fetch(probe["url"])
        retrieved_path = ""
        raw_count = 0
        date_field_detected = ""
        probe_listing_rows: list[dict[str, Any]] = []
        probe_suspension_rows: list[dict[str, Any]] = []
        probe_proxy_rows: list[dict[str, Any]] = []
        status = "failed"

        if raw is not None and http_code == 200:
            raw_path = save_raw(probe["source_id"], raw)
            retrieved_path = str(raw_path)
            try:
                payload = load_json(raw)
                raw_count = len(payload) if isinstance(payload, list) else 0
                probe_listing_rows, probe_suspension_rows, probe_proxy_rows, date_field_detected = parse_payload(probe, payload)
                listing_rows.extend(probe_listing_rows)
                suspension_rows.extend(probe_suspension_rows)
                proxy_rows.extend(probe_proxy_rows)
                status = "retrieved"
                error = ""
            except Exception as exc:  # noqa: BLE001 - source audit evidence
                status = "parse_failed"
                error = f"{type(exc).__name__}: {exc}"

        event_dates = [row["event_date"] for row in [*probe_listing_rows, *probe_suspension_rows] if row.get("event_date")]
        attempts.append(
            {
                "source_id": probe["source_id"],
                "market": probe["market"],
                "dataset": probe["dataset"],
                "url": probe["url"],
                "method": "GET",
                "status": status,
                "http_code": http_code if http_code is not None else "",
                "content_type": content_type,
                "raw_row_count": raw_count,
                "accepted_listing_rows": len(probe_listing_rows),
                "accepted_suspension_rows": len(probe_suspension_rows),
                "proxy_rows": len(probe_proxy_rows),
                "date_field_detected": date_field_detected,
                "min_event_date": min(event_dates) if event_dates else "",
                "max_event_date": max(event_dates) if event_dates else "",
                "retrieved_path": retrieved_path,
                "error": error,
            }
        )
        run_log.append(
            {
                "timestamp": datetime.now().astimezone().isoformat(timespec="seconds"),
                "step": "probe_source",
                "status": status,
                "detail": f"{probe['source_id']} listing={len(probe_listing_rows)} suspension={len(probe_suspension_rows)} proxy={len(probe_proxy_rows)}",
            }
        )

    blocked_rows = [
        {
            "dataset": "listing_delisting_suspension_master",
            "market": "TWSE",
            "blocked_requirement": "complete 2015-latest suspension/resumption master",
            "blocked_reason": "TWSE swagger exposed current material information and delisting/listing endpoints, but no full historical suspension/resumption event archive was confirmed in this bounded probe.",
            "next_programmatic_source": "Probe TWSE historical material-information archive/query endpoints or daily status files for suspended/resumed securities.",
            "formal_ready": "false",
        },
        {
            "dataset": "listing_delisting_suspension_master",
            "market": "TPEx",
            "blocked_requirement": "complete 2015-latest listing/delisting master",
            "blocked_reason": "TPEx swagger exposed suspension/resumption history and current profile/status endpoints, but no complete historical delisting/listing archive endpoint was confirmed.",
            "next_programmatic_source": "Probe TPEx historical delisting/removal pages and downloadable archives beyond current OpenAPI catalog.",
            "formal_ready": "false",
        },
        {
            "dataset": "listing_delisting_suspension_master",
            "market": "TWSE/TPEx",
            "blocked_requirement": "code/name change and transfer listing master",
            "blocked_reason": "Current material-information feeds can contain name changes, but current-day feeds are not a complete historical master.",
            "next_programmatic_source": "Build bounded MOPS/TWSE/TPEx material-information archive query for name_change/transfer keywords by date range.",
            "formal_ready": "false",
        },
    ]

    coverage = build_coverage(listing_rows, suspension_rows)
    source_rows = source_manifest()
    future_audit = [
        {
            "audit_id": "accepted_event_rows",
            "future_data_violation_count": 0,
            "decision": "accepted_only_when_event_date_present_and_within_requested_window",
            "evidence": "Rows use explicit official event date fields; rows outside 2015-01-01 to 2026-07-03 are excluded.",
        },
        {
            "audit_id": "current_snapshot_exclusion",
            "future_data_violation_count": 0,
            "decision": "current snapshots kept in proxy_source_rows_only",
            "evidence": "TWSE/TPEx current company profiles and current status endpoints are not copied into accepted master rows.",
        },
    ]

    write_csv(OUTPUT_DIR / "source_probe_attempts.csv", attempts, CSV_FIELDS_ATTEMPT)
    write_csv(OUTPUT_DIR / "accepted_listing_metadata_rows.csv", listing_rows, CSV_FIELDS_EVENT)
    write_csv(OUTPUT_DIR / "accepted_suspension_event_rows.csv", suspension_rows, CSV_FIELDS_EVENT)
    write_csv(OUTPUT_DIR / "proxy_source_rows.csv", proxy_rows[:10000], CSV_FIELDS_PROXY)
    write_csv(
        OUTPUT_DIR / "blocked_source_rows.csv",
        blocked_rows,
        ["dataset", "market", "blocked_requirement", "blocked_reason", "next_programmatic_source", "formal_ready"],
    )
    write_csv(
        OUTPUT_DIR / "coverage_by_year_market.csv",
        coverage,
        ["year", "market", "listing_delisting_event_rows", "suspension_resumption_event_rows", "coverage_status", "formal_master_ready", "notes"],
    )
    write_csv(OUTPUT_DIR / "future_data_violation_audit.csv", future_audit, ["audit_id", "future_data_violation_count", "decision", "evidence"])
    write_csv(
        OUTPUT_DIR / "source_manifest.csv",
        source_rows,
        ["source_id", "dataset", "source_name", "source_url", "official_proxy_manual", "coverage", "source_date_available", "effective_date_available", "formal_ready", "notes"],
    )
    write_json(OUTPUT_DIR / "source_manifest.json", {"task_id": TASK_ID, "sources": source_rows})
    write_csv(
        OUTPUT_DIR / "completed.csv",
        [
            {
                "task_id": TASK_ID,
                "status": "completed_partial_event_sources_but_master_ready_false",
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
                "status": "master_metadata_blocked",
                "failed_item": "complete_listing_delisting_suspension_master",
                "reason": "Partial official event rows were acquired, but complete 2015-latest TWSE/TPEx listing/delisting/suspension master is not ready.",
            }
        ],
        ["task_id", "status", "failed_item", "reason"],
    )
    run_log.append(
        {
            "timestamp": datetime.now().astimezone().isoformat(timespec="seconds"),
            "step": "write_outputs",
            "status": "completed_partial",
            "detail": f"listing_rows={len(listing_rows)} suspension_rows={len(suspension_rows)} proxy_rows={len(proxy_rows)}",
        }
    )
    write_csv(OUTPUT_DIR / "run_log.csv", run_log, ["timestamp", "step", "status", "detail"])

    coverage_statuses = {row["coverage_status"] for row in coverage}
    readiness = {
        "task_id": TASK_ID,
        "status": "completed_partial_event_sources_but_master_ready_false",
        "accepted_listing_metadata_rows": len(listing_rows),
        "accepted_suspension_event_rows": len(suspension_rows),
        "proxy_source_rows": len(proxy_rows),
        "blocked_source_rows": len(blocked_rows),
        "listing_delisting_suspension_metadata_ready": False,
        "ready_for_core_rerun": True,
        "ready_for_strategy_replay": False,
        "dynamic_pool1_shadow_challenger_ready": False,
        "formal_model_changed": False,
        "trade_decision_changed": False,
        "active_in_trade_decision": False,
        "future_data_violation_count": 0,
        "coverage_statuses": sorted(coverage_statuses),
        "coverage_by_year_market": str(OUTPUT_DIR / "coverage_by_year_market.csv"),
        "core_input_hint": {
            "accepted_listing_metadata_rows": str(OUTPUT_DIR / "accepted_listing_metadata_rows.csv"),
            "accepted_suspension_event_rows": str(OUTPUT_DIR / "accepted_suspension_event_rows.csv"),
            "source_probe_attempts": str(OUTPUT_DIR / "source_probe_attempts.csv"),
            "proxy_source_rows": str(OUTPUT_DIR / "proxy_source_rows.csv"),
            "blocked_source_rows": str(OUTPUT_DIR / "blocked_source_rows.csv"),
        },
        "readiness_decision": "partial official event rows available, but not a complete master for Dynamic Pool1 replay",
        "next_programmatic_sources": [
            "Probe TWSE historical suspension/resumption status archive or MOPS/TWSE material-information date query for stopped/resumed trading keywords.",
            "Probe TPEx historical listing/delisting/removal archive outside current OpenAPI catalog.",
            "Build MOPS/TWSE/TPEx date-range material-information crawler for name_change and transfer listing events.",
        ],
    }
    write_json(OUTPUT_DIR / "readiness_for_core.json", readiness)
    write_json(
        OUTPUT_DIR / "manifest.json",
        {
            "task_id": TASK_ID,
            "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            "upstream_full_sweep_output": str(UPSTREAM_FULL_SWEEP),
            "output_path": str(OUTPUT_DIR),
            "raw_source_dir": str(RAW_DIR),
            "files": sorted(path.name for path in OUTPUT_DIR.glob("*") if path.is_file()),
            "formal_model_changed": False,
            "trade_decision_changed": False,
            "active_in_trade_decision": False,
        },
    )
    summary = f"""# Dynamic Pool1 listing / delisting / suspension master metadata

- Task: `{TASK_ID}`
- Status: `completed_partial_event_sources_but_master_ready_false`
- Accepted listing/delisting metadata rows: `{len(listing_rows)}`
- Accepted suspension/resumption event rows: `{len(suspension_rows)}`
- Proxy/current snapshot rows: `{len(proxy_rows)}`
- Blocked source rows: `{len(blocked_rows)}`
- listing_delisting_suspension_metadata_ready: `false`
- ready_for_core_rerun: `true`
- ready_for_strategy_replay: `false`
- future_data_violation_count: `0`

## Accepted partial event sources

- TWSE `/company/suspendListingCsvAndHtml` produced dated official delisting rows.
- TWSE `/company/newlisting` produced dated recent listing rows where `ListingDate` or `ApprovedListingDate` was present.
- TPEx `/tpex_spendi_history` produced dated suspension/resumption rows.

These rows are source-backed event evidence, but they are not a complete 2015-latest master. Dynamic Pool1 cannot use this package alone as a formal tradable-universe master.

## Proxy-only sources

TWSE/TPEx current company profile and current status endpoints were saved to `proxy_source_rows.csv` only. They were not used to infer 2015 historical membership, delisting, suspension, resumption, transfer listing, or name change state.

## Remaining blockers

- TWSE full historical suspension/resumption master was not found in this bounded OpenAPI probe.
- TPEx complete historical listing/delisting master was not found in this bounded OpenAPI probe.
- Code/name change and transfer listing master still needs a date-range MOPS/TWSE/TPEx material-information crawler.

## Boundary

No strategy replay, formal model change, trade decision change, or report change was made.
"""
    (OUTPUT_DIR / "final_summary_zh.md").write_text(summary, encoding="utf-8")
    (OUTPUT_DIR / "current_step.txt").write_text("completed_partial_event_sources_but_master_ready_false\n", encoding="utf-8")
    print(json.dumps(readiness, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
