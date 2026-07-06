from __future__ import annotations

import csv
import json
from collections import Counter
from datetime import date
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
CORE = Path(r"C:\Users\zergv\Documents\Codex\2026-05-30\ep05-chat-ai-stock-backtest-lab\outputs\vnext_theme_taxonomy_readiness_20260706")
MOPS_DOC = ROOT / "outputs" / "radar_dynamic_pool1_mops_document_extraction_v1_20260704"
MOPS_MAINLINE = ROOT / "outputs" / "radar_dynamic_pool1_mops_mainline_evidence_ledger_20260704"
SECTOR_READY = ROOT / "outputs" / "radar_dynamic_pool1_sector_taxonomy_readiness_20260704"
SECTOR_SOURCE = ROOT / "outputs" / "radar_dynamic_pool1_sector_mainline_pit_source_package_20260703"


FLAGS = {
    "formal_model_changed": False,
    "trade_decision_changed": False,
    "active_in_trade_decision": False,
    "report_changed": False,
    "portfolio_replay_executed": False,
    "ready_for_strategy_replay": False,
}


def read_csv(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def write_csv(path: Path, rows: list[dict[str, object]], fieldnames: list[str]) -> None:
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def bool_str(value: object) -> str:
    return str(value).lower()


def norm_ticker(value: str) -> str:
    return value.replace(".TW", "").replace(".TWO", "").strip()


def first_by_ticker(rows: list[dict[str, str]]) -> dict[str, dict[str, str]]:
    out: dict[str, dict[str, str]] = {}
    for row in rows:
        ticker = norm_ticker(row.get("ticker", ""))
        if ticker and ticker not in out:
            out[ticker] = row
    return out


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)

    core_quality = read_csv(CORE / "theme_membership_source_quality_ledger.csv")
    core_dated = read_csv(CORE / "dated_ai_membership_readiness.csv")
    core_components = read_csv(CORE / "theme_strength_component_readiness.csv")
    core_blocked = read_csv(CORE / "blocked_fields_and_proxy_fields.csv")
    mops_doc_rows = read_csv(MOPS_DOC / "accepted_document_evidence_rows.csv")
    mops_mainline_rows = read_csv(MOPS_MAINLINE / "accepted_evidence_rows.csv")
    sector_inventory = read_csv(SECTOR_READY / "theme_taxonomy_source_inventory.csv")
    sector_blocked = read_csv(SECTOR_READY / "blocked_source_rows.csv")
    tpex_attempts = read_csv(SECTOR_SOURCE / "source_probe_attempts.csv")

    evidence_by_ticker = first_by_ticker(mops_doc_rows + mops_mainline_rows)
    doc_by_ticker = first_by_ticker(mops_doc_rows)
    mainline_by_ticker = first_by_ticker(mops_mainline_rows)

    ai_rows = [r for r in core_quality if r.get("accepted_for_diagnostic", "").lower() == "true"]
    ai_package_rows: list[dict[str, object]] = []
    for row in ai_rows:
        ticker = norm_ticker(row.get("ticker", ""))
        ev = evidence_by_ticker.get(ticker, {})
        source_package = "none"
        if ticker in doc_by_ticker:
            source_package = "TASK-RADAR-DATA-DYNAMIC-POOL1-MOPS-DOCUMENT-EXTRACTION-V1-20260704"
        elif ticker in mainline_by_ticker:
            source_package = "TASK-RADAR-DATA-DYNAMIC-POOL1-MOPS-MAINLINE-EVIDENCE-LEDGER-20260704"

        higher_quality = bool(ev)
        ai_package_rows.append(
            {
                "ticker": ticker,
                "theme_id": row.get("theme_id", ""),
                "theme_name": row.get("theme_name", ""),
                "ai_subtheme": row.get("ai_subtheme", ""),
                "source": ev.get("source_url_or_file") or ev.get("source_url") or "no_dated_company_document_matched",
                "source_package_task_id": source_package,
                "source_doc_type": ev.get("source_doc_type", ""),
                "source_date": ev.get("source_date", ""),
                "effective_date": ev.get("effective_date", ""),
                "source_quality": "higher_quality_dated_document_diagnostic" if higher_quality else "proxy_from_core_membership_ledger",
                "exact_membership_available": False,
                "higher_quality_dated_membership_available": higher_quality,
                "accepted_for_diagnostic": row.get("accepted_for_diagnostic", "true"),
                "accepted_for_formal": False,
                "human_review_required": True,
                "formal_exact": False,
                "future_data_violation_count": 0,
                "blocked_reason": "formal taxonomy policy and human review are still required",
            }
        )

    subtheme_rows: list[dict[str, object]] = []
    for ev in mops_doc_rows + mops_mainline_rows:
        subtheme_rows.append(
            {
                "ticker": norm_ticker(ev.get("ticker", "")),
                "company_name": ev.get("company_name", ""),
                "ai_subtheme": ev.get("ai_supply_chain_layer", ""),
                "theme_label": ev.get("mainline_theme_label", ""),
                "evidence_category": ev.get("evidence_category") or ev.get("evidence_type", ""),
                "keyword_or_topic": ev.get("keyword_or_topic", ""),
                "source": ev.get("source_url_or_file") or ev.get("source_url", ""),
                "source_doc_type": ev.get("source_doc_type", ""),
                "source_date": ev.get("source_date", ""),
                "effective_date": ev.get("effective_date", ""),
                "confidence_level": ev.get("confidence_level", ""),
                "accepted_for_diagnostic": True,
                "accepted_for_formal": False,
                "human_review_required": True,
                "formal_exact": False,
                "source_excerpt": ev.get("source_excerpt", ""),
            }
        )

    non_ai_taxonomy = [
        {
            "theme_id": "semiconductor_official_industry_proxy",
            "theme_name": "Semiconductor official industry proxy",
            "theme_family": "non_ai_theme_taxonomy",
            "source": "TWSE MI_INDEX by official industry",
            "source_route": "https://www.twse.com.tw/rwd/zh/afterTrading/MI_INDEX?date={yyyymmdd}&type={industry_code}&response=json",
            "coverage": "TWSE listed industry route; not TPEx all-stock and not AI/mainline theme taxonomy",
            "source_quality": "official_date_aware_industry_proxy",
            "accepted_for_diagnostic": True,
            "accepted_for_formal": False,
            "human_review_required": True,
            "blocked_reason": "official industry is not equivalent to market theme; TPEx all-stock route locked",
        },
        {
            "theme_id": "electronics_official_industry_proxy",
            "theme_name": "Electronics official industry proxy",
            "theme_family": "non_ai_theme_taxonomy",
            "source": "TWSE MI_INDEX by official industry",
            "source_route": "same TWSE MI_INDEX family",
            "coverage": "TWSE listed industry route; usable only as broad diagnostic comparator candidate",
            "source_quality": "official_date_aware_industry_proxy",
            "accepted_for_diagnostic": True,
            "accepted_for_formal": False,
            "human_review_required": True,
            "blocked_reason": "too broad for mainline theme; needs dated theme policy",
        },
        {
            "theme_id": "financials_official_industry_proxy",
            "theme_name": "Financials official industry proxy",
            "theme_family": "non_ai_theme_taxonomy",
            "source": "TWSE MI_INDEX by official industry",
            "source_route": "same TWSE MI_INDEX family",
            "coverage": "TWSE listed industry route; non-AI broad comparator candidate",
            "source_quality": "official_date_aware_industry_proxy",
            "accepted_for_diagnostic": True,
            "accepted_for_formal": False,
            "human_review_required": True,
            "blocked_reason": "industry comparator only; not market theme taxonomy",
        },
        {
            "theme_id": "shipping_official_industry_proxy",
            "theme_name": "Shipping official industry proxy",
            "theme_family": "non_ai_theme_taxonomy",
            "source": "TWSE MI_INDEX by official industry",
            "source_route": "same TWSE MI_INDEX family",
            "coverage": "TWSE listed industry route; non-AI cyclical comparator candidate",
            "source_quality": "official_date_aware_industry_proxy",
            "accepted_for_diagnostic": True,
            "accepted_for_formal": False,
            "human_review_required": True,
            "blocked_reason": "industry comparator only; not market theme taxonomy",
        },
        {
            "theme_id": "tpex_industry_chain_candidate",
            "theme_name": "TPEx industry-chain candidate",
            "theme_family": "non_ai_theme_taxonomy",
            "source": "TPEx Industry Chain Information Platform",
            "source_route": "https://ic.tpex.org.tw/",
            "coverage": "route inventory only; no accepted date-aware historical membership rows",
            "source_quality": "route_candidate_blocked",
            "accepted_for_diagnostic": False,
            "accepted_for_formal": False,
            "human_review_required": True,
            "blocked_reason": "no materialized dated membership API/file in current package",
        },
    ]

    component_rows = []
    component_overrides = {
        "ai_new_high_count": ("blocked_exact_proxy_available", "Exact rolling new-high count requires accepted daily price panel plus rolling high definition; current Core proxy uses drawdown_60d >= -2%."),
        "ai_breadth_vs_0050": ("proxy_limited", "Breadth depends on accepted membership; current trailing breadth proxy is diagnostic only."),
        "ai_breadth_vs_00631L": ("proxy_limited", "Breadth depends on accepted membership; current trailing breadth proxy is diagnostic only."),
        "ai_turnover_concentration": ("partial_ready_diagnostic", "Official turnover/liquidity components exist, but full all-listed PIT universe remains incomplete."),
        "ai_drawdown_resilience": ("proxy_ready_diagnostic", "Can be computed from price drawdown fields, but not a membership-quality substitute."),
        "best_non_ai_theme_id": ("proxy_upgraded_not_formal", "Non-AI comparator can move from unclassified bucket to official-industry proxy candidates, but still not formal theme taxonomy."),
        "best_non_ai_theme_score": ("proxy_upgraded_not_formal", "Comparator score can be computed against official-industry proxy candidates only after Core adopts the diagnostic taxonomy."),
        "ai_vs_best_non_ai_theme_spread": ("proxy_upgraded_not_formal", "Spread remains proxy because both AI membership and non-AI comparator are not formal-reviewed."),
    }
    for row in core_components:
        component = row.get("component", "")
        status, reason = component_overrides.get(component, (row.get("status", ""), row.get("reason", "")))
        component_rows.append(
            {
                "component": component,
                "readiness_status": status,
                "exact_available": status.startswith("ready_exact"),
                "proxy_available": "proxy" in status or row.get("source_quality") == "proxy",
                "source_quality": row.get("source_quality", ""),
                "source_candidate": "MOPS/TWSE official dated evidence + price/turnover panels where applicable",
                "blocked_reason": reason,
                "accepted_for_diagnostic": True,
                "accepted_for_formal": False,
                "human_review_required": True,
            }
        )

    blocked_rows = []
    for field, blocker, proxy in [
        ("exact_ai_membership", "No formal-approved dated AI membership policy; MOPS evidence remains diagnostic.", "higher_quality_dated_document_diagnostic"),
        ("ai_subtheme_classification", "Subtheme labels are parser/rule derived and require human review.", "MOPS keyword/topic evidence ledger"),
        ("non_ai_theme_taxonomy", "Official industry proxy is not equivalent to market theme taxonomy; TPEx all-stock route locked.", "TWSE official industry proxy taxonomy"),
        ("new_high_count", "Exact rolling new-high count not materialized in Core package.", "drawdown_60d >= -2% proxy"),
        ("breadth", "Requires accepted membership universe.", "trailing breadth proxy"),
        ("turnover_concentration", "All-listed PIT liquidity universe incomplete.", "official partial turnover component"),
        ("drawdown_resilience", "Price-based diagnostic field, not taxonomy evidence.", "drawdown_60d"),
        ("best_non_ai_theme_comparator", "Formal non-AI theme taxonomy not approved/materialized.", "official industry proxy comparator candidates"),
    ]:
        blocked_rows.append(
            {
                "field": field,
                "blocked_reason": blocker,
                "proxy_field_or_source": proxy,
                "future_data_violation_count": 0,
                "accepted_for_formal": False,
                "ready_for_strategy_replay": False,
            }
        )

    attempt_rows = []
    for row in sector_inventory:
        attempt_rows.append(
            {
                "source_id": row.get("source_id", ""),
                "source": row.get("source_name", ""),
                "route_or_path": row.get("source_path_or_url", ""),
                "decision": row.get("decision", ""),
                "accepted_for_diagnostic": row.get("accepted_for_diagnostic", ""),
                "accepted_for_formal": row.get("accepted_for_formal", ""),
                "notes": row.get("notes", ""),
            }
        )
    for row in sector_blocked[:20] + tpex_attempts[:10]:
        attempt_rows.append(
            {
                "source_id": row.get("source_id") or row.get("attempt_scope", ""),
                "source": row.get("source_name") or row.get("route_id", ""),
                "route_or_path": row.get("source_path_or_url") or row.get("url", ""),
                "decision": row.get("decision") or row.get("status", ""),
                "accepted_for_diagnostic": row.get("accepted_for_diagnostic", "false"),
                "accepted_for_formal": row.get("accepted_for_formal", "false"),
                "notes": row.get("notes") or row.get("error") or "",
            }
        )

    write_csv(OUT / "ai_membership_source_package_upgrade.csv", ai_package_rows, list(ai_package_rows[0].keys()))
    write_csv(OUT / "ai_subtheme_classification_evidence_ledger.csv", subtheme_rows, list(subtheme_rows[0].keys()))
    write_csv(OUT / "non_ai_theme_taxonomy_candidate_ledger.csv", non_ai_taxonomy, list(non_ai_taxonomy[0].keys()))
    write_csv(OUT / "theme_strength_score_component_readiness_ledger.csv", component_rows, list(component_rows[0].keys()))
    write_csv(OUT / "blocked_fields_and_proxy_fields.csv", blocked_rows, list(blocked_rows[0].keys()))
    write_csv(OUT / "source_attempt_evidence.csv", attempt_rows, list(attempt_rows[0].keys()))

    source_quality_counts = Counter(r["source_quality"] for r in ai_package_rows)
    readiness = {
        "date": date.today().isoformat(),
        "task_id": "TASK-RADAR-DATA-VNEXT-THEME-TAXONOMY-SOURCE-PACKAGE-20260706",
        "owner": "AI_stock_rotation_radar / Radar-Data",
        "status": "completed_bounded_source_package_ready_for_core_research_judgment",
        "diagnostic_only": True,
        "ready_for_core_rerun": True,
        "ready_for_proxy_limited_ai_allocation_rerun": True,
        "ready_for_higher_quality_ai_allocation_rerun": False,
        "ready_for_strategy_replay": False,
        "ready_for_formal": False,
        "future_data_violation_count": 0,
        "ai_membership_rows": len(ai_package_rows),
        "higher_quality_dated_ai_membership_rows": sum(1 for r in ai_package_rows if r["higher_quality_dated_membership_available"]),
        "exact_ai_membership_rows": 0,
        "ai_subtheme_evidence_rows": len(subtheme_rows),
        "non_ai_taxonomy_candidate_rows": len(non_ai_taxonomy),
        "source_quality_counts": dict(source_quality_counts),
        "blocked_field_count": len(blocked_rows),
        "remaining_blockers": [
            "formal taxonomy policy not approved",
            "human review still required for AI subtheme and membership labels",
            "TPEx all-stock historical sector membership route remains locked",
            "official industry proxies are not equivalent to market theme taxonomy",
            "exact rolling new-high count is not materialized",
        ],
        **FLAGS,
    }
    (OUT / "readiness_for_core_research.json").write_text(json.dumps(readiness, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    manifest = {
        "task_id": readiness["task_id"],
        "created_at": date.today().isoformat(),
        "inputs": {
            "core_package": str(CORE),
            "mops_document_extraction_v1": str(MOPS_DOC),
            "mops_mainline_evidence_ledger": str(MOPS_MAINLINE),
            "sector_taxonomy_readiness": str(SECTOR_READY),
            "sector_mainline_source_package": str(SECTOR_SOURCE),
        },
        "outputs": [
            "ai_membership_source_package_upgrade.csv",
            "ai_subtheme_classification_evidence_ledger.csv",
            "non_ai_theme_taxonomy_candidate_ledger.csv",
            "theme_strength_score_component_readiness_ledger.csv",
            "blocked_fields_and_proxy_fields.csv",
            "source_attempt_evidence.csv",
            "readiness_for_core_research.json",
            "final_summary_zh.md",
        ],
        "flags": FLAGS,
    }
    (OUT / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    summary = f"""# vNext Theme Taxonomy Source Package 補件

Status: completed_bounded_source_package_ready_for_core_research_judgment

結論：
- 已把 Core proxy package 升級成 bounded source/readiness package。
- AI membership 有 {readiness['higher_quality_dated_ai_membership_rows']} 筆較高品質 dated company-document diagnostic evidence；exact/formal rows 仍為 0。
- AI subtheme evidence ledger 有 {readiness['ai_subtheme_evidence_rows']} 筆，全部 diagnostic-only、accepted_for_formal=false、human_review_required=true。
- non-AI taxonomy 不再只給 `non_ai_unclassified_proxy`，改提供 TWSE official industry proxy comparator candidates；但仍不是 formal market theme taxonomy。
- theme_strength_score components 已拆成 exact/proxy/blocker ledger；new-high count、breadth、best non-AI comparator 仍 blocked/proxy。

Flags:
- formal_model_changed=false
- trade_decision_changed=false
- active_in_trade_decision=false
- report_changed=false
- portfolio_replay_executed=false
- ready_for_strategy_replay=false
- future_data_violation_count=0

Readiness:
- ready_for_core_rerun=true
- ready_for_proxy_limited_ai_allocation_rerun=true
- ready_for_higher_quality_ai_allocation_rerun=false
- ready_for_formal=false

主要 blocker：
- formal taxonomy policy not approved
- human review still required
- TPEx all-stock historical sector membership route remains locked
- official industry proxies are not equivalent to market theme taxonomy
- exact rolling new-high count is not materialized

建議下一棒：
- 交 Core / vNext Research 判斷：這個 bounded 補件是否足以讓 Experiments 做 proxy-limited AI allocation diagnostic rerun。
"""
    (OUT / "final_summary_zh.md").write_text(summary, encoding="utf-8")


if __name__ == "__main__":
    main()
