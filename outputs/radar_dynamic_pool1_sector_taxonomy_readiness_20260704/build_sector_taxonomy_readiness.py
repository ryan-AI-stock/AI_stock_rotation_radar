from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path


OUTPUT_DIR = Path(__file__).resolve().parent
REPO_ROOT = OUTPUT_DIR.parents[1]
PREV_OUTPUT = REPO_ROOT / "outputs" / "radar_dynamic_pool1_sector_mainline_pit_full_sweep_and_tpex_reverse_20260703"
RESEARCH_JUDGMENT = Path(
    r"C:\Users\zergv\Documents\Codex\2026-06-17\repo-ai-stock-backtest-lab-repo-2\outputs"
    r"\research_dynamic_pool1_twse_sector_proxy_shadow_diagnostic_judgment_20260704.md"
)

ACCEPTED_TPEX_COLUMNS = [
    "ticker",
    "name",
    "market",
    "sector",
    "sector_code",
    "source_date",
    "effective_date",
    "as_of_date",
    "source_url",
    "source_type",
    "accepted_for_diagnostic",
    "accepted_for_formal",
    "notes",
]

ACCEPTED_THEME_COLUMNS = [
    "ticker",
    "name",
    "taxonomy_level",
    "taxonomy_label",
    "evidence_date",
    "source_date",
    "effective_date",
    "as_of_date",
    "source_url",
    "source_type",
    "accepted_for_diagnostic",
    "accepted_for_formal",
    "notes",
]


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def write_csv(path: Path, rows: list[dict], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def read_csv(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def append_log(status: str, detail: str) -> None:
    path = OUTPUT_DIR / "run_log.csv"
    is_new = not path.exists()
    with path.open("a", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=["timestamp_utc", "status", "detail"])
        if is_new:
            writer.writeheader()
        writer.writerow({"timestamp_utc": now_iso(), "status": status, "detail": detail})


def local_file_inventory() -> list[dict]:
    candidates = [
        ("sector_map", REPO_ROOT / "data" / "sector_map.csv"),
        ("sector_map_generated", REPO_ROOT / "data" / "sector_map.generated.csv"),
        ("theme_map", REPO_ROOT / "data" / "theme_map.csv"),
        ("theme_history_generated", REPO_ROOT / "data" / "theme_history.generated.csv"),
        ("theme_universe", REPO_ROOT / "data" / "theme_universe.csv"),
        ("industry_sector_rules", REPO_ROOT / "data" / "industry_sector_rules.csv"),
    ]
    rows = []
    for source_id, path in candidates:
        rows.append(
            {
                "source_id": source_id,
                "source_name": path.name,
                "source_path_or_url": str(path),
                "taxonomy_scope": "sector/theme/mainline_candidate",
                "source_type": "repo_current_or_generated_static_map",
                "source_date_available": "false",
                "effective_date_available": "false",
                "as_of_date_available": "false",
                "accepted_for_diagnostic": "false",
                "accepted_for_formal": "false",
                "decision": "blocked_current_static_or_generated_map_not_pit",
                "notes": "Inventory only. Must not be used as historical PIT evidence.",
            }
        )
    return rows


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUTPUT_DIR / "current_step.txt").write_text("building_sector_taxonomy_readiness_package\n", encoding="utf-8")
    append_log("started", "sector taxonomy readiness package")

    previous_tpex_attempts = read_csv(PREV_OUTPUT / "tpex_sector_route_probe_attempts.csv")
    tpex_attempt_rows = []
    for row in previous_tpex_attempts:
        tpex_attempt_rows.append(
            {
                "candidate_id": row.get("candidate_id", ""),
                "source_url": row.get("source_url", ""),
                "method": row.get("method", ""),
                "status": row.get("status", ""),
                "http_code": row.get("http_code", ""),
                "content_type": row.get("content_type", ""),
                "bytes": row.get("bytes", ""),
                "accepted_membership_rows": 0,
                "decision": "route_evidence_only_not_accepted",
                "blocked_reason": "No all-stock date-aware historical sector membership table was identified in this response.",
                "notes": row.get("notes", ""),
            }
        )
    write_csv(
        OUTPUT_DIR / "tpex_sector_route_attempts.csv",
        tpex_attempt_rows,
        [
            "candidate_id",
            "source_url",
            "method",
            "status",
            "http_code",
            "content_type",
            "bytes",
            "accepted_membership_rows",
            "decision",
            "blocked_reason",
            "notes",
        ],
    )

    write_csv(OUTPUT_DIR / "accepted_tpex_sector_rows.csv", [], ACCEPTED_TPEX_COLUMNS)
    write_csv(OUTPUT_DIR / "accepted_theme_taxonomy_rows.csv", [], ACCEPTED_THEME_COLUMNS)

    source_inventory = [
        {
            "source_id": "twse_mi_index_by_industry",
            "source_name": "TWSE MI_INDEX by official industry",
            "source_path_or_url": "https://www.twse.com.tw/rwd/zh/afterTrading/MI_INDEX?date={yyyymmdd}&type={industry_code}&response=json",
            "taxonomy_scope": "official_industry_twse_only",
            "source_type": "official_date_aware_daily_route",
            "source_date_available": "true",
            "effective_date_available": "as_of_trading_date",
            "as_of_date_available": "true",
            "accepted_for_diagnostic": "true",
            "accepted_for_formal": "false",
            "decision": "diagnostic_only_twse_official_industry_proxy",
            "notes": "Useful as TWSE-only official industry proxy; not AI/mainline/theme taxonomy and not TPEx.",
        },
        {
            "source_id": "tpex_statistics_idx",
            "source_name": "TPEx statistics idx route",
            "source_path_or_url": "https://www.tpex.org.tw/www/zh-tw/statistics/idx",
            "taxonomy_scope": "tpex_sector_route_candidate",
            "source_type": "official_route_probe",
            "source_date_available": "partial_response_date_parameter",
            "effective_date_available": "not_proven",
            "as_of_date_available": "not_proven_for_all_stock_membership",
            "accepted_for_diagnostic": "false",
            "accepted_for_formal": "false",
            "decision": "blocked_index_statistics_not_all_stock_sector_membership",
            "notes": "Fetched successfully in prior bounded probe but did not yield accepted membership rows.",
        },
        {
            "source_id": "tpex_ic_platform",
            "source_name": "TPEx Industry Chain Information Platform",
            "source_path_or_url": "https://ic.tpex.org.tw/",
            "taxonomy_scope": "tpex_industry_chain_current_platform_candidate",
            "source_type": "official_or_semi_official_platform_probe",
            "source_date_available": "not_proven",
            "effective_date_available": "not_proven",
            "as_of_date_available": "not_proven",
            "accepted_for_diagnostic": "false",
            "accepted_for_formal": "false",
            "decision": "blocked_until_api_static_reverse_finds_dated_membership",
            "notes": "Landing page contains industry-chain content but no accepted date-aware historical membership in current evidence.",
        },
        {
            "source_id": "mops_filings_theme_evidence_ledger",
            "source_name": "MOPS annual reports, prospectuses, investor presentations, material information",
            "source_path_or_url": "https://mops.twse.com.tw/",
            "taxonomy_scope": "ai_mainline_theme_dated_evidence_candidate",
            "source_type": "official_document_evidence_candidate",
            "source_date_available": "true_if_document_date_or_publish_date_is_captured",
            "effective_date_available": "manual_or_parser_dependent",
            "as_of_date_available": "true_if_source_date_is_captured",
            "accepted_for_diagnostic": "false",
            "accepted_for_formal": "false",
            "decision": "blocked_pending_dated_evidence_ledger",
            "notes": "Next programmatic route: build document locator/parser for dated company evidence; do not infer AI theme from current labels.",
        },
    ]
    source_inventory.extend(local_file_inventory())
    write_csv(
        OUTPUT_DIR / "theme_taxonomy_source_inventory.csv",
        source_inventory,
        [
            "source_id",
            "source_name",
            "source_path_or_url",
            "taxonomy_scope",
            "source_type",
            "source_date_available",
            "effective_date_available",
            "as_of_date_available",
            "accepted_for_diagnostic",
            "accepted_for_formal",
            "decision",
            "notes",
        ],
    )
    write_csv(OUTPUT_DIR / "taxonomy_source_manifest.csv", source_inventory, list(source_inventory[0].keys()))

    blocked_rows = [
        {
            "source_id": "tpex_historical_sector_membership",
            "dataset": "tpex_sector_membership",
            "status": "blocked_with_route_evidence",
            "blocked_reason": "Prior official route probes fetched responses, but no all-stock date-aware historical TPEx sector membership rows were accepted.",
            "next_programmatic_source": "Reverse TPEx IC platform JS/API and statistics idx response schema; identify all-stock membership endpoint with date/as-of parameter.",
            "accepted_for_strategy_replay": "false",
        },
        {
            "source_id": "ai_mainline_theme_taxonomy",
            "dataset": "ai_mainline_theme_taxonomy",
            "status": "blocked_no_date_aware_evidence_ledger",
            "blocked_reason": "Current/static/generated maps lack source_date/effective_date/as_of_date and cannot be backfilled into 2015+ PIT taxonomy.",
            "next_programmatic_source": "Build dated MOPS document evidence ledger from annual reports, prospectuses, investor presentations, material information, and official filings.",
            "accepted_for_strategy_replay": "false",
        },
        {
            "source_id": "official_industry_to_market_mainline_mapping",
            "dataset": "taxonomy_boundary",
            "status": "blocked_policy_not_equivalent",
            "blocked_reason": "Official industry categories do not equal AI/mainline/theme taxonomy; any mapping would be Research policy, not source data.",
            "next_programmatic_source": "Research policy judgment after Data provides dated evidence rows; keep TWSE official industry as diagnostic-only proxy.",
            "accepted_for_strategy_replay": "false",
        },
    ]
    write_csv(
        OUTPUT_DIR / "blocked_source_rows.csv",
        blocked_rows,
        ["source_id", "dataset", "status", "blocked_reason", "next_programmatic_source", "accepted_for_strategy_replay"],
    )
    write_csv(OUTPUT_DIR / "blocked_sources.csv", blocked_rows, list(blocked_rows[0].keys()))

    audit = [
        {
            "check": "current_static_maps_not_accepted",
            "status": "pass",
            "future_data_violation_count": 0,
            "notes": "Repo current/static/generated sector and theme maps are inventoried only and excluded from accepted historical rows.",
        },
        {
            "check": "accepted_rows_require_date_awareness",
            "status": "pass",
            "future_data_violation_count": 0,
            "notes": "No TPEx or theme taxonomy rows were accepted because date-aware evidence is not established.",
        },
    ]
    write_csv(OUTPUT_DIR / "future_data_violation_audit.csv", audit, ["check", "status", "future_data_violation_count", "notes"])

    tpex_readiness = {
        "task_id": "TASK-RADAR-DATA-DYNAMIC-POOL1-SECTOR-TAXONOMY-READINESS-20260704",
        "dataset": "tpex_sector_membership",
        "status": "blocked_with_route_evidence",
        "tpex_sector_membership_route_unlocked": False,
        "accepted_tpex_sector_rows": 0,
        "accepted_for_diagnostic": False,
        "accepted_for_formal": False,
        "proxy_policy": "TPEx current/platform routes may be retained only as route evidence until a dated all-stock membership endpoint or source document is identified. Do not backfill current membership into historical periods.",
        "next_programmatic_source": "Reverse TPEx IC platform JS/API and statistics idx schema; search official dated membership/download endpoints.",
        "future_data_violation_count": 0,
    }
    theme_readiness = {
        "task_id": "TASK-RADAR-DATA-DYNAMIC-POOL1-SECTOR-TAXONOMY-READINESS-20260704",
        "dataset": "ai_mainline_theme_taxonomy",
        "status": "blocked_pending_dated_evidence_ledger",
        "ai_mainline_theme_taxonomy_ready": False,
        "accepted_theme_taxonomy_rows": 0,
        "accepted_for_diagnostic": False,
        "accepted_for_formal": False,
        "official_industry_mapping_boundary": "TWSE official industry can be diagnostic sector proxy only; it is not AI/mainline/theme taxonomy.",
        "next_programmatic_source": "Dated MOPS document evidence ledger: annual reports, prospectuses, investor presentations, material information, official filings.",
        "future_data_violation_count": 0,
    }
    (OUTPUT_DIR / "tpex_sector_membership_readiness.json").write_text(json.dumps(tpex_readiness, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (OUTPUT_DIR / "ai_mainline_theme_taxonomy_readiness.json").write_text(json.dumps(theme_readiness, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    readiness = {
        "task_id": "TASK-RADAR-DATA-DYNAMIC-POOL1-SECTOR-TAXONOMY-READINESS-20260704",
        "status": "completed_readiness_blocked_with_evidence",
        "tpex_sector_membership_ready": False,
        "tpex_sector_membership_route_unlocked": False,
        "accepted_tpex_sector_rows": 0,
        "ai_mainline_theme_taxonomy_ready": False,
        "accepted_theme_taxonomy_rows": 0,
        "official_industry_to_mainline_mapping_ready": False,
        "twse_official_industry_diagnostic_only": True,
        "ready_for_core_rerun": True,
        "ready_for_strategy_replay": False,
        "future_data_violation_count": 0,
        "formal_model_changed": False,
        "trade_decision_changed": False,
        "active_in_trade_decision": False,
        "research_judgment_source": str(RESEARCH_JUDGMENT),
        "previous_sector_output": str(PREV_OUTPUT),
        "remaining_blockers": [
            "TPEx all-stock historical sector membership route remains locked.",
            "AI/mainline/theme taxonomy lacks date-aware evidence ledger.",
            "Official industry categories are not equivalent to market mainline/theme taxonomy.",
        ],
    }
    (OUTPUT_DIR / "readiness_for_core.json").write_text(json.dumps(readiness, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (OUTPUT_DIR / "manifest.json").write_text(json.dumps(readiness, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    summary = """# Dynamic Pool1 sector taxonomy readiness 20260704

## 結論
- 狀態：`completed_readiness_blocked_with_evidence`
- TPEx accepted sector rows：0
- AI/mainline/theme accepted taxonomy rows：0
- `future_data_violation_count=0`
- `ready_for_core_rerun=true`
- `ready_for_strategy_replay=false`

## 判斷
- TPEx：已有官方 route probe evidence，但尚未找到可接受的 all-stock date-aware historical sector membership endpoint，因此不能回推歷史。
- AI/mainline/theme：repo 內 current/static/generated maps 只能列 inventory / blocked，不能作 2015+ PIT evidence。
- TWSE official industry：可保留為 TWSE-only diagnostic sector proxy，但不能轉寫成 AI 主線、market mainline 或 theme taxonomy。

## 下一個最小資料缺口
1. Reverse TPEx IC platform JS/API 與 `statistics/idx` schema，找 date-aware all-stock membership route。
2. 建立 MOPS dated document evidence ledger，從年報、公開說明書、法說/簡報、重大訊息中抽 AI/mainline/theme evidence。
3. official industry -> market mainline/theme 若要建立，只能由 Research 另做 policy judgment，不能由 Data 直接映射。
"""
    (OUTPUT_DIR / "final_summary_zh.md").write_text(summary, encoding="utf-8")
    write_csv(OUTPUT_DIR / "completed.csv", [{"task_id": readiness["task_id"], "status": readiness["status"]}], ["task_id", "status"])
    write_csv(OUTPUT_DIR / "failed.csv", [], ["task_id", "status", "reason"])
    (OUTPUT_DIR / "current_step.txt").write_text("completed_readiness_blocked_with_evidence\n", encoding="utf-8")
    append_log("completed", "accepted_tpex_rows=0 accepted_theme_rows=0 ready_for_core_rerun=true")
    print(json.dumps(readiness, ensure_ascii=False))


if __name__ == "__main__":
    main()
