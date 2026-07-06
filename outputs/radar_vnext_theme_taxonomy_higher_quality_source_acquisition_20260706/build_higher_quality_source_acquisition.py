from __future__ import annotations

import csv
import json
from collections import Counter
from datetime import date
from pathlib import Path


OUT = Path(__file__).resolve().parent
ROOT = OUT.parents[1]
RADAR_PACKAGE = ROOT / "outputs" / "radar_vnext_theme_taxonomy_source_package_20260706"
CORE_INGEST = Path(r"C:\Users\zergv\Documents\Codex\2026-05-30\ep05-chat-ai-stock-backtest-lab\outputs\vnext_theme_taxonomy_source_ingest_readiness_20260706")
RESEARCH_JUDGMENT = Path(r"C:\Users\zergv\Documents\Codex\2026-07-06\backtest-lab-vnext-research-dynamic-candidate\outputs\vnext_ai_allocation_proxy_limited_rerun_research_judgment_20260706.md")


FLAGS = {
    "formal_model_changed": False,
    "trade_decision_changed": False,
    "active_in_trade_decision": False,
    "report_changed": False,
    "portfolio_replay_executed": False,
    "ready_for_strategy_replay": False,
}


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def write_csv(path: Path, rows: list[dict[str, object]], fieldnames: list[str]) -> None:
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "current_step.txt").write_text("building_higher_quality_source_acquisition_package\n", encoding="utf-8")

    ai_evidence = read_csv(RADAR_PACKAGE / "ai_subtheme_classification_evidence_ledger.csv")
    source_attempts = read_csv(RADAR_PACKAGE / "source_attempt_evidence.csv")
    non_ai = read_csv(RADAR_PACKAGE / "non_ai_theme_taxonomy_candidate_ledger.csv")
    components = read_csv(RADAR_PACKAGE / "theme_strength_score_component_readiness_ledger.csv")
    core_readiness = json.loads((CORE_INGEST / "readiness_for_ai_allocation_rerun.json").read_text(encoding="utf-8"))

    source_route_rows = [
        {
            "workstream": "exact_or_human_reviewed_dated_ai_membership",
            "route_id": "mops_dated_company_document_human_review_contract",
            "route_or_source": "MOPS annual reports / official disclosures with captured source_date and effective_date",
            "current_status": "higher_quality_diagnostic_ready_human_review_required",
            "source_quality": "higher-quality diagnostic",
            "accepted_for_diagnostic": True,
            "accepted_for_formal": False,
            "exact_available": False,
            "human_review_required": True,
            "attempt_evidence": "44 AI subtheme evidence rows; 39 higher-quality dated AI membership rows ingested by Core",
            "blocked_reason": "No approved human-review acceptance policy and no formal taxonomy policy.",
            "next_action": "Core/Research define reviewer columns and acceptance threshold; then run bounded review on current 44 evidence rows.",
        },
        {
            "workstream": "non_ai_market_theme_taxonomy",
            "route_id": "twse_official_industry_proxy_comparator",
            "route_or_source": "TWSE MI_INDEX official industry route",
            "current_status": "proxy_upgraded_not_formal",
            "source_quality": "proxy",
            "accepted_for_diagnostic": True,
            "accepted_for_formal": False,
            "exact_available": False,
            "human_review_required": True,
            "attempt_evidence": "5 non-AI taxonomy candidate rows; prior TWSE industry route probes fetched dated rows",
            "blocked_reason": "Official industry is not equivalent to market theme taxonomy and excludes TPEx all-stock coverage.",
            "next_action": "If Strategy Center accepts temporary comparator, Core can map official industries to comparator buckets for diagnostic only.",
        },
        {
            "workstream": "tpex_all_stock_historical_sector_membership",
            "route_id": "tpex_sector_membership_route_or_alternative",
            "route_or_source": "TPEx statistics/industry-chain routes plus documented TWSE-only alternative",
            "current_status": "blocked_with_documented_alternative",
            "source_quality": "blocked",
            "accepted_for_diagnostic": False,
            "accepted_for_formal": False,
            "exact_available": False,
            "human_review_required": False,
            "attempt_evidence": "Prior TPEx route probes did not yield all-stock dated sector membership rows.",
            "blocked_reason": "TPEx route remains locked; current TPEx daily quote/index routes lack all-stock sector membership.",
            "next_action": "Use TWSE-only official-industry comparator as documented alternative, or acquire TPEx official historical constituent/member file manually.",
        },
        {
            "workstream": "exact_rolling_new_high_count",
            "route_id": "price_panel_rolling_new_high_contract",
            "route_or_source": "Accepted daily OHLC close panel + accepted membership universe + rolling window spec",
            "current_status": "source_ready_contract_not_materialized",
            "source_quality": "blocked",
            "accepted_for_diagnostic": False,
            "accepted_for_formal": False,
            "exact_available": False,
            "human_review_required": False,
            "attempt_evidence": "Core currently uses drawdown_60d >= -2% proxy; Radar has partial price caches but no accepted all-theme membership universe.",
            "blocked_reason": "Needs accepted membership universe and explicit rolling high window/calendar policy.",
            "next_action": "Materialize component after Core accepts membership universe and defines window, e.g. 60D/120D close >= rolling max.",
        },
    ]

    review_contract_rows = []
    for row in ai_evidence:
        review_contract_rows.append(
            {
                "ticker": row["ticker"],
                "company_name": row["company_name"],
                "candidate_ai_subtheme": row["ai_subtheme"],
                "theme_label": row["theme_label"],
                "source": row["source"],
                "source_doc_type": row["source_doc_type"],
                "source_date": row["source_date"],
                "effective_date": row["effective_date"],
                "evidence_category": row["evidence_category"],
                "keyword_or_topic": row["keyword_or_topic"],
                "current_confidence_level": row["confidence_level"],
                "review_required": True,
                "review_decision_allowed_values": "accept_ai_member;reject_ai_member;accept_non_ai;needs_more_source",
                "reviewed_ai_subtheme_allowed_values": "ai_server_hardware;cooling_thermal;pcb_ccl;semiconductor;semiconductor_materials;ai_supply_chain;other;not_ai",
                "accepted_for_formal_before_review": False,
                "accepted_for_higher_quality_rerun_before_review": False,
                "future_data_violation_count": 0,
            }
        )

    tpex_rows = []
    for row in source_attempts:
        if "tpex" in (row.get("source_id", "") + row.get("source", "") + row.get("route_or_path", "")).lower():
            tpex_rows.append(
                {
                    "route_id": row.get("source_id", ""),
                    "source": row.get("source", ""),
                    "route_or_path": row.get("route_or_path", ""),
                    "decision": row.get("decision", ""),
                    "accepted_for_diagnostic": row.get("accepted_for_diagnostic", ""),
                    "accepted_for_formal": row.get("accepted_for_formal", ""),
                    "blocked_reason_or_notes": row.get("notes", ""),
                    "documented_alternative": "TWSE official industry proxy is available only for TWSE-listed diagnostic comparator; not all-stock TPEx exact membership.",
                }
            )

    new_high_rows = [
        {
            "component": "rolling_new_high_count",
            "required_input": "daily close or adjusted close price panel",
            "required_coverage": "same candidate universe and date range as AI allocation diagnostic",
            "required_membership": "accepted dated AI/non-AI membership universe",
            "calculation_contract": "count ticker where close(date) >= max(close over trailing_window ending date)",
            "calendar_policy_needed": "trading-day window, e.g. 60D or 120D; must be fixed by Core/Research",
            "current_proxy": "drawdown_60d >= -2%",
            "source_quality": "blocked",
            "ready_to_materialize": False,
            "blocked_reason": "accepted membership universe and exact rolling window policy are missing",
            "future_data_violation_count": 0,
        },
        {
            "component": "theme_new_high_share",
            "required_input": "rolling_new_high_count + theme member count by date",
            "required_coverage": "per theme per trading date",
            "required_membership": "accepted dated theme taxonomy",
            "calculation_contract": "rolling_new_high_count / eligible_theme_member_count",
            "calendar_policy_needed": "same as rolling_new_high_count",
            "current_proxy": "none; derived from current drawdown proxy in Core",
            "source_quality": "blocked",
            "ready_to_materialize": False,
            "blocked_reason": "depends on rolling_new_high_count and accepted theme membership",
            "future_data_violation_count": 0,
        },
    ]

    quality_rows = []
    quality_rows.extend(
        [
            {
                "field": "dated_ai_membership",
                "source_quality": "higher-quality diagnostic",
                "rows_or_routes": len(review_contract_rows),
                "accepted_for_diagnostic": True,
                "accepted_for_formal": False,
                "ready_for_higher_quality_ai_allocation_rerun": False,
                "blocked_reason": "human review contract exists, but review not executed/approved",
            },
            {
                "field": "non_ai_market_theme_taxonomy",
                "source_quality": "proxy",
                "rows_or_routes": len(non_ai),
                "accepted_for_diagnostic": True,
                "accepted_for_formal": False,
                "ready_for_higher_quality_ai_allocation_rerun": False,
                "blocked_reason": "TWSE industry proxy is not market theme taxonomy; TPEx unavailable",
            },
            {
                "field": "tpex_all_stock_sector_membership",
                "source_quality": "blocked",
                "rows_or_routes": len(tpex_rows),
                "accepted_for_diagnostic": False,
                "accepted_for_formal": False,
                "ready_for_higher_quality_ai_allocation_rerun": False,
                "blocked_reason": "route locked; no accepted all-stock dated membership rows",
            },
            {
                "field": "exact_rolling_new_high_count",
                "source_quality": "blocked",
                "rows_or_routes": len(new_high_rows),
                "accepted_for_diagnostic": False,
                "accepted_for_formal": False,
                "ready_for_higher_quality_ai_allocation_rerun": False,
                "blocked_reason": "contract documented, component not materialized",
            },
        ]
    )
    for row in components:
        quality_rows.append(
            {
                "field": row["component"],
                "source_quality": row["source_quality"],
                "rows_or_routes": "",
                "accepted_for_diagnostic": row["accepted_for_diagnostic"],
                "accepted_for_formal": row["accepted_for_formal"],
                "ready_for_higher_quality_ai_allocation_rerun": False,
                "blocked_reason": row["blocked_reason"],
            }
        )

    write_csv(OUT / "source_route_acquisition_ledger.csv", source_route_rows, list(source_route_rows[0].keys()))
    write_csv(OUT / "human_review_ai_membership_contract.csv", review_contract_rows, list(review_contract_rows[0].keys()))
    write_csv(OUT / "tpex_sector_route_or_alternative_evidence.csv", tpex_rows, list(tpex_rows[0].keys()))
    write_csv(OUT / "rolling_new_high_materialization_contract.csv", new_high_rows, list(new_high_rows[0].keys()))
    write_csv(OUT / "source_quality_upgrade_ledger.csv", quality_rows, list(quality_rows[0].keys()))

    source_quality_counts = Counter(row["source_quality"] for row in quality_rows)
    readiness = {
        "date": date.today().isoformat(),
        "task_id": "TASK-RADAR-DATA-VNEXT-THEME-TAXONOMY-HIGHER-QUALITY-SOURCE-ACQUISITION-001",
        "owner": "AI_stock_rotation_radar / Radar-Data",
        "status": "blocked_higher_quality_source_contract_ready",
        "diagnostic_only": True,
        "ready_for_proxy_limited_ai_allocation_rerun": True,
        "ready_for_higher_quality_ai_allocation_rerun": False,
        "ready_for_strategy_replay": False,
        "ready_for_formal": False,
        "future_data_violation_count": 0,
        "exact_ai_membership_rows": 0,
        "human_review_contract_rows": len(review_contract_rows),
        "higher_quality_dated_ai_membership_rows_from_core": core_readiness.get("higher_quality_dated_ai_membership_rows"),
        "non_ai_taxonomy_candidate_rows": len(non_ai),
        "tpex_attempt_rows": len(tpex_rows),
        "rolling_new_high_contract_rows": len(new_high_rows),
        "source_quality_counts": dict(source_quality_counts),
        "blocking_summary": [
            "Human review contract exists but review is not executed/approved.",
            "Non-AI comparator remains official-industry proxy, not formal market theme taxonomy.",
            "TPEx all-stock historical sector membership remains locked; only documented alternative is TWSE-only diagnostic proxy.",
            "Exact rolling new-high count has a materialization contract but no accepted membership universe/window policy.",
        ],
        "next_owner": "Core/Data or vNext Research for taxonomy policy and human-review decision",
        "recommended_next_step": "Do not rerun Experiments until Core/Research either executes human review and accepts TWSE proxy comparator, or provides an exact TPEx/non-AI taxonomy source.",
        **FLAGS,
    }
    (OUT / "readiness_for_core_research.json").write_text(json.dumps(readiness, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    manifest = {
        "task_id": readiness["task_id"],
        "created_at": date.today().isoformat(),
        "inputs": {
            "research_judgment": str(RESEARCH_JUDGMENT),
            "core_ingest": str(CORE_INGEST),
            "radar_source_package": str(RADAR_PACKAGE),
        },
        "outputs": [
            "source_route_acquisition_ledger.csv",
            "human_review_ai_membership_contract.csv",
            "tpex_sector_route_or_alternative_evidence.csv",
            "rolling_new_high_materialization_contract.csv",
            "source_quality_upgrade_ledger.csv",
            "readiness_for_core_research.json",
            "final_summary_zh.md",
            "current_step.txt",
            "completed.csv",
        ],
        "flags": FLAGS,
    }
    (OUT / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    summary = f"""# vNext Theme Taxonomy Higher-Quality Source Acquisition

Status: blocked_higher_quality_source_contract_ready

結論：
- 沒有把 proxy 包裝成 exact，也沒有升 formal taxonomy。
- 已產出 human-reviewed dated AI membership contract：{len(review_contract_rows)} rows。
- 已整理 non-AI theme taxonomy beyond `non_ai_unclassified_proxy` 的可用路線：TWSE official industry proxy 可作 diagnostic comparator，但不是 formal market theme taxonomy。
- TPEx all-stock historical sector membership route 仍 blocked；本包提供 documented alternative，不宣稱 unlock。
- exact rolling new-high count 已產出 source-ready materialization contract，但尚未 materialized。

Readiness:
- ready_for_proxy_limited_ai_allocation_rerun=true
- ready_for_higher_quality_ai_allocation_rerun=false
- ready_for_strategy_replay=false
- ready_for_formal=false
- future_data_violation_count=0

Flags:
- formal_model_changed=false
- trade_decision_changed=false
- active_in_trade_decision=false
- report_changed=false
- portfolio_replay_executed=false

下一棒：
- Core / vNext Research 需決定是否執行 human review、是否接受 TWSE official industry proxy 作 temporary non-AI comparator。
- Experiments 應繼續暫停；除非 higher-quality readiness 變 true，或 Strategy Center 明確批准再次 proxy-limited diagnostic。
"""
    (OUT / "final_summary_zh.md").write_text(summary, encoding="utf-8")
    write_csv(OUT / "completed.csv", [{"status": "completed", "date": date.today().isoformat(), "output": str(OUT)}], ["status", "date", "output"])
    (OUT / "current_step.txt").write_text("completed\n", encoding="utf-8")


if __name__ == "__main__":
    main()
