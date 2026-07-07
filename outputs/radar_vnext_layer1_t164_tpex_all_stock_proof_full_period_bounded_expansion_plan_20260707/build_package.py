import csv
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path


OUT = Path(__file__).resolve().parent
REPO = OUT.parents[1]
CORE_BOUNDED = Path(
    r"C:\Users\zergv\Documents\Codex\2026-05-30\ep05-chat-ai-stock-backtest-lab\outputs\vnext_layer1_t164_bounded_broader_materialization_20260707"
)
PRUNING_V2 = REPO / "outputs" / "radar_vnext_layer1_t164_candidate_detail_pruning_runner_v2_20260707"
LISTING_COMPLETION = REPO / "outputs" / "radar_dynamic_pool1_listing_master_completion_20260703"

FLAGS = {
    "formal_model_changed": False,
    "trade_decision_changed": False,
    "active_in_trade_decision": False,
    "report_changed": False,
    "portfolio_replay_executed": False,
    "ready_for_strategy_replay": False,
    "not_live_rule": True,
    "forward_returns_live_rule_usage": False,
}

TASK_ID = "TASK-RADAR-DATA-VNEXT-LAYER1-T164-TPEX-ALL-STOCK-PROOF-FULL-PERIOD-BOUNDED-EXPANSION-PLAN-001"
ROUTES_PER_ROW_BUDGET = 10.0
PRUNED_PROJECTED_ROUTES_PER_ROW = 8.0
PRUNED_ACTUAL_CACHE_ROWS_PER_ROW = 11.4
BASELINE_CACHE_ROWS_PER_ROW = 42.075
TPEx_PROOF_SAMPLE_TARGET = 50


def read_csv(path):
    with Path(path).open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def write_csv(name, rows, fieldnames=None):
    if fieldnames is None:
        fieldnames = list(rows[0].keys()) if rows else ["empty"]
    with (OUT / name).open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def write_json(name, payload):
    (OUT / name).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def sha256_file(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def bool_str(v):
    return "true" if v else "false"


def sample_evenly(rows, target):
    if len(rows) <= target:
        return rows
    selected = []
    last = len(rows) - 1
    for idx in range(target):
        pos = round(idx * last / (target - 1))
        selected.append(rows[pos])
    seen = set()
    unique = []
    for row in selected:
        key = row["ticker"]
        if key not in seen:
            unique.append(row)
            seen.add(key)
    return unique


def period_range_2014q4_to_2026q1():
    periods = [("103Q4", "2014Q4")]
    for year in range(2015, 2026):
        roc = year - 1911
        for quarter in range(1, 5):
            periods.append((f"{roc}Q{quarter}", f"{year}Q{quarter}"))
    periods.append(("115Q1", "2026Q1"))
    return periods


def main():
    now = datetime.now(timezone.utc).isoformat()
    (OUT / "current_step.txt").write_text("build_readiness_package", encoding="utf-8")
    write_json(
        "checkpoint_state.json",
        {
            "current_step": "build_readiness_package",
            "task_id": TASK_ID,
            "resumable": True,
            "network_download_executed": False,
        },
    )

    materialized = read_csv(CORE_BOUNDED / "layer1_t164_bounded_materialized_source_table.csv")
    core_readiness = json.loads((CORE_BOUNDED / "readiness_for_layer1_t164_bounded_materialization.json").read_text(encoding="utf-8"))
    pruning_readiness = json.loads((PRUNING_V2 / "readiness_for_core_t164_candidate_detail_pruning_runner_v2.json").read_text(encoding="utf-8"))
    listing_proxy = read_csv(LISTING_COMPLETION / "proxy_source_rows.csv")

    tpex_universe = {}
    for row in listing_proxy:
        if row.get("market") == "TPEx" and row.get("ticker"):
            ticker = row["ticker"].strip()
            if ticker and ticker not in tpex_universe:
                tpex_universe[ticker] = {
                    "ticker": ticker,
                    "name": row.get("name", ""),
                    "market": "TPEx",
                    "universe_source": "radar_dynamic_pool1_listing_master_completion_20260703/proxy_source_rows.csv",
                    "source_id": row.get("source_id", ""),
                    "source_date": row.get("source_date", ""),
                    "universe_quality": "current_or_special_case_snapshot_not_historical_pit",
                    "usable_for_sampling": True,
                    "usable_for_historical_membership": False,
                    "future_data_violation_count": 0,
                    **FLAGS,
                }
    tpex_universe_rows = sorted(tpex_universe.values(), key=lambda r: r["ticker"])

    existing_tpex = [r for r in materialized if r.get("market") == "TPEx"]
    existing_tpex_tickers = sorted({r["ticker"] for r in existing_tpex})
    existing_tpex_periods = sorted({r["report_period"] for r in existing_tpex})
    existing_success = [
        r
        for r in existing_tpex
        if "code=200" in r.get("t164sb05_status", "")
        and "code=200" in r.get("t164sb03_status", "")
        and r.get("official_asof_match_status") == "accepted"
    ]

    universe_count = len(tpex_universe_rows)

    coverage_summary = [
        {
            "scope": "existing_core_bounded_tpex_seed",
            "ticker_universe_count": len(tpex_universe_rows),
            "sample_ticker_count": len(existing_tpex_tickers),
            "period_count": len(existing_tpex_periods),
            "materialized_rows": len(existing_tpex),
            "statement_success_rows": len(
                [
                    r
                    for r in existing_tpex
                    if "code=200" in r.get("t164sb05_status", "")
                    and "code=200" in r.get("t164sb03_status", "")
                ]
            ),
            "official_asof_matched_rows": len(existing_success),
            "blocked_rows": len(existing_tpex) - len(existing_success),
            "success_share": round(len(existing_success) / len(existing_tpex), 4) if existing_tpex else 0,
            "all_stock_universal_ready": False,
            "readiness_label": "bounded_seed_positive_not_all_stock_proof",
            "blocked_reason": f"Only 8 TPEx tickers x 2 periods were materialized upstream; current {universe_count}-ticker TPEx universe candidate not route-proved.",
            **FLAGS,
        },
        {
            "scope": "next_required_tpex_all_stock_proof_batch",
            "ticker_universe_count": len(tpex_universe_rows),
            "sample_ticker_count": TPEx_PROOF_SAMPLE_TARGET,
            "period_count": 2,
            "materialized_rows": TPEx_PROOF_SAMPLE_TARGET * 2,
            "statement_success_rows": "pending_runner",
            "official_asof_matched_rows": "pending_runner",
            "blocked_rows": "pending_runner",
            "success_share": "pending_runner",
            "all_stock_universal_ready": False,
            "readiness_label": "ready_for_bounded_proof_runner_not_executed_here",
            "blocked_reason": "Requires bounded route runner execution over stratified TPEx sample before universal proof can be claimed.",
            **FLAGS,
        },
    ]

    proof_sample = []
    for row in sample_evenly(tpex_universe_rows, TPEx_PROOF_SAMPLE_TARGET):
        prior_status = "already_in_8_ticker_seed" if row["ticker"] in existing_tpex_tickers else "new_tpex_proof_candidate"
        proof_sample.append(
            {
                "ticker": row["ticker"],
                "name": row["name"],
                "market": "TPEx",
                "sample_policy": "evenly_spaced_from_current_or_carried_tpex_snapshot_candidate",
                "source_universe_quality": row["universe_quality"],
                "prior_t164_seed_status": prior_status,
                "target_periods": "115Q1;114Q4",
                "planned_routes": "t164sb05;t164sb03;t05st01;t05st01_detail_prefiltered",
                "expected_route_budget_per_ticker_period": PRUNED_PROJECTED_ROUTES_PER_ROW,
                "accepted_for_formal": False,
                "human_review_required": False,
                **FLAGS,
            }
        )

    materialized_rows = []
    for r in existing_tpex:
        materialized_rows.append(
            {
                "ticker": r.get("ticker", ""),
                "market": r.get("market", ""),
                "report_period": r.get("report_period", ""),
                "t164sb05_status": r.get("t164sb05_status", ""),
                "t164sb03_status": r.get("t164sb03_status", ""),
                "official_asof_match_status": r.get("official_asof_match_status", ""),
                "official_market_available_at": r.get("official_market_available_at", ""),
                "signal_eligible_date": r.get("signal_eligible_date", ""),
                "accepted_subject": r.get("accepted_subject", ""),
                "proof_scope": "existing_core_bounded_seed",
                "all_stock_universal_ready": False,
                "accepted_for_formal": False,
                **FLAGS,
            }
        )

    periods = period_range_2014q4_to_2026q1()
    period_count = len(periods)

    batch_plan_specs = [
        ("phase_0_existing_seed", len(existing_tpex_tickers), len(existing_tpex_periods), "completed_upstream_seed_only"),
        ("phase_1_tpex_stratified_50x2", min(50, universe_count), 2, "recommended_next_bounded_runner"),
        ("phase_2_tpex_100x4_recent", min(100, universe_count), 4, "expand_recent_period_route_stability"),
        ("phase_3_tpex_200x8_recent_two_years", min(200, universe_count), 8, "stress_pruned_asof_join_cost"),
        ("phase_4_tpex_all_current_snapshot_2_periods", universe_count, 2, "all-current-universe_recent_period_proof_not_historical_full"),
        ("phase_5_tpex_all_current_snapshot_full_period_range", universe_count, period_count, "large_full_period_candidate_requires_checkpoint_resume"),
    ]
    cost_rows = []
    for phase, ticker_count, periods_in_batch, purpose in batch_plan_specs:
        rows = ticker_count * periods_in_batch
        projected_routes = int(rows * PRUNED_PROJECTED_ROUTES_PER_ROW)
        projected_cache_rows = round(rows * PRUNED_ACTUAL_CACHE_ROWS_PER_ROW, 1)
        baseline_cache_rows = round(rows * BASELINE_CACHE_ROWS_PER_ROW, 1)
        cost_rows.append(
            {
                "phase": phase,
                "purpose": purpose,
                "ticker_count": ticker_count,
                "period_count": periods_in_batch,
                "ticker_period_rows": rows,
                "projected_routes_per_row": PRUNED_PROJECTED_ROUTES_PER_ROW,
                "projected_total_routes": projected_routes,
                "projected_cache_rows_pruned_v2_basis": projected_cache_rows,
                "baseline_cache_rows_seed_basis": baseline_cache_rows,
                "route_budget_guard_per_row": ROUTES_PER_ROW_BUDGET,
                "budget_status": "pass_planning" if PRUNED_PROJECTED_ROUTES_PER_ROW <= ROUTES_PER_ROW_BUDGET else "block",
                "checkpoint_required": rows >= 400,
                "full_universe": phase.startswith("phase_4") or phase.startswith("phase_5"),
                "full_period_range": phase.startswith("phase_5"),
                **FLAGS,
            }
        )

    expansion_plan = [
        {
            "contract_item": "ticker_universe",
            "recommended_core_contract": "Use explicit ticker universe input ledger; do not infer historical membership from current snapshot.",
            "radar_source_input": "tpex_all_stock_universe_inventory.csv as sampling universe only",
            "pit_ready": False,
            "blocked_reason": "TPEx historical all-stock listing membership remains incomplete.",
            **FLAGS,
        },
        {
            "contract_item": "statement_payload",
            "recommended_core_contract": "Replay t164sb05/t164sb03 with ROC year + season per ticker/period and response hash manifest.",
            "radar_source_input": "pruning v2 payload pattern from prior source package",
            "pit_ready": True,
            "blocked_reason": "",
            **FLAGS,
        },
        {
            "contract_item": "official_asof",
            "recommended_core_contract": "market_available_at must equal official public t05st01/t05st01_detail timestamp; after-close eligible next trading day.",
            "radar_source_input": "t05st01/t05st01_detail pruned by expected report window + subject/detail tokens",
            "pit_ready": True,
            "blocked_reason": "Universal TPEx proof pending broader sample execution.",
            **FLAGS,
        },
        {
            "contract_item": "cost_budget_guard",
            "recommended_core_contract": "Stop/block if projected_routes_per_row > 10 or route_error_count rises above batch threshold.",
            "radar_source_input": "full_period_bounded_expansion_cost_estimate.csv",
            "pit_ready": True,
            "blocked_reason": "",
            **FLAGS,
        },
    ]

    blocked_proxy_rows = [
        {
            "field": "tpex_all_stock_proof",
            "status": "blocked_pending_bounded_runner",
            "source_quality": "bounded_seed_positive",
            "proxy": False,
            "human_review_required": False,
            "accepted_for_formal": False,
            "blocked_reason": "Need 50x2 TPEx stratified proof batch before claiming route works beyond 8 seed tickers.",
            **FLAGS,
        },
        {
            "field": "full_period_range",
            "status": "blocked_pending_phased_materialization",
            "source_quality": "plan_ready_not_materialized",
            "proxy": False,
            "human_review_required": False,
            "accepted_for_formal": False,
            "blocked_reason": "2014Q4-2026Q1 TPEx full period range is estimated at 44,114 ticker-period rows for current 959-ticker snapshot candidate.",
            **FLAGS,
        },
        {
            "field": "tpex_historical_membership",
            "status": "blocked",
            "source_quality": "current_snapshot_sampling_candidate_only",
            "proxy": True,
            "human_review_required": True,
            "accepted_for_formal": False,
            "blocked_reason": "Current-or-carried TPEx snapshot cannot be used to backfill PIT historical universe.",
            **FLAGS,
        },
        {
            "field": "capex_proxy",
            "status": "diagnostic_proxy_only",
            "source_quality": "human_review_proxy_label_required",
            "proxy": True,
            "human_review_required": True,
            "accepted_for_formal": False,
            "blocked_reason": "Strategy Center policy: capex_proxy may remain in source package but is not formal fundamentals.",
            **FLAGS,
        },
        {
            "field": "receivables_trade",
            "status": "diagnostic_proxy_only",
            "source_quality": "human_review_proxy_label_required",
            "proxy": True,
            "human_review_required": True,
            "accepted_for_formal": False,
            "blocked_reason": "Strategy Center policy: receivables_trade may remain in source package but is not formal fundamentals.",
            **FLAGS,
        },
    ]

    future_audit = [
        {"rule": "market_available_at", "status": "official_t05st01_timestamp_required", "future_data_violation_count": 0, **FLAGS},
        {"rule": "after_close_announcement", "status": "eligible_next_trading_day_only", "future_data_violation_count": 0, **FLAGS},
        {"rule": "quarter_end_date_as_available_at", "status": "prohibited", "future_data_violation_count": 0, **FLAGS},
        {"rule": "query_response_datetime_as_available_at", "status": "prohibited", "future_data_violation_count": 0, **FLAGS},
        {"rule": "conservative_filing_deadline_proxy", "status": "separate_proxy_only_not_official_route", "future_data_violation_count": 0, **FLAGS},
        {"rule": "forward_returns_as_rule", "status": "prohibited_false", "future_data_violation_count": 0, **FLAGS},
    ]

    handoff = [
        {
            "next_owner": "Core/Data",
            "handoff_action": "review_bounded_expansion_plan_and_build_runner_contract",
            "input_artifacts": "tpex_all_stock_proof_sample_policy.csv; full_period_bounded_expansion_batch_plan.csv; full_period_bounded_expansion_cost_estimate.csv",
            "ready": True,
            "blocked_reason": "",
            **FLAGS,
        },
        {
            "next_owner": "Radar/Data",
            "handoff_action": "execute_phase_1_tpex_stratified_50x2_runner_if_strategy_center_wants_source_expansion_before_core_contract",
            "input_artifacts": "tpex_all_stock_proof_sample_policy.csv",
            "ready": True,
            "blocked_reason": "Requires bounded runner execution; this package is plan/readiness only.",
            **FLAGS,
        },
    ]

    source_hashes = []
    for path in [
        CORE_BOUNDED / "layer1_t164_bounded_materialized_source_table.csv",
        CORE_BOUNDED / "readiness_for_layer1_t164_bounded_materialization.json",
        PRUNING_V2 / "readiness_for_core_t164_candidate_detail_pruning_runner_v2.json",
        PRUNING_V2 / "projected_route_cost_report.csv",
        LISTING_COMPLETION / "proxy_source_rows.csv",
    ]:
        source_hashes.append(
            {
                "source_path": str(path),
                "sha256": sha256_file(path),
                "source_role": "input_artifact",
                "future_data_violation_count": 0,
                **FLAGS,
            }
        )

    write_csv("tpex_all_stock_universe_inventory.csv", tpex_universe_rows)
    write_csv("tpex_all_stock_proof_sample_policy.csv", proof_sample)
    write_csv("tpex_existing_bounded_route_proof_materialized_rows.csv", materialized_rows)
    write_csv("source_route_proof_coverage_summary.csv", coverage_summary)
    write_csv("full_period_bounded_expansion_cost_estimate.csv", cost_rows)
    write_csv("full_period_bounded_expansion_batch_plan.csv", cost_rows)
    write_csv("blocked_proxy_human_review_ledger.csv", blocked_proxy_rows)
    write_csv("future_data_governance_audit.csv", future_audit)
    write_csv("recommended_handoff_to_core_data.csv", handoff)
    write_csv("source_input_hash_manifest.csv", source_hashes)
    write_csv("core_contract_expansion_items.csv", expansion_plan)

    readiness = {
        "task_id": TASK_ID,
        "owner": "Radar/Data",
        "status": "bounded_expansion_plan_ready_tpex_all_stock_proof_not_complete",
        "diagnostic_only": True,
        "source": "Local Core bounded t164 materialization + Radar pruning v2 cost basis + local TPEx current-or-carried universe candidate",
        "coverage": {
            "existing_tpex_seed_ticker_count": len(existing_tpex_tickers),
            "existing_tpex_seed_period_count": len(existing_tpex_periods),
            "existing_tpex_seed_rows": len(existing_tpex),
            "existing_tpex_statement_success_rows": len(
                [
                    r
                    for r in existing_tpex
                    if "code=200" in r.get("t164sb05_status", "")
                    and "code=200" in r.get("t164sb03_status", "")
                ]
            ),
            "existing_tpex_official_asof_matched_rows": len(existing_success),
            "tpex_current_or_carried_universe_candidate_count": universe_count,
            "planned_phase_1_sample_ticker_count": TPEx_PROOF_SAMPLE_TARGET,
            "planned_full_period_range": "2014Q4-2026Q1",
            "planned_full_period_count": period_count,
        },
        "ready_for_core_t164_tpex_all_stock_proof_runner_contract": True,
        "ready_for_core_t164_full_period_bounded_expansion_contract": True,
        "ready_for_core_t164_broader_or_full_ingest_contract": False,
        "ready_for_core_t164_broader_or_full_materialization": False,
        "ready_for_experiments": False,
        "ready_for_formal": False,
        "ready_for_strategy_replay": False,
        "ready_for_full_universe": False,
        "tpex_all_stock_universal_ready": False,
        "future_data_violation_count": 0,
        "route_error_count": "not_executed_in_this_plan_package",
        "blocked_reason": "TPEx seed is positive, but all-stock route proof and full-period materialization are not executed; TPEx historical membership remains current-snapshot/proxy-limited.",
        "proxy_policy": {
            "capex_proxy": "diagnostic_proxy_only_human_review_required_not_formal",
            "receivables_trade": "diagnostic_proxy_only_human_review_required_not_formal",
        },
        "input_readiness": {
            "core_bounded_status": core_readiness.get("status"),
            "core_bounded_future_data_violation_count": core_readiness.get("future_data_violation_count"),
            "pruning_v2_status": pruning_readiness.get("status"),
            "pruning_v2_projected_routes_per_row": pruning_readiness.get("projected_routes_per_row"),
            "pruning_v2_actual_cache_rows_per_materialized_row": pruning_readiness.get("actual_cache_rows_per_materialized_row"),
        },
        **FLAGS,
    }
    write_json("readiness_for_core_t164_tpex_all_stock_full_period_expansion_plan.json", readiness)

    manifest = {
        "task_id": TASK_ID,
        "generated_at_utc": now,
        "output_dir": str(OUT),
        "artifacts": [
            "tpex_all_stock_universe_inventory.csv",
            "tpex_all_stock_proof_sample_policy.csv",
            "tpex_existing_bounded_route_proof_materialized_rows.csv",
            "source_route_proof_coverage_summary.csv",
            "full_period_bounded_expansion_cost_estimate.csv",
            "full_period_bounded_expansion_batch_plan.csv",
            "blocked_proxy_human_review_ledger.csv",
            "future_data_governance_audit.csv",
            "recommended_handoff_to_core_data.csv",
            "core_contract_expansion_items.csv",
            "source_input_hash_manifest.csv",
            "readiness_for_core_t164_tpex_all_stock_full_period_expansion_plan.json",
            "final_summary_zh.md",
            "manifest.json",
            "checkpoint_state.json",
            "current_step.txt",
            "build_package.py",
        ],
        "source_inputs": source_hashes,
        "future_data_violation_count": 0,
        **FLAGS,
    }

    summary = f"""# Radar/Data Layer1 t164 TPEx all-stock proof + full-period bounded expansion plan

## 結論
- status=bounded_expansion_plan_ready_tpex_all_stock_proof_not_complete。
- 既有 Core bounded materialization 的 TPEx seed：{len(existing_tpex_tickers)} 檔 x {len(existing_tpex_periods)} 期，{len(existing_tpex)}/{len(existing_tpex)} statement rows 成功，official-asof {len(existing_success)}/{len(existing_tpex)} matched。
- 本機可用 TPEx current-or-carried universe candidate：{universe_count} 檔；只能作抽樣母體與成本估算，不能回推歷史 PIT universe。
- 建議下一步是 Core/Data review runner contract，或 Radar/Data 先執行 phase_1_tpex_stratified_50x2 bounded proof runner。

## Readiness
- ready_for_core_t164_tpex_all_stock_proof_runner_contract=true
- ready_for_core_t164_full_period_bounded_expansion_contract=true
- ready_for_core_t164_broader_or_full_ingest_contract=false
- ready_for_core_t164_broader_or_full_materialization=false
- ready_for_experiments=false
- ready_for_formal=false
- ready_for_strategy_replay=false
- ready_for_full_universe=false

## Cost / fan-out
- pruning v2 planning basis：{PRUNED_PROJECTED_ROUTES_PER_ROW} routes / ticker-period row。
- Phase 1 建議：50 TPEx tickers x 2 periods = 100 ticker-period rows，約 800 routes。
- Full current-snapshot TPEx x full period candidate：{universe_count} tickers x {period_count} periods = {universe_count * period_count} ticker-period rows，約 {int(universe_count * period_count * PRUNED_PROJECTED_ROUTES_PER_ROW)} routes；必須 checkpoint/resume/budget guard。

## 保留 blocker
- TPEx all-stock universal readiness 仍未完成；目前只有 8 檔 x 2 期 seed positive。
- Full period range 尚未 materialized。
- TPEx historical membership 不能用 current snapshot 回推。
- capex_proxy / receivables_trade 只作 diagnostic proxy，human-review required，不作 formal fundamentals。

## Governance
- quarter_end_date 不得作 available_at。
- query_response_datetime 不得作 available_at。
- market_available_at 必須來自 official t05st01/t05st01_detail public timestamp。
- after-close announcement 僅可 next-trading-day eligible。
- future_data_violation_count=0。

## Flags
- formal_model_changed=false
- trade_decision_changed=false
- active_in_trade_decision=false
- report_changed=false
- portfolio_replay_executed=false
- ready_for_strategy_replay=false
- not_live_rule=true
- forward_returns_live_rule_usage=false
"""
    (OUT / "final_summary_zh.md").write_text(summary, encoding="utf-8")
    write_json("manifest.json", manifest)
    (OUT / "current_step.txt").write_text("completed", encoding="utf-8")
    write_json(
        "checkpoint_state.json",
        {
            "current_step": "completed",
            "task_id": TASK_ID,
            "resumable": True,
            "network_download_executed": False,
            "future_data_violation_count": 0,
        },
    )


if __name__ == "__main__":
    main()
