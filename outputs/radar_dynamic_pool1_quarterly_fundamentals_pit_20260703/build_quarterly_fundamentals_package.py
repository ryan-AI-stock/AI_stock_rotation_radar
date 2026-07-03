from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path


TASK_ID = "TASK-RADAR-DATA-DYNAMIC-POOL1-QUARTERLY-FUNDAMENTALS-PIT-20260703"
BASE = Path("outputs/radar_dynamic_pool1_quarterly_fundamentals_pit_20260703")
CORE_READINESS = Path(
    r"C:\Users\zergv\Documents\Codex\2026-05-30\ep05-chat-ai-stock-backtest-lab\outputs\dynamic_pool1_pit_readiness_after_mops_monthly_revenue_20260703"
)
RUN_TS = datetime.now(timezone.utc).isoformat()

PROBE_FIELDS = [
    "attempt_id",
    "source_family",
    "route",
    "method",
    "target",
    "url",
    "params",
    "http_code",
    "content_type",
    "response_length",
    "row_count",
    "ticker_like_count",
    "status",
    "release_date_available",
    "accepted_for_pit",
    "error",
    "evidence",
]


def write_csv(path: Path, rows: list[dict[str, object]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fields})


def build_package() -> dict[str, object]:
    BASE.mkdir(parents=True, exist_ok=True)
    attempts = [
        {
            "attempt_id": "get_t163sb04_shell",
            "source_family": "MOPS financial summary",
            "route": "t163sb04",
            "method": "GET",
            "target": "page shell",
            "url": "https://mops.twse.com.tw/mops/web/t163sb04",
            "params": "",
            "http_code": 200,
            "content_type": "text/html",
            "response_length": 65,
            "row_count": 0,
            "ticker_like_count": 0,
            "status": "shell_too_short",
            "release_date_available": "unknown",
            "accepted_for_pit": "false",
            "error": "",
            "evidence": "GET shell returned only 65 bytes; insufficient to parse route contract.",
        },
        {
            "attempt_id": "ajax_t163sb04_2024Q4_sii",
            "source_family": "MOPS financial summary",
            "route": "ajax_t163sb04",
            "method": "POST",
            "target": "TWSE 2024Q4",
            "url": "https://mops.twse.com.tw/mops/web/ajax_t163sb04",
            "params": "encodeURIComponent=1&step=1&firstin=1&off=1&TYPEK=sii&year=113&season=04",
            "http_code": 200,
            "content_type": "text/html; charset=UTF-8",
            "response_length": 686,
            "row_count": 0,
            "ticker_like_count": 0,
            "status": "security_block",
            "release_date_available": "unknown",
            "accepted_for_pit": "false",
            "error": "FOR SECURITY REASONS, THIS PAGE CAN NOT BE ACCESSED",
            "evidence": "MOPS returned security page, not data table.",
        },
        {
            "attempt_id": "ajax_t163sb04_2024Q4_otc",
            "source_family": "MOPS financial summary",
            "route": "ajax_t163sb04",
            "method": "POST",
            "target": "TPEx 2024Q4",
            "url": "https://mops.twse.com.tw/mops/web/ajax_t163sb04",
            "params": "encodeURIComponent=1&step=1&firstin=1&off=1&TYPEK=otc&year=113&season=04",
            "http_code": 200,
            "content_type": "text/html; charset=UTF-8",
            "response_length": 686,
            "row_count": 0,
            "ticker_like_count": 0,
            "status": "security_block",
            "release_date_available": "unknown",
            "accepted_for_pit": "false",
            "error": "FOR SECURITY REASONS, THIS PAGE CAN NOT BE ACCESSED",
            "evidence": "MOPS returned security page, not data table.",
        },
        {
            "attempt_id": "ajax_t163sb05_2024Q4_sii",
            "source_family": "MOPS financial ratio",
            "route": "ajax_t163sb05",
            "method": "POST",
            "target": "TWSE 2024Q4",
            "url": "https://mops.twse.com.tw/mops/web/ajax_t163sb05",
            "params": "encodeURIComponent=1&step=1&firstin=1&off=1&TYPEK=sii&year=113&season=04",
            "http_code": 200,
            "content_type": "text/html; charset=UTF-8",
            "response_length": 686,
            "row_count": 0,
            "ticker_like_count": 0,
            "status": "security_block",
            "release_date_available": "unknown",
            "accepted_for_pit": "false",
            "error": "FOR SECURITY REASONS, THIS PAGE CAN NOT BE ACCESSED",
            "evidence": "MOPS returned security page, not data table.",
        },
        {
            "attempt_id": "ajax_t163sb06_2024Q4_sii",
            "source_family": "MOPS financial ratio",
            "route": "ajax_t163sb06",
            "method": "POST",
            "target": "TWSE 2024Q4",
            "url": "https://mops.twse.com.tw/mops/web/ajax_t163sb06",
            "params": "encodeURIComponent=1&step=1&firstin=1&off=1&TYPEK=sii&year=113&season=04",
            "http_code": 200,
            "content_type": "text/html; charset=UTF-8",
            "response_length": 686,
            "row_count": 0,
            "ticker_like_count": 0,
            "status": "security_block",
            "release_date_available": "unknown",
            "accepted_for_pit": "false",
            "error": "FOR SECURITY REASONS, THIS PAGE CAN NOT BE ACCESSED",
            "evidence": "MOPS returned security page, not data table.",
        },
        {
            "attempt_id": "ajax_t163sb04_2015Q4_sii",
            "source_family": "MOPS financial summary",
            "route": "ajax_t163sb04",
            "method": "POST",
            "target": "TWSE 2015Q4",
            "url": "https://mops.twse.com.tw/mops/web/ajax_t163sb04",
            "params": "encodeURIComponent=1&step=1&firstin=1&off=1&TYPEK=sii&year=104&season=04",
            "http_code": 200,
            "content_type": "text/html; charset=UTF-8",
            "response_length": 686,
            "row_count": 0,
            "ticker_like_count": 0,
            "status": "security_block",
            "release_date_available": "unknown",
            "accepted_for_pit": "false",
            "error": "FOR SECURITY REASONS, THIS PAGE CAN NOT BE ACCESSED",
            "evidence": "MOPS returned security page for historical quarter sample.",
        },
        {
            "attempt_id": "xbrl_zip_guess_2024Q4",
            "source_family": "MOPS XBRL/static download",
            "route": "server-java/FileDownLoad",
            "method": "GET",
            "target": "2024Q4 zip guess",
            "url": "https://mops.twse.com.tw/server-java/FileDownLoad?step=9&functionName=t164sb01&filePath=/tifrs/2024/&fileName=tifrs-2024Q4.zip",
            "params": "",
            "http_code": 404,
            "content_type": "",
            "response_length": 0,
            "row_count": 0,
            "ticker_like_count": 0,
            "status": "not_found",
            "release_date_available": "unknown",
            "accepted_for_pit": "false",
            "error": "404",
            "evidence": "Guessed static XBRL zip path not valid.",
        },
        {
            "attempt_id": "ajax_t164sb04_2024Q4_sii",
            "source_family": "MOPS XBRL",
            "route": "ajax_t164sb04",
            "method": "GET",
            "target": "TWSE 2024Q4",
            "url": "https://mops.twse.com.tw/mops/web/ajax_t164sb04",
            "params": "encodeURIComponent=1&step=1&firstin=1&off=1&TYPEK=sii&year=113&season=04",
            "http_code": 200,
            "content_type": "text/html; charset=UTF-8",
            "response_length": 686,
            "row_count": 0,
            "ticker_like_count": 0,
            "status": "security_block",
            "release_date_available": "unknown",
            "accepted_for_pit": "false",
            "error": "FOR SECURITY REASONS, THIS PAGE CAN NOT BE ACCESSED",
            "evidence": "MOPS returned security page.",
        },
    ]

    source_manifest = [
        {
            "source_id": "mops_t163sb04_candidate",
            "source_name": "MOPS quarterly financial summary",
            "source_url_or_pattern": "https://mops.twse.com.tw/mops/web/ajax_t163sb04",
            "source_type": "official_ajax_candidate",
            "markets": "TWSE;TPEx",
            "coverage_probe": "2015Q4;2024Q4",
            "release_date_available": "not_confirmed",
            "accepted_for_pit": "false",
            "decision": "blocked_security_page",
        },
        {
            "source_id": "mops_t163sb05_t163sb06_candidate",
            "source_name": "MOPS quarterly financial ratios / fields",
            "source_url_or_pattern": "https://mops.twse.com.tw/mops/web/ajax_t163sb05; ajax_t163sb06",
            "source_type": "official_ajax_candidate",
            "markets": "TWSE;TPEx",
            "coverage_probe": "2024Q4",
            "release_date_available": "not_confirmed",
            "accepted_for_pit": "false",
            "decision": "blocked_security_page",
        },
        {
            "source_id": "mops_xbrl_static_candidate",
            "source_name": "MOPS XBRL/static download candidate",
            "source_url_or_pattern": "server-java/FileDownLoad or t164 routes",
            "source_type": "official_download_candidate",
            "markets": "TWSE;TPEx",
            "coverage_probe": "2024Q4",
            "release_date_available": "not_confirmed",
            "accepted_for_pit": "false",
            "decision": "route_not_resolved",
        },
    ]

    blocked_rows = [
        {
            "dataset": "quarterly_fundamentals_pit",
            "blocked_component": "MOPS ajax financial table data",
            "blocked_reason": "MOPS returned security page for direct ajax probes",
            "evidence": "source_probe_attempts.csv status=security_block",
            "next_programmatic_source": "Use browser/devtools exact request extraction with valid session and hidden anti-CSRF fields, or MOPS open XBRL bulk download if exact path can be resolved.",
        },
        {
            "dataset": "quarterly_fundamentals_pit",
            "blocked_component": "filing/release date",
            "blocked_reason": "No accepted rows; route did not confirm filing_date/source_date/available_date fields",
            "evidence": "accepted_quarterly_fundamentals_rows.csv is header-only",
            "next_programmatic_source": "Probe MOPS material information / financial report announcement routes by company-quarter after data route is solved.",
        },
    ]

    coverage = []
    for year in range(2015, 2027):
        for quarter in ("Q1", "Q2", "Q3", "Q4"):
            coverage.append(
                {
                    "fiscal_year": year,
                    "quarter": quarter,
                    "market": "TWSE;TPEx",
                    "accepted_rows": 0,
                    "probe_status": "blocked_security_or_route_unresolved",
                    "coverage_status": "blocked",
                }
            )
    coverage_market = [
        {"market": "TWSE", "accepted_rows": 0, "symbol_count": 0, "coverage_status": "blocked"},
        {"market": "TPEx", "accepted_rows": 0, "symbol_count": 0, "coverage_status": "blocked"},
    ]

    write_csv(BASE / "source_probe_attempts.csv", attempts, PROBE_FIELDS)
    write_csv(BASE / "download_attempts.csv", attempts, PROBE_FIELDS)
    write_csv(
        BASE / "accepted_quarterly_fundamentals_rows.csv",
        [],
        [
            "ticker",
            "name",
            "market",
            "fiscal_year",
            "quarter",
            "metric_name",
            "metric_value",
            "source_date",
            "filing_date",
            "available_date",
            "source_url",
            "source_route",
            "source_type",
            "formal_exact",
            "pit_usable",
        ],
    )
    write_csv(
        BASE / "rejected_or_blocked_rows.csv",
        blocked_rows,
        ["dataset", "blocked_component", "blocked_reason", "evidence", "next_programmatic_source"],
    )
    write_csv(
        BASE / "coverage_by_year_quarter.csv",
        coverage,
        ["fiscal_year", "quarter", "market", "accepted_rows", "probe_status", "coverage_status"],
    )
    write_csv(BASE / "coverage_by_market.csv", coverage_market, ["market", "accepted_rows", "symbol_count", "coverage_status"])
    write_csv(
        BASE / "source_manifest.csv",
        source_manifest,
        ["source_id", "source_name", "source_url_or_pattern", "source_type", "markets", "coverage_probe", "release_date_available", "accepted_for_pit", "decision"],
    )
    (BASE / "source_manifest.json").write_text(json.dumps(source_manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    write_csv(
        BASE / "future_data_violation_audit.csv",
        [
            {
                "audit_item": "accepted_rows",
                "result": "pass",
                "future_data_violation_count": 0,
                "evidence": "No rows accepted because filing/source/available date could not be confirmed.",
            },
            {
                "audit_item": "current_snapshot_backfill",
                "result": "pass",
                "future_data_violation_count": 0,
                "evidence": "No current snapshot used to backfill historical fundamentals.",
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
        "status": "blocked_with_route_evidence",
        "quarterly_fundamentals_pit_ready": False,
        "quarterly_fundamentals_pit_partial_ready": False,
        "output_path": str(BASE.resolve()),
        "core_readiness_input": str(CORE_READINESS),
        "source_probe_attempts": len(attempts),
        "accepted_rows": 0,
        "future_data_violation_count": 0,
        "ready_for_core_rerun": True,
        "ready_for_strategy_replay": False,
        "formal_model_changed": False,
        "trade_decision_changed": False,
        "active_in_trade_decision": False,
        "remaining_blockers": [
            "MOPS ajax financial table routes returned security pages for direct scripted requests.",
            "Static/XBRL bulk route path was not resolved in bounded probes.",
            "No accepted rows because filing/source/available date fields were not confirmed.",
        ],
        "next_programmatic_sources": [
            "Browser/devtools exact request extraction for MOPS t163/t164 financial routes with valid session.",
            "Official XBRL bulk download route discovery via MOPS UI/static JS or TWSE open-data catalog.",
            "MOPS material information / financial report announcement crawler by company-quarter for filing_date.",
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
                    "source_probe_attempts.csv",
                    "download_attempts.csv",
                    "accepted_quarterly_fundamentals_rows.csv",
                    "rejected_or_blocked_rows.csv",
                    "coverage_by_year_quarter.csv",
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
            {"step": "mops_ajax_route_probe", "status": "completed_with_blocker", "evidence": "source_probe_attempts.csv"},
            {"step": "xbrl_static_route_probe", "status": "completed_with_blocker", "evidence": "source_probe_attempts.csv"},
            {"step": "readiness_package", "status": "completed", "evidence": "readiness_for_core.json"},
        ],
        ["step", "status", "evidence"],
    )
    write_csv(
        BASE / "failed.csv",
        [
            {"step": "accepted_quarterly_fundamentals_rows", "status": "blocked", "reason": "No route returned parseable data with filing/source/available date."}
        ],
        ["step", "status", "reason"],
    )
    (BASE / "current_step.txt").write_text("blocked_with_route_evidence", encoding="utf-8")
    (BASE / "final_summary_zh.md").write_text(
        """# Dynamic Pool1 quarterly fundamentals PIT source package

## 結論

狀態：`blocked_with_route_evidence`。

本棒完成 MOPS quarterly fundamentals route bounded probes，但沒有 accepted rows：

- source_probe_attempts：8
- accepted_quarterly_fundamentals_rows：0
- `quarterly_fundamentals_pit_ready=false`
- `quarterly_fundamentals_pit_partial_ready=false`
- `future_data_violation_count=0`

## 主要 blocker

MOPS `ajax_t163sb04` / `ajax_t163sb05` / `ajax_t163sb06` / `ajax_t164sb04` 直接 scripted request 回 security page：`FOR SECURITY REASONS, THIS PAGE CAN NOT BE ACCESSED`。猜測 XBRL/static download path 回 404 或同樣 security page。

因為沒有取得可解析資料表，也沒有確認 filing/source/available date 欄位，本棒不接受任何 quarterly fundamentals row。

## 下一步

1. 用 browser/devtools exact request extraction 取得 MOPS t163/t164 成功查詢時的 session/header/body/hidden fields。
2. 反查官方 XBRL bulk download 或 TWSE open-data catalog 的正確可下載路徑。
3. 若財報資料 route 解開後，再用 MOPS material information / financial report announcement crawler 補 filing_date。

## 邊界

- `ready_for_core_rerun=true`，讓 Core 記錄 blocker evidence。
- `ready_for_strategy_replay=false`
- `formal_model_changed=false`
- `trade_decision_changed=false`
- `active_in_trade_decision=false`
""",
        encoding="utf-8",
    )
    with (BASE / "run_log.csv").open("a", encoding="utf-8", newline="") as handle:
        csv.writer(handle).writerow([datetime.now(timezone.utc).isoformat(), "completed", json.dumps(readiness, ensure_ascii=False)])
    return readiness


if __name__ == "__main__":
    BASE.mkdir(parents=True, exist_ok=True)
    print(json.dumps(build_package(), ensure_ascii=False, indent=2))
