from __future__ import annotations

import csv
import json
from datetime import datetime
from pathlib import Path
from typing import Any


TASK_ID = "TASK-RADAR-DATA-DYNAMIC-POOL1-TPEX-HISTORICAL-LISTING-STATUS-MASTER-20260703"
OUTPUT_DIR = Path(__file__).resolve().parent
PREVIOUS_OUTPUT = OUTPUT_DIR.parents[0] / "radar_dynamic_pool1_listing_master_completion_20260703"
CORE_OUTPUT = (
    Path(r"C:\Users\zergv\Documents\Codex\2026-05-30\ep05-chat-ai-stock-backtest-lab")
    / "outputs"
    / "dynamic_pool1_pit_readiness_after_listing_master_completion_20260703"
)


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


def main() -> int:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUTPUT_DIR / "current_step.txt").write_text("building_blocked_with_attempt_evidence_package\n", encoding="utf-8")
    started = datetime.now().astimezone().isoformat(timespec="seconds")

    previous_listing = read_csv(PREVIOUS_OUTPUT / "accepted_listing_metadata_rows.csv")
    previous_suspension = read_csv(PREVIOUS_OUTPUT / "accepted_suspension_event_rows.csv")
    previous_code_name = read_csv(PREVIOUS_OUTPUT / "accepted_code_name_change_rows.csv")
    previous_transfer = read_csv(PREVIOUS_OUTPUT / "accepted_transfer_listing_rows.csv")
    previous_attempts = read_csv(PREVIOUS_OUTPUT / "source_probe_attempts.csv")

    tpex_carried_rows = [
        row
        for row in [*previous_listing, *previous_suspension, *previous_code_name, *previous_transfer]
        if row.get("market") == "TPEx"
    ]
    tpex_carried_current_2026_rows = [
        row
        for row in tpex_carried_rows
        if str(row.get("event_date", "")).startswith("2026")
    ]

    attempts = [
        {
            "source_id": "core_latest_readiness",
            "market": "TPEx",
            "route_family": "core_output",
            "route": str(CORE_OUTPUT / "readiness.json"),
            "target_period": "2015-2025",
            "status": "read_local_contract",
            "http_code": "",
            "content_type": "application/json",
            "result_class": "tpex_2015_2025_still_blocked",
            "accepted_historical_rows": 0,
            "accepted_current_or_carried_rows": len(tpex_carried_current_2026_rows),
            "error": "",
            "evidence": "Core latest readiness marks TPEx 2015-2025 blocked and cross-market master not ready.",
        },
        {
            "source_id": "previous_tpex_openapi_spendi_history",
            "market": "TPEx",
            "route_family": "openapi",
            "route": "https://www.tpex.org.tw/openapi/v1/tpex_spendi_history?startDate=20150101&endDate=20150131",
            "target_period": "2015-01",
            "status": "retrieved_but_ignored_historical_params",
            "http_code": "200",
            "content_type": "application/json",
            "result_class": "current_only_or_param_ignored",
            "accepted_historical_rows": 0,
            "accepted_current_or_carried_rows": 178,
            "error": "Historical startDate/endDate parameters were ignored; endpoint returned ROC year 115 rows in prior package.",
            "evidence": "Recorded in previous output source_probe_attempts.csv as tpex_spendi_history_no_param_support.",
        },
        {
            "source_id": "tpex_web_stock_aftertrading_root",
            "market": "TPEx",
            "route_family": "old_web_root",
            "route": "https://www.tpex.org.tw/web/stock/aftertrading/",
            "target_period": "route_inventory",
            "status": "retrieved",
            "http_code": "200",
            "content_type": "text/html",
            "result_class": "root_page_no_direct_historical_status_endpoint",
            "accepted_historical_rows": 0,
            "accepted_current_or_carried_rows": 0,
            "error": "",
            "evidence": "Root page returned valid HTML and generic trading links, but no direct spendi/cmode/delist historical endpoint was found from bounded link extraction.",
        },
        {
            "source_id": "tpex_new_site_stock_pricing",
            "market": "TPEx",
            "route_family": "new_site_page",
            "route": "https://www.tpex.org.tw/zh-tw/mainboard/trading/info/stock-pricing.html",
            "target_period": "route_inventory",
            "status": "retrieved",
            "http_code": "200",
            "content_type": "text/html",
            "result_class": "valid_page_not_listing_status_master",
            "accepted_historical_rows": 0,
            "accepted_current_or_carried_rows": 0,
            "error": "",
            "evidence": "Valid TPEx page; data attributes show stock pricing table route, not historical listing/status master.",
        },
        {
            "source_id": "tpex_new_site_guessed_pages",
            "market": "TPEx",
            "route_family": "new_site_guessed_pages",
            "route": "trading-calendar.html; attention.html; disposal.html; suspension.html; altered-trading.html",
            "target_period": "route_inventory",
            "status": "http_200_404_html",
            "http_code": "200",
            "content_type": "text/html",
            "result_class": "not_found_pages",
            "accepted_historical_rows": 0,
            "accepted_current_or_carried_rows": 0,
            "error": "TPEx site returned 404 title HTML for guessed pages.",
            "evidence": "Bounded page probes returned title '404 - 證券櫃檯買賣中心'.",
        },
        {
            "source_id": "tpex_frontend_js_inventory",
            "market": "TPEx",
            "route_family": "frontend_js",
            "route": "https://www.tpex.org.tw/rsrc/js/tables.js ; /rsrc/asset/js/global.js ; /rsrc/js/main.js",
            "target_period": "route_inventory",
            "status": "retrieved_not_reversed",
            "http_code": "200",
            "content_type": "application/javascript",
            "result_class": "needs_static_reverse_followup",
            "accepted_historical_rows": 0,
            "accepted_current_or_carried_rows": 0,
            "error": "JS files retrieved/inspected only at token-limited keyword level; no exact historical TPEx status route extracted before user requested convergence.",
            "evidence": "JS files contain generic api/query/pathname logic; follow-up should reverse table URL construction for specific page ids.",
        },
        {
            "source_id": "mops_ajax_t05st02_security_probe",
            "market": "TWSE/TPEx",
            "route_family": "mops_material_information",
            "route": "https://mops.twse.com.tw/mops/web/ajax_t05st02",
            "target_period": "2015-01 and 2026-07 samples",
            "status": "blocked_security_page",
            "http_code": "200",
            "content_type": "text/html",
            "result_class": "security_block",
            "accepted_historical_rows": 0,
            "accepted_current_or_carried_rows": 0,
            "error": "MOPS returned FOR SECURITY REASONS page even with referer/session probe in previous package.",
            "evidence": "Previous package raw_sources/mops_ajax_t05st02_security_probe/*.html.",
        },
    ]

    status_fields = [
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
    tpex_accepted_historical_rows: list[dict[str, Any]] = []
    tpex_accepted_current_or_carried_rows = tpex_carried_current_2026_rows

    blocked_rows = [
        {
            "dataset": "tpex_historical_listing_status_master",
            "market": "TPEx",
            "blocked_requirement": "2015-2025 historical suspension/resumption route",
            "blocked_reason": "OpenAPI tpex_spendi_history ignored historical params and returned ROC year 115 only; no accepted 2015-2025 rows.",
            "next_programmatic_source": "Reverse TPEx frontend JS table URL construction for spendi/status pages or locate official historical downloads outside OpenAPI.",
            "formal_ready": "false",
        },
        {
            "dataset": "tpex_historical_listing_status_master",
            "market": "TPEx",
            "blocked_requirement": "2015-2025 historical listing/delisting/removal route",
            "blocked_reason": "Bounded official OpenAPI and new/old site page probes did not identify a complete historical delisting/removal archive.",
            "next_programmatic_source": "Search/reverse TPEx official archives for terminated TPEx listings and transfer-to-TWSE files; use browser/devtools only if approved.",
            "formal_ready": "false",
        },
        {
            "dataset": "full_cross_market_listing_master",
            "market": "TWSE/TPEx",
            "blocked_requirement": "complete cross-market master",
            "blocked_reason": "TWSE has stronger partial status coverage from previous package, but TPEx 2015-2025 remains blocked; full cross-market master is not ready.",
            "next_programmatic_source": "After TPEx route is found, merge with prior TWSE accepted rows and rerun Core readiness.",
            "formal_ready": "false",
        },
        {
            "dataset": "material_information_code_transfer",
            "market": "TWSE/TPEx",
            "blocked_requirement": "date-range material information crawler for code/name change and transfer listing",
            "blocked_reason": "MOPS ajax_t05st02 direct/session probe returned security block page; no browser/devtools approval path used in this converged package.",
            "next_programmatic_source": "Use browser/devtools exact request extraction or alternate official bulk archive if strategy center approves.",
            "formal_ready": "false",
        },
    ]

    coverage = []
    for year in range(2015, 2027):
        for market in ["TWSE", "TPEx"]:
            if market == "TWSE":
                status = "carried_forward_stronger_partial_from_previous_package"
                notes = "TWSE rows are carried forward from radar_dynamic_pool1_listing_master_completion_20260703; this task did not rerun TWSE full daily TWT85U."
                accepted = "carried_forward"
            elif year == 2026 and tpex_accepted_current_or_carried_rows:
                status = "current_year_partial_carried_forward_only"
                notes = "TPEx 2026 suspension/resumption rows exist from previous OpenAPI current-year output; not a 2015-2025 historical solution."
                accepted = len(tpex_accepted_current_or_carried_rows)
            else:
                status = "blocked_no_accepted_historical_rows"
                notes = "No accepted TPEx historical rows acquired for this year in this package."
                accepted = 0
            coverage.append(
                {
                    "year": year,
                    "market": market,
                    "coverage_status": status,
                    "accepted_rows": accepted,
                    "formal_master_ready": "false",
                    "notes": notes,
                }
            )

    source_manifest = [
        {
            "source_id": "previous_cross_market_master_completion",
            "dataset": "full_cross_market_listing_master",
            "source_name": "Prior Radar listing master completion package",
            "source_url": str(PREVIOUS_OUTPUT),
            "official_proxy_manual": "mixed_official_source_package",
            "coverage": "TWSE stronger partial; TPEx 2026 current partial only",
            "source_date_available": "true_for_accepted_rows",
            "effective_date_available": "true_for_accepted_rows",
            "formal_ready": "false",
            "notes": "Carried forward for context; not reclassified as formal-ready.",
        },
        {
            "source_id": "tpex_spendi_history_no_param_support",
            "dataset": "tpex_historical_suspension_resumption",
            "source_name": "TPEx OpenAPI tpex_spendi_history with historical params",
            "source_url": "https://www.tpex.org.tw/openapi/v1/tpex_spendi_history?startDate=20150101&endDate=20150131",
            "official_proxy_manual": "official_endpoint_blocked_for_history",
            "coverage": "current ROC year only; historical params ignored",
            "source_date_available": "true_for_current_rows_only",
            "effective_date_available": "true_for_current_rows_only",
            "formal_ready": "false",
            "notes": "No accepted 2015-2025 historical rows.",
        },
        {
            "source_id": "tpex_site_route_inventory",
            "dataset": "tpex_route_discovery",
            "source_name": "TPEx old/new site route probes",
            "source_url": "https://www.tpex.org.tw/web/stock/aftertrading/ ; https://www.tpex.org.tw/zh-tw/mainboard/trading/info/stock-pricing.html",
            "official_proxy_manual": "official_route_inventory",
            "coverage": "bounded route discovery only",
            "source_date_available": "not_applicable",
            "effective_date_available": "not_applicable",
            "formal_ready": "false",
            "notes": "Route inventory produced no accepted historical TPEx metadata rows.",
        },
    ]

    future_audit = [
        {
            "audit_id": "no_new_tpex_historical_accepted_rows",
            "future_data_violation_count": 0,
            "decision": "No current snapshot or current-year TPEx rows were accepted as 2015-2025 historical rows.",
            "evidence": "accepted_status_snapshot_rows.csv is header-only; current/carried TPEx 2026 rows are separated.",
        },
        {
            "audit_id": "current_snapshot_exclusion",
            "future_data_violation_count": 0,
            "decision": "Current snapshots/proxy rows remain excluded from formal historical PIT rows.",
            "evidence": "proxy/current rows are not copied into accepted historical files.",
        },
    ]

    run_log = [
        {"timestamp": started, "step": "start", "status": "running", "detail": TASK_ID},
        {"timestamp": datetime.now().astimezone().isoformat(timespec="seconds"), "step": "read_core_and_prior_outputs", "status": "completed", "detail": f"prior_tpex_current_rows={len(tpex_accepted_current_or_carried_rows)}"},
        {"timestamp": datetime.now().astimezone().isoformat(timespec="seconds"), "step": "write_converged_attempt_package", "status": "completed", "detail": "No new accepted TPEx 2015-2025 historical rows; route evidence captured."},
    ]

    attempt_fields = [
        "source_id",
        "market",
        "route_family",
        "route",
        "target_period",
        "status",
        "http_code",
        "content_type",
        "result_class",
        "accepted_historical_rows",
        "accepted_current_or_carried_rows",
        "error",
        "evidence",
    ]
    write_csv(OUTPUT_DIR / "source_probe_attempts.csv", attempts, attempt_fields)
    write_csv(OUTPUT_DIR / "accepted_listing_metadata_rows.csv", [], status_fields)
    write_csv(OUTPUT_DIR / "accepted_suspension_event_rows.csv", [], status_fields)
    write_csv(OUTPUT_DIR / "accepted_status_snapshot_rows.csv", tpex_accepted_historical_rows, status_fields)
    write_csv(OUTPUT_DIR / "accepted_current_or_carried_tpex_rows.csv", tpex_accepted_current_or_carried_rows, status_fields)
    write_csv(OUTPUT_DIR / "blocked_source_rows.csv", blocked_rows, ["dataset", "market", "blocked_requirement", "blocked_reason", "next_programmatic_source", "formal_ready"])
    write_csv(OUTPUT_DIR / "coverage_by_year_market.csv", coverage, ["year", "market", "coverage_status", "accepted_rows", "formal_master_ready", "notes"])
    write_csv(OUTPUT_DIR / "future_data_violation_audit.csv", future_audit, ["audit_id", "future_data_violation_count", "decision", "evidence"])
    write_csv(
        OUTPUT_DIR / "source_manifest.csv",
        source_manifest,
        ["source_id", "dataset", "source_name", "source_url", "official_proxy_manual", "coverage", "source_date_available", "effective_date_available", "formal_ready", "notes"],
    )
    write_json(OUTPUT_DIR / "source_manifest.json", {"task_id": TASK_ID, "sources": source_manifest})
    write_csv(OUTPUT_DIR / "run_log.csv", run_log, ["timestamp", "step", "status", "detail"])

    readiness = {
        "task_id": TASK_ID,
        "status": "blocked_with_attempt_evidence",
        "accepted_historical_rows": 0,
        "accepted_listing_metadata_rows": 0,
        "accepted_suspension_event_rows": 0,
        "accepted_status_snapshot_rows": 0,
        "accepted_current_or_carried_tpex_rows": len(tpex_accepted_current_or_carried_rows),
        "source_probe_attempts": len(attempts),
        "blocked_source_rows": len(blocked_rows),
        "tpex_2015_2025_historical_listing_status_ready": False,
        "full_cross_market_listing_master_ready": False,
        "listing_delisting_suspension_metadata_ready": False,
        "ready_for_core_rerun": True,
        "ready_for_strategy_replay": False,
        "dynamic_pool1_shadow_challenger_ready": False,
        "formal_model_changed": False,
        "trade_decision_changed": False,
        "active_in_trade_decision": False,
        "future_data_violation_count": 0,
        "readiness_decision": "No new TPEx 2015-2025 accepted historical rows; package captures bounded route evidence and remaining blockers.",
        "core_input_hint": {
            "source_probe_attempts": str(OUTPUT_DIR / "source_probe_attempts.csv"),
            "blocked_source_rows": str(OUTPUT_DIR / "blocked_source_rows.csv"),
            "coverage_by_year_market": str(OUTPUT_DIR / "coverage_by_year_market.csv"),
            "accepted_status_snapshot_rows": str(OUTPUT_DIR / "accepted_status_snapshot_rows.csv"),
        },
        "next_programmatic_sources": [
            "Reverse TPEx frontend table URL construction in /rsrc/js/tables.js for a concrete historical status/listing page id.",
            "Search TPEx official archived downloads for terminated TPEx listings and transfer-to-TWSE events.",
            "Use browser/devtools exact request extraction for TPEx if strategy center approves external browser capture.",
            "Use browser/devtools or alternate official bulk archive for MOPS ajax_t05st02 material-information date query if approved.",
        ],
    }
    write_json(OUTPUT_DIR / "readiness_for_core.json", readiness)
    write_json(
        OUTPUT_DIR / "manifest.json",
        {
            "task_id": TASK_ID,
            "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            "output_path": str(OUTPUT_DIR),
            "previous_output": str(PREVIOUS_OUTPUT),
            "core_output": str(CORE_OUTPUT),
            "files": sorted(path.name for path in OUTPUT_DIR.glob("*") if path.is_file()),
            "formal_model_changed": False,
            "trade_decision_changed": False,
            "active_in_trade_decision": False,
        },
    )
    write_csv(
        OUTPUT_DIR / "completed.csv",
        [
            {
                "task_id": TASK_ID,
                "status": "blocked_with_attempt_evidence",
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
                "status": "blocked_with_attempt_evidence",
                "failed_item": "tpex_2015_2025_historical_listing_status_master",
                "reason": "Bounded official route probes did not identify or retrieve accepted TPEx 2015-2025 historical rows.",
            }
        ],
        ["task_id", "status", "failed_item", "reason"],
    )
    summary = f"""# TPEx historical listing/status master

- Task: `{TASK_ID}`
- Status: `blocked_with_attempt_evidence`
- Accepted TPEx 2015-2025 historical rows: `0`
- Accepted listing metadata rows: `0`
- Accepted suspension event rows: `0`
- Accepted status snapshot rows: `0`
- Current/carried TPEx 2026 rows from previous package: `{len(tpex_accepted_current_or_carried_rows)}`
- Source probe attempts recorded: `{len(attempts)}`
- future_data_violation_count: `0`
- full_cross_market_listing_master_ready: `false`
- ready_for_core_rerun: `true`

## What was confirmed

- Core latest readiness still marks TPEx 2015-2025 as the leading blocker.
- Previous TPEx OpenAPI `tpex_spendi_history` ignores historical parameters and returns current ROC year 115 rows.
- TPEx old `/web/stock/aftertrading/` root is reachable but bounded link extraction did not expose a direct historical spendi/cmode/delist route.
- TPEx new `stock-pricing.html` is valid, but the guessed status/disposal/suspension/altered pages returned TPEx 404 HTML.
- MOPS material-information date query remains security-blocked.

## Decision

No current snapshot, current-year row, or proxy row was accepted as 2015-2025 TPEx historical metadata. This package is intentionally blocked/partial with evidence, not formal-ready.

## Next programmable routes

- Reverse TPEx frontend table URL construction in `/rsrc/js/tables.js` for concrete page ids.
- Locate TPEx official archived downloads for terminated listings/removals and transfer-to-TWSE events.
- Use browser/devtools exact request extraction for TPEx or MOPS only if approved.
"""
    (OUTPUT_DIR / "final_summary_zh.md").write_text(summary, encoding="utf-8")
    (OUTPUT_DIR / "current_step.txt").write_text("blocked_with_attempt_evidence\n", encoding="utf-8")
    print(json.dumps(readiness, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
