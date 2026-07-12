from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path

from run_p3_placebo_tradability_termination_gap_fill import FLAGS, fetch_month, sha256_file, write_csv


TASK_ID = "TASK-RADAR-DATA-VNEXT-P3-FULL-SPEC-V2-STAGE-B-PLACEBO-OHLC-GAP-FILL-003"
OUTPUT_NAME = "radar_vnext_p3_full_spec_v2_stage_b_placebo_ohlc_gap_fill_20260712"
CORE_AUDIT = Path("C:/Users/zergv/Documents/Codex/2026-05-30/ep05-chat-ai-stock-backtest-lab/outputs/vnext_p3_layer5_phase_b_complete_paths_20260712/p3_layer5_phase_b_all_scenario_tradability_horizon_audit.csv")

MARKETS = {
    "1522": "TWSE", "1618": "TWSE", "2301": "TWSE", "2476": "TWSE",
    "3138": "TWSE", "3481": "TWSE", "3563": "TWSE", "3661": "TWSE",
    "4746": "TWSE", "5534": "TWSE", "6117": "TWSE", "6257": "TWSE",
    "6799": "TWSE", "3152": "TPEx", "3680": "TPEx", "4908": "TPEx",
    "6190": "TPEx", "8048": "TPEx", "8088": "TPEx",
}

EXPECTED = {
    ("1522", "5534", "2025-04-09"), ("5534", "3563", "2025-04-22"),
    ("6190", "6257", "2026-06-02"), ("8048", "3661", "2023-10-31"),
    ("4908", "2476", "2026-05-05"), ("4746", "6799", "2024-03-12"),
    ("1618", "2301", "2025-06-03"), ("3138", "3481", "2026-03-31"),
    ("3152", "6117", "2023-12-12"), ("8088", "3680", "2026-02-10"),
}


def main() -> None:
    repo = Path(__file__).resolve().parents[1]
    output = repo / "outputs" / OUTPUT_NAME
    raw_dir = output / "raw_audit_samples"
    output.mkdir(parents=True, exist_ok=True)
    raw_dir.mkdir(parents=True, exist_ok=True)

    with CORE_AUDIT.open(encoding="utf-8-sig", newline="") as handle:
        audit = list(csv.DictReader(handle))
    blocked = [row for row in audit if row["tradability_horizon_ready"].lower() == "false"]
    actual = {(row["intended_prior_target"], row["intended_new_target"], row["requested_execution_date"]) for row in blocked}
    if actual != EXPECTED:
        raise RuntimeError(f"Core Stage B blocker scope changed: {sorted(actual)}")

    query_keys: set[tuple[str, str, str]] = set()
    for row in blocked:
        for ticker in (row["intended_prior_target"], row["intended_new_target"]):
            query_keys.add((ticker, MARKETS[ticker], row["requested_execution_date"][:7]))

    all_prices: list[dict] = []
    source_manifest: list[dict] = []
    exact: dict[tuple[str, str], dict] = {}
    (output / "current_step.txt").write_text(f"fetching_0_of_{len(query_keys)}\n", encoding="utf-8")
    for index, (ticker, market, month) in enumerate(sorted(query_keys), start=1):
        rows, manifest = fetch_month(ticker, market, month, raw_dir)
        all_prices.extend(rows)
        source_manifest.append(manifest)
        for row in rows:
            exact[(ticker, row["date"])] = row
        (output / "current_step.txt").write_text(f"fetching_{index}_of_{len(query_keys)}\n", encoding="utf-8")

    patches: list[dict] = []
    impacts: list[dict] = []
    false_events: list[dict] = []
    remaining: list[dict] = []
    for row in blocked:
        prior = row["intended_prior_target"]
        new = row["intended_new_target"]
        execution = row["requested_execution_date"]
        prior_ready = (prior, execution) in exact
        new_ready = (new, execution) in exact
        ready = prior_ready and new_ready
        impact = {
            "scenario": row["scenario"], "decision_date": row["decision_date"],
            "requested_execution_date": execution, "prior_target": prior, "new_target": new,
            "core_prior_last_price_date": row["prior_target_last_official_price_date"],
            "prior_exact_official_close_ready": prior_ready, "new_exact_official_close_ready": new_ready,
            "exact_same_day_transition_ready": ready,
            "status": "active_scope_compact_gap_official_patch_ready" if ready else "official_exact_date_blocked",
            "false_termination_inference": ready, "future_data_violation_count": 0,
        }
        impacts.append(impact)
        if ready:
            for role, ticker in (("prior_exit", prior), ("new_entry", new)):
                patches.append({
                    "scenario": row["scenario"], "decision_date": row["decision_date"],
                    "requested_execution_date": execution, "actual_execution_date": execution,
                    "role": role, **exact[(ticker, execution)],
                })
            false_events.append({
                "scenario": row["scenario"], "ticker": prior,
                "event_type": "false_positive_termination_inference",
                "holder_treatment": "not_applicable_official_trading_continues",
                "evidence": f"official exact execution-date OHLC exists on {execution}",
                "source_url": exact[(prior, execution)]["source_url"],
                "raw_sha256": exact[(prior, execution)]["raw_sha256"],
                "future_data_violation_count": 0,
            })
        else:
            remaining.append({
                **impact,
                "blocked_reason": "official exact requested execution-date price absent for prior or new target",
                "attempted_source": "TWSE_RWD_STOCK_DAY_or_TPEX_TRADING_STOCK",
                "no_last_price_neighbor_or_benchmark_substitution": True,
            })

    price_fields = [
        "scenario", "decision_date", "requested_execution_date", "actual_execution_date", "role",
        "date", "ticker", "market", "open", "high", "low", "close", "volume", "turnover_value",
        "source_url", "source_route", "source_quality", "adjustment_policy", "raw_sha256",
        "raw_cache_path", "retrieval_time_utc", "future_data_violation_count",
    ]
    write_csv(output / "full_spec_v2_stage_b_placebo_official_ohlcv_patch_rows.csv", patches, price_fields)
    write_csv(output / "full_spec_v2_stage_b_placebo_official_unadjusted_ohlcv_rows.csv", all_prices, price_fields[5:])
    write_csv(output / "full_spec_v2_stage_b_placebo_source_manifest.csv", source_manifest)
    write_csv(output / "full_spec_v2_stage_b_placebo_path_impact_ledger.csv", impacts)
    write_csv(output / "full_spec_v2_stage_b_placebo_false_termination_ledger.csv", false_events)
    write_csv(output / "full_spec_v2_stage_b_placebo_blocked_ledger.csv", remaining)
    write_csv(output / "full_spec_v2_stage_b_placebo_future_data_audit.csv", [{
        "audit": "requested execution date exact official OHLC only; no last-price, neighbour, benchmark, or current-status backfill",
        "status": "pass", "future_data_violation_count": 0,
    }])

    ready = len(impacts) == 10 and not remaining
    readiness = {
        "task_id": TASK_ID,
        "status": "full_spec_v2_stage_b_placebo_exact_ohlc_patch_ready" if ready else "full_spec_v2_stage_b_placebo_ohlc_partial_blocked",
        "source": "official selected ticker-month TWSE STOCK_DAY / TPEx tradingStock",
        "coverage": "Core full_spec_v2 Stage B incremental gap only; 10 episodes / 20 roles / 19 unique ticker-date keys",
        "input_gap_episodes": len(blocked), "requested_role_rows": 20,
        "unique_ticker_date_queries": len(query_keys), "official_patch_rows": len(patches),
        "resolved_episodes": sum(row["exact_same_day_transition_ready"] for row in impacts),
        "blocked_episodes": len(remaining),
        "ready_for_core_p3_full_spec_v2_stage_b_placebo_ohlcv_absorption": ready,
        "ready_for_core_rerun": ready, "ready_for_experiments": False,
        "future_data_violation_count": 0, **FLAGS,
    }
    (output / "readiness_for_core_p3_full_spec_v2_stage_b_placebo_ohlcv_absorption.json").write_text(json.dumps(readiness, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (output / "final_summary_zh.md").write_text(
        f"# P3 full_spec_v2 Stage B placebo OHLC fill 003\n\n"
        f"- input episodes={len(blocked)}；role rows=20；unique ticker-date queries={len(query_keys)}。\n"
        f"- exact requested-date resolved={readiness['resolved_episodes']}；patch rows={len(patches)}；blocked={len(remaining)}。\n"
        "- 不使用last-price、neighbor或benchmark替代。\n"
        f"- ready_for_core absorption={str(ready).lower()}；future_data_violation_count=0。\n"
        "- 下一棒交Core/Data absorption/rechain；Radar不算績效。\n",
        encoding="utf-8",
    )
    (output / "current_step.txt").write_text("completed_handoff_core_pending\n", encoding="utf-8")

    artifacts = []
    for path in sorted(output.rglob("*")):
        if path.is_file() and path.name != "manifest.json":
            artifacts.append({"path": str(path.relative_to(output)), "bytes": path.stat().st_size, "sha256": sha256_file(path)})
    manifest = {
        "task_id": TASK_ID, "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "source": readiness["source"], "coverage": readiness["coverage"],
        "future_data_violation_count": 0, "ready_for_core_rerun": ready,
        "ready_for_strategy_replay": False, "formal_model_changed": False,
        "trade_decision_changed": False, "active_in_trade_decision": False,
        "report_changed": False, "artifacts": artifacts,
    }
    (output / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
