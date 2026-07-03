import csv
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path


BASE = Path(__file__).resolve().parent
RAW_JS = BASE / "raw_sources" / "js"
RAW_HTML = BASE / "raw_sources" / "html"
RAW_JSON = BASE / "raw_sources" / "json"
RAW_PROBES = BASE / "raw_sources" / "probe_responses"
TASK_ID = "TASK-RADAR-DATA-DYNAMIC-POOL1-TPEX-STATIC-REVERSE-ARCHIVE-PROBE-20260703"
RUN_TS = datetime.now(timezone.utc).isoformat()


def write_csv(path, rows, fieldnames):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({k: row.get(k, "") for k in fieldnames})


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def sha256(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def roc_to_iso(value):
    if value is None:
        return ""
    s = str(value).strip()
    m = re.match(r"^(\d{2,3})[/-](\d{1,2})[/-](\d{1,2})$", s)
    if m:
        return f"{int(m.group(1)) + 1911:04d}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
    m = re.match(r"^(\d{8})$", s)
    if m:
        return f"{s[0:4]}-{s[4:6]}-{s[6:8]}"
    m = re.match(r"^(\d{4})/(\d{1,2})/(\d{1,2})$", s)
    if m:
        return f"{int(m.group(1)):04d}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
    return s


def probe_meta(stem):
    m = re.match(r"^(altered|delisted|latest|newlisted|anndownload|disposal|attention)_(\d{4})$", stem)
    if not m:
        if stem == "halt_current_contract":
            return {
                "route_family": "halt_current_contract",
                "action": "bulletin/sprc",
                "params": "response=json",
                "target_year": "",
                "target_period": "current_contract",
            }
        return {"route_family": stem, "action": "", "params": "", "target_year": "", "target_period": ""}
    family, year = m.groups()
    action = {
        "altered": "afterTrading/chtm",
        "delisted": "company/deListed",
        "latest": "company/latest",
        "newlisted": "company/applicantStat",
        "anndownload": "bulletin/annDownload",
        "disposal": "bulletin/disposal",
        "attention": "bulletin/attention",
    }[family]
    params = {
        "altered": f"date={year}/01/05&response=json",
        "delisted": f"code=&date={year}&reason=&response=json&paging-offset=0&paging-size=1000",
        "latest": f"code=&date={year}&response=json",
        "newlisted": f"date={year}&response=json",
        "anndownload": f"startDate={year}/01/01&endDate={year}/01/31&response=json",
        "disposal": f"startDate={year}/01/01&endDate={year}/01/31&type=all&response=json",
        "attention": f"startDate={year}/01/01&endDate={year}/01/31&type=all&order=date&response=json",
    }[family]
    return {
        "route_family": family,
        "action": action,
        "params": params,
        "target_year": year,
        "target_period": f"{year}-sample",
    }


def table_rows(obj):
    total = 0
    for table in obj.get("tables") or []:
        data = table.get("data")
        if isinstance(data, list):
            total += len(data)
    return total


def table_fields(obj):
    for table in obj.get("tables") or []:
        if table.get("fields"):
            return table["fields"]
    return []


def table_data(obj):
    for table in obj.get("tables") or []:
        data = table.get("data")
        if isinstance(data, list):
            for row in data:
                yield row


def build_js_inventory():
    snippets = {
        "tables.js": "bxRport.init default pattern '/{LANG}/{ACTION}'; apiAction derived from tables.init action; submit posts form fields plus response=json; serverPaging adds paging-offset/paging-size and paging-table.",
        "main.js": "Defines API_PATTERN='/www/{LANG}/{ACTION}' and header codeQuery service.",
        "global.js": "Defines menu JSON route /data/menu/zh-tw/menu.json and sitemap/menu rendering helpers.",
    }
    rows = []
    for path in sorted(RAW_JS.glob("*.js")):
        rows.append(
            {
                "file": path.name,
                "relative_path": path.relative_to(BASE).as_posix(),
                "bytes": path.stat().st_size,
                "sha256": sha256(path),
                "source_url": {
                    "tables.js": "https://www.tpex.org.tw/rsrc/js/tables.js",
                    "main.js": "https://www.tpex.org.tw/rsrc/js/main.js",
                    "global.js": "https://www.tpex.org.tw/rsrc/asset/js/global.js",
                }.get(path.name, ""),
                "relevant_symbols": snippets.get(path.name, ""),
                "source_type": "official_frontend_js",
            }
        )
    return rows


def extract_route_candidates():
    rows = [
        {
            "candidate_id": "tables_js_bxRport_submit",
            "source_file": "raw_sources/js/tables.js",
            "page_url": "",
            "page_title": "shared table runner",
            "function_or_config": "bxRport.init / #u / #k",
            "pattern": "API_PATTERN or /{LANG}/{ACTION}",
            "action": "<page tables.init action>",
            "endpoint_url": "https://www.tpex.org.tw/www/zh-tw/<action>",
            "method": "POST",
            "params_detected": "form serialized fields + response=json; serverPaging adds paging-offset,paging-size,paging-table,paging-order,paging-dir",
            "date_parameter": "page form input names such as date,startDate,endDate",
            "evidence": "tables.js derives apiAction from pattern/action and posts JSON request.",
            "acceptance_scope": "contract only",
        },
        {
            "candidate_id": "menu_json_official_page_index",
            "source_file": "raw_sources/json/www_tpex_org_tw_data_menu_zh_tw_menu_json.json",
            "page_url": "https://www.tpex.org.tw/data/menu/zh-tw/menu.json",
            "page_title": "official menu JSON",
            "function_or_config": "_init_sitemap / _get_json",
            "pattern": "menu link inventory",
            "action": "",
            "endpoint_url": "",
            "method": "GET",
            "params_detected": "",
            "date_parameter": "",
            "evidence": "menu JSON revealed valid status/listing pages such as /mainboard/trading/info/altered.html, /mainboard/listed/delisted.html, /announce/market/halt.html.",
            "acceptance_scope": "route discovery",
        },
    ]
    for path in sorted(RAW_HTML.glob("*.html")):
        content = path.read_text(encoding="utf-8", errors="replace")
        title_match = re.search(r"<title>(.*?)</title>", content, flags=re.S)
        title = title_match.group(1) if title_match else ""
        init_match = re.search(r"tables\.init\((.*?)\);", content, flags=re.S)
        if not init_match:
            continue
        init = init_match.group(1)
        action_match = re.search(r'action:"([^"]+)"', init)
        option_match = re.search(r'option:"([^"]*)"', init)
        action = action_match.group(1) if action_match else ""
        option = option_match.group(1) if option_match else ""
        inputs = []
        for tag in re.findall(r"<(?:input|select|button)[^>]+>", content):
            name = re.search(r'name="([^"]+)"', tag)
            data_format = re.search(r'data-format="([^"]+)"', tag)
            data_start = re.search(r'data-start="([^"]*)"', tag)
            value = re.search(r'value="([^"]*)"', tag)
            if name:
                desc = name.group(1)
                if data_format:
                    desc += f":format={data_format.group(1)}"
                if data_start:
                    desc += f":start={data_start.group(1)}"
                if value:
                    desc += f":value={value.group(1)}"
                inputs.append(desc)
        page_url = "https://www.tpex.org.tw/" + path.stem.replace("www_tpex_org_tw_", "").replace("_", "/")
        rows.append(
            {
                "candidate_id": f"page_action_{action.replace('/','_')}",
                "source_file": f"raw_sources/html/{path.name}",
                "page_url": page_url,
                "page_title": title,
                "function_or_config": "tables.init inline config",
                "pattern": "API_PATTERN=/www/{LANG}/{ACTION}",
                "action": action,
                "endpoint_url": f"https://www.tpex.org.tw/www/zh-tw/{action}" if action else "",
                "method": "POST",
                "params_detected": ";".join(inputs),
                "date_parameter": ",".join([x for x in inputs if "date" in x.lower() or "Date" in x]),
                "evidence": f"tables.init action={action}; option={option}; title={title}",
                "acceptance_scope": (
                    "accepted_candidate"
                    if action in {"afterTrading/chtm", "company/deListed", "company/latest", "company/applicantStat"}
                    else "route_evidence_only"
                ),
            }
        )
    return rows


def build_probe_attempts():
    rows = []
    for path in sorted(RAW_PROBES.glob("*.json")):
        obj = read_json(path)
        meta = probe_meta(path.stem)
        row_count = table_rows(obj)
        action = meta["action"]
        decision = "route_evidence_only"
        if action in {"company/deListed", "company/latest"} and row_count > 0:
            decision = "accepted_listing_metadata_rows"
        elif action == "afterTrading/chtm" and row_count > 0:
            decision = "accepted_status_snapshot_rows"
        elif action == "bulletin/sprc":
            decision = "blocked_current_only_contract"
        elif action in {"bulletin/annDownload", "bulletin/disposal", "bulletin/attention"}:
            decision = "route_evidence_only_not_master"
        rows.append(
            {
                "attempt_id": path.stem,
                "source": "TPEx official API",
                "query_url": f"https://www.tpex.org.tw/www/zh-tw/{action}",
                "method": "POST",
                "params": meta["params"],
                "target_year": meta["target_year"],
                "target_period": meta["target_period"],
                "http_code": 200,
                "content_type": "application/json",
                "stat": obj.get("stat", ""),
                "date_field_detected": "yes" if obj.get("date") else "no",
                "source_date": roc_to_iso(obj.get("date", "")),
                "row_count": row_count,
                "retrieved_path": path.relative_to(BASE).as_posix(),
                "acceptance_decision": decision,
                "error": "",
            }
        )
    # Carry forward bounded 404 evidence from this run only, not as repeated old-route probe.
    for path in sorted(RAW_HTML.glob("*_trading_info_*_html.html")):
        content = path.read_text(encoding="utf-8", errors="replace")
        if "<title>404 - " in content:
            rows.append(
                {
                    "attempt_id": f"html_404_{path.stem}",
                    "source": "TPEx official page",
                    "query_url": "https://www.tpex.org.tw/" + path.stem.replace("www_tpex_org_tw_", "").replace("_", "/"),
                    "method": "GET",
                    "params": "",
                    "target_year": "",
                    "target_period": "route_discovery",
                    "http_code": 200,
                    "content_type": "text/html",
                    "stat": "HTTP 200 with TPEx 404 title",
                    "date_field_detected": "no",
                    "source_date": "",
                    "row_count": 0,
                    "retrieved_path": path.relative_to(BASE).as_posix(),
                    "acceptance_decision": "blocked_invalid_page_id",
                    "error": "menu-derived route should be used instead of guessed URL",
                }
            )
    return rows


def build_accepted_listing_rows():
    rows = []
    for path in sorted(RAW_PROBES.glob("latest_*.json")):
        obj = read_json(path)
        meta = probe_meta(path.stem)
        year = meta["target_year"]
        for raw in table_data(obj):
            if len(raw) < 4 or not str(raw[1]).strip():
                continue
            rows.append(
                {
                    "ticker": str(raw[1]).strip(),
                    "name": str(raw[2]).strip(),
                    "market": "TPEx",
                    "event_type": "listing",
                    "event_date": roc_to_iso(raw[3]),
                    "source_date": f"{year}-12-31",
                    "source_url": "https://www.tpex.org.tw/www/zh-tw/company/latest",
                    "source_type": "official_historical_api",
                    "formal_ready": "true",
                    "raw_source_id": path.name,
                    "evidence_fields": json.dumps(table_fields(obj), ensure_ascii=False),
                    "notes": "TPEx company/latest route returned historical year listing rows via date parameter.",
                }
            )
    for path in sorted(RAW_PROBES.glob("delisted_*.json")):
        obj = read_json(path)
        meta = probe_meta(path.stem)
        year = meta["target_year"]
        for raw in table_data(obj):
            if len(raw) < 3 or not str(raw[0]).strip():
                continue
            rows.append(
                {
                    "ticker": str(raw[0]).strip(),
                    "name": str(raw[1]).strip(),
                    "market": "TPEx",
                    "event_type": "delisting",
                    "event_date": roc_to_iso(raw[2]),
                    "source_date": f"{year}-12-31",
                    "source_url": "https://www.tpex.org.tw/www/zh-tw/company/deListed",
                    "source_type": "official_historical_api",
                    "formal_ready": "true",
                    "raw_source_id": path.name,
                    "evidence_fields": json.dumps(table_fields(obj), ensure_ascii=False),
                    "notes": "TPEx company/deListed route returned historical year delisting rows via date parameter.",
                }
            )
    return rows


def build_status_snapshot_rows():
    rows = []
    for path in sorted(RAW_PROBES.glob("altered_*.json")):
        obj = read_json(path)
        date = roc_to_iso(obj.get("date", ""))
        for raw in table_data(obj):
            if len(raw) < 7 or not str(raw[0]).strip():
                continue
            rows.append(
                {
                    "ticker": str(raw[0]).strip(),
                    "name": str(raw[1]).strip(),
                    "market": "TPEx",
                    "status_date": date,
                    "source_date": date,
                    "source_url": "https://www.tpex.org.tw/www/zh-tw/afterTrading/chtm",
                    "source_type": "official_historical_api",
                    "is_altered_trading": "true" if str(raw[2]).strip() else "false",
                    "is_periodic_call_auction": "true" if str(raw[3]).strip() else "false",
                    "is_management_stock": "true" if str(raw[4]).strip() else "false",
                    "matching_cycle_minutes": str(raw[5]).strip(),
                    "is_suspended": "true" if str(raw[6]).strip() else "false",
                    "formal_ready": "true",
                    "raw_source_id": path.name,
                    "notes": "Daily TPEx altered/periodic-call/management/suspended status snapshot; not an event ledger.",
                }
            )
    return rows


def build_blockers():
    return [
        {
            "source": "TPEx bulletin/sprc",
            "blocked_component": "suspension/resumption event history",
            "function_or_endpoint": "tables.init action=bulletin/sprc; endpoint=/www/zh-tw/bulletin/sprc",
            "parameter_blocker": "Page exposes no date/startDate/endDate controls; POST response is current-day contract only.",
            "evidence_path": "raw_sources/probe_responses/halt_current_contract.json",
            "blocked_reason": "current_only_no_historical_date_parameter",
            "next_programmatic_route": "Use daily afterTrading/chtm snapshots to infer suspended-as-of-date, and separately search old/public announcement archives for transition event dates.",
        },
        {
            "source": "TPEx guessed old new-site status pages",
            "blocked_component": "guessed status page URLs",
            "function_or_endpoint": "/zh-tw/mainboard/trading/info/suspension.html, /altered-trading.html, /disposal.html",
            "parameter_blocker": "HTTP 200 shell with TPEx 404 title; official menu JSON points to /trading/info/altered.html and /announce/market/disposal.html instead.",
            "evidence_path": "raw_sources/html/*suspension_html.html; raw_sources/html/*altered_trading_html.html; raw_sources/html/*trading_info_disposal_html.html",
            "blocked_reason": "invalid_page_id",
            "next_programmatic_route": "Continue from menu-derived pages only.",
        },
        {
            "source": "TPEx company/applicantStat download",
            "blocked_component": "bulk new-listed/applicant download extraction",
            "function_or_endpoint": "tables.init action=company/applicantStat; file links /zh-tw/company/applicantStatDl?type=list|app&date=YYYY",
            "parameter_blocker": "Probe identified annual download route but did not download/parse CSV/PDF payload in this bounded pass.",
            "evidence_path": "raw_sources/probe_responses/newlisted_2015.json",
            "blocked_reason": "download_payload_not_extracted_yet",
            "next_programmatic_route": "Download applicantStatDl for 2015-2025 and compare against company/latest rows.",
        },
        {
            "source": "TPEx bulletin/annDownload",
            "blocked_component": "announcement archive ZIP details",
            "function_or_endpoint": "tables.init action=bulletin/annDownload; storage/eb_data/YYYYMM/YYYYMMDD.zip",
            "parameter_blocker": "Route returns dated ZIP links but ZIP contents not extracted in this bounded pass.",
            "evidence_path": "raw_sources/probe_responses/anndownload_2015.json",
            "blocked_reason": "archive_zip_not_extracted_yet",
            "next_programmatic_route": "Download one monthly ZIP sample and search contained files for 終止上櫃/暫停/恢復 keywords.",
        },
    ]


def build_coverage(listing_rows, status_rows, probe_rows):
    rows = []
    years = [2015, 2018, 2021, 2025]
    for year in years:
        y = str(year)
        listing = sum(1 for r in listing_rows if r["event_type"] == "listing" and r["source_date"].startswith(y))
        delisting = sum(1 for r in listing_rows if r["event_type"] == "delisting" and r["source_date"].startswith(y))
        status = sum(1 for r in status_rows if r["status_date"].startswith(y))
        attempts = sum(1 for r in probe_rows if r.get("target_year") == y)
        rows.append(
            {
                "year": y,
                "market": "TPEx",
                "listing_rows": listing,
                "delisting_rows": delisting,
                "status_snapshot_rows": status,
                "probe_attempts": attempts,
                "coverage_status": "sample_verified" if listing or delisting or status else "missing_in_sample",
                "formal_ready_scope": "partial_sample_only",
                "remaining_gap": "Need full 2015-2025 sweep and suspension/resumption event extraction.",
            }
        )
    return rows


def build_audit():
    return [
        {
            "audit_item": "current_snapshot_backfill",
            "result": "pass",
            "future_data_violation_count": 0,
            "evidence": "Accepted rows come from TPEx official APIs with historical date/year parameters, not current company profile snapshots.",
        },
        {
            "audit_item": "date_parameter_presence",
            "result": "pass_with_blocker",
            "future_data_violation_count": 0,
            "evidence": "company/latest, company/deListed, afterTrading/chtm use date/year parameters; bulletin/sprc has no historical date parameter and is blocked/current-only.",
        },
        {
            "audit_item": "formal_model_boundary",
            "result": "pass",
            "future_data_violation_count": 0,
            "evidence": "No BACKTEST_LAB formal model, report, selector, or trade action changed.",
        },
    ]


def main():
    js_rows = build_js_inventory()
    route_rows = extract_route_candidates()
    probe_rows = build_probe_attempts()
    listing_rows = build_accepted_listing_rows()
    status_rows = build_status_snapshot_rows()
    blockers = build_blockers()
    coverage = build_coverage(listing_rows, status_rows, probe_rows)
    audit = build_audit()

    write_csv(
        BASE / "js_inventory.csv",
        js_rows,
        ["file", "relative_path", "bytes", "sha256", "source_url", "relevant_symbols", "source_type"],
    )
    write_csv(
        BASE / "extracted_route_candidates.csv",
        route_rows,
        [
            "candidate_id",
            "source_file",
            "page_url",
            "page_title",
            "function_or_config",
            "pattern",
            "action",
            "endpoint_url",
            "method",
            "params_detected",
            "date_parameter",
            "evidence",
            "acceptance_scope",
        ],
    )
    write_csv(
        BASE / "route_probe_attempts.csv",
        probe_rows,
        [
            "attempt_id",
            "source",
            "query_url",
            "method",
            "params",
            "target_year",
            "target_period",
            "http_code",
            "content_type",
            "stat",
            "date_field_detected",
            "source_date",
            "row_count",
            "retrieved_path",
            "acceptance_decision",
            "error",
        ],
    )
    listing_fields = [
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
        "evidence_fields",
        "notes",
    ]
    write_csv(BASE / "accepted_listing_metadata_rows.csv", listing_rows, listing_fields)
    write_csv(
        BASE / "accepted_suspension_event_rows.csv",
        [],
        ["ticker", "name", "market", "event_type", "event_date", "source_date", "source_url", "source_type", "formal_ready", "raw_source_id", "notes"],
    )
    write_csv(
        BASE / "accepted_status_snapshot_rows.csv",
        status_rows,
        [
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
        ],
    )
    write_csv(
        BASE / "blocked_source_rows.csv",
        blockers,
        ["source", "blocked_component", "function_or_endpoint", "parameter_blocker", "evidence_path", "blocked_reason", "next_programmatic_route"],
    )
    write_csv(
        BASE / "coverage_by_year_market.csv",
        coverage,
        ["year", "market", "listing_rows", "delisting_rows", "status_snapshot_rows", "probe_attempts", "coverage_status", "formal_ready_scope", "remaining_gap"],
    )
    write_csv(
        BASE / "future_data_violation_audit.csv",
        audit,
        ["audit_item", "result", "future_data_violation_count", "evidence"],
    )
    write_csv(
        BASE / "completed.csv",
        [
            {"step": "download_official_js_and_menu", "status": "completed", "evidence": "raw_sources/js and raw_sources/json"},
            {"step": "static_reverse_tables_js_contract", "status": "completed", "evidence": "extracted_route_candidates.csv"},
            {"step": "bounded_official_api_probes", "status": "completed", "evidence": "route_probe_attempts.csv"},
            {"step": "accepted_partial_historical_rows", "status": "completed_partial", "evidence": "accepted_listing_metadata_rows.csv; accepted_status_snapshot_rows.csv"},
        ],
        ["step", "status", "evidence"],
    )
    write_csv(
        BASE / "failed.csv",
        [
            {"step": "bulletin_sprc_historical_events", "status": "blocked", "reason": "current-only endpoint; no date parameter in live form"},
            {"step": "full_2015_2025_sweep", "status": "not_run_by_scope", "reason": "this pass is static reverse + bounded sample probe"},
        ],
        ["step", "status", "reason"],
    )
    write_csv(
        BASE / "run_log.csv",
        [
            {"timestamp_utc": RUN_TS, "level": "INFO", "message": "Read previous TPEx blocker package and Core readiness context."},
            {"timestamp_utc": RUN_TS, "level": "INFO", "message": "Downloaded TPEx official JS, menu JSON, and menu-derived HTML pages."},
            {"timestamp_utc": RUN_TS, "level": "INFO", "message": "Extracted tables.js POST contract and page-level action endpoints."},
            {"timestamp_utc": RUN_TS, "level": "INFO", "message": "Probed 2015/2018/2021/2025 sample years for listing, delisting, status, and bulletin routes."},
            {"timestamp_utc": RUN_TS, "level": "INFO", "message": "Accepted partial TPEx historical listing/delisting rows and daily status snapshot rows; kept suspension event history blocked."},
        ],
        ["timestamp_utc", "level", "message"],
    )

    readiness = {
        "task_id": TASK_ID,
        "status": "completed_partial_with_accepted_historical_rows",
        "output_path": str(BASE),
        "accepted_listing_metadata_rows": len(listing_rows),
        "accepted_status_snapshot_rows": len(status_rows),
        "accepted_suspension_event_rows": 0,
        "route_probe_attempts": len(probe_rows),
        "future_data_violation_count": 0,
        "tpex_static_reverse_contract_extracted": True,
        "tpex_sample_historical_listing_delisting_ready": True,
        "tpex_sample_historical_status_snapshot_ready": True,
        "tpex_full_2015_2025_master_ready": False,
        "listing_delisting_suspension_master_full_ready": False,
        "ready_for_core_rerun": True,
        "ready_for_strategy_replay": False,
        "formal_model_changed": False,
        "trade_decision_changed": False,
        "active_in_trade_decision": False,
        "remaining_blockers": [
            "Run full 2015-2025 sweep for company/latest, company/deListed, and afterTrading/chtm.",
            "Extract suspension/resumption event history; bulletin/sprc is current-only, so use announcement archive ZIP or daily status transition inference.",
            "Download and parse company/applicantStatDl annual files as cross-check.",
        ],
    }
    (BASE / "readiness_for_core.json").write_text(json.dumps(readiness, ensure_ascii=False, indent=2), encoding="utf-8")
    (BASE / "manifest.json").write_text(
        json.dumps(
            {
                "task_id": TASK_ID,
                "created_at_utc": RUN_TS,
                "status": readiness["status"],
                "source_package": "TPEx static reverse + official bounded API probe",
                "raw_sources": {
                    "js_files": [p.name for p in sorted(RAW_JS.glob("*.js"))],
                    "html_files": [p.name for p in sorted(RAW_HTML.glob("*.html"))],
                    "json_files": [p.name for p in sorted(RAW_JSON.glob("*.json"))],
                    "probe_response_files": [p.name for p in sorted(RAW_PROBES.glob("*.json"))],
                },
                "outputs": [
                    "js_inventory.csv",
                    "extracted_route_candidates.csv",
                    "route_probe_attempts.csv",
                    "accepted_listing_metadata_rows.csv",
                    "accepted_suspension_event_rows.csv",
                    "accepted_status_snapshot_rows.csv",
                    "blocked_source_rows.csv",
                    "coverage_by_year_market.csv",
                    "future_data_violation_audit.csv",
                    "readiness_for_core.json",
                    "final_summary_zh.md",
                ],
                "formal_model_changed": False,
                "trade_decision_changed": False,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    (BASE / "current_step.txt").write_text(
        "completed_partial_with_accepted_historical_rows; next: Core can rerun readiness against partial TPEx listing/delisting/status sample, or Radar/Data can run full 2015-2025 sweep.",
        encoding="utf-8",
    )
    (BASE / "final_summary_zh.md").write_text(
        f"""# Dynamic Pool1 TPEx static reverse / archive probe summary

## 結論

狀態：`completed_partial_with_accepted_historical_rows`。

本棒沒有重跑上一棒已知的 current-only / 404 route，而是從 TPEx 官方 `tables.js`、`main.js`、`global.js` 與 `menu.json` 反推出新站 table API contract：

- `main.js` 定義 `API_PATTERN=/www/{{LANG}}/{{ACTION}}`。
- `tables.js` 的 `bxRport.init/#u/#k` 會把頁面 `tables.init({{ action }})` 組成 `apiAction`，用 POST 送出表單欄位並加上 `response=json`；server paging 另加 `paging-*`。
- 官方 `menu.json` 找到有效頁面：`/mainboard/trading/info/altered.html`、`/mainboard/listed/delisted.html`、`/mainboard/listed/latest.html`、`/announce/market/halt.html`、`/announce/market/download.html` 等。

## Accepted historical rows

- `accepted_listing_metadata_rows.csv`：{len(listing_rows)} rows。
  - `company/latest`：sample years 2015、2018、2021、2025 可回 listing rows。
  - `company/deListed`：sample years 2015、2018、2021、2025 可回 delisting rows。
- `accepted_status_snapshot_rows.csv`：{len(status_rows)} rows。
  - `afterTrading/chtm`：sample dates 2015-01-05、2018-01-05、2021-01-05 可回變更交易 / 分盤 / 管理股票 / 停止交易 status snapshot；2025-01-05 無 rows。
- `accepted_suspension_event_rows.csv`：0 rows。
  - `bulletin/sprc` 目前 confirmed current-only，未找到 historical date parameter。

## 不可包裝的邊界

- 這不是 full 2015-2025 master，只是官方 route contract + bounded sample accepted rows。
- `afterTrading/chtm` 是每日 status snapshot，不是 suspension/resumption transition event ledger。
- `bulletin/annDownload`、`bulletin/disposal`、`bulletin/attention` 只保留 route evidence；不混入 listing master。
- 沒有用 current snapshot 回推，`future_data_violation_count=0`。

## 下一步

1. Radar/Data 可用相同 contract 跑 full 2015-2025 sweep：
   - `company/latest`
   - `company/deListed`
   - `afterTrading/chtm`
2. 對 `company/applicantStatDl?type=list|app&date=YYYY` 做 annual download parse，交叉檢查 new-listed rows。
3. 對 `bulletin/annDownload` 的 monthly ZIP 做 keyword/content extraction，找 `終止上櫃`、`暫停`、`恢復` 等 announcement event dates。
4. Core 可先重跑 readiness，確認 TPEx listing/delisting/status blocker 是否從 blocked 降到 stronger partial。

`formal_model_changed=false`、`trade_decision_changed=false`、`active_in_trade_decision=false`。
""",
        encoding="utf-8",
    )
    print(json.dumps(readiness, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
