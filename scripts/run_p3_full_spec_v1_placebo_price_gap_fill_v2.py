from __future__ import annotations

import csv
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from run_p3_placebo_tradability_termination_gap_fill import FLAGS, fetch_month, sha256_file, write_csv


TASK_ID = "TASK-RADAR-DATA-VNEXT-P3-PHASE-B-FULL-SPEC-V1-PLACEBO-PRICE-GAP-FILL-002"
OUTPUT_NAME = "radar_vnext_p3_phase_b_full_spec_v1_placebo_price_gap_fill_20260712"
CORE_AUDIT = Path("C:/Users/zergv/Documents/Codex/2026-05-30/ep05-chat-ai-stock-backtest-lab/outputs/vnext_p3_layer5_phase_b_complete_paths_20260712/p3_layer5_phase_b_all_scenario_tradability_horizon_audit.csv")

MARKETS = {
    "1717": "TWSE", "2301": "TWSE", "3047": "TWSE", "3673": "TWSE",
    "4906": "TWSE", "7750": "TWSE", "8039": "TWSE", "8150": "TWSE",
    "4123": "TPEx", "4162": "TPEx", "4563": "TPEx", "4749": "TPEx",
    "5289": "TPEx", "6290": "TPEx", "8096": "TPEx",
}

EXPECTED = {
    ("4906", "4563", "2024-09-24"), ("1717", "2301", "2026-05-20"),
    ("4162", "", "2025-03-11"), ("3047", "8096", "2024-09-10"),
    ("3673", "8150", "2026-05-12"), ("7750", "5289", "2026-06-10"),
    ("4123", "8039", "2026-03-11"), ("4749", "6290", "2026-05-12"),
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
        raise RuntimeError(f"Core blocker scope changed; expected 8 exact rows, got {sorted(actual)}")

    query_keys: set[tuple[str, str, str]] = set()
    for row in blocked:
        for ticker in (row["intended_prior_target"], row["intended_new_target"]):
            if ticker:
                query_keys.add((ticker, MARKETS[ticker], row["requested_execution_date"][:7]))

    prices: list[dict] = []
    manifests: list[dict] = []
    exact: dict[tuple[str, str], dict] = {}
    (output / "current_step.txt").write_text(f"fetching_0_of_{len(query_keys)}\n", encoding="utf-8")
    for index, (ticker, market, month) in enumerate(sorted(query_keys), start=1):
        rows, manifest = fetch_month(ticker, market, month, raw_dir)
        prices.extend(rows)
        manifests.append(manifest)
        for row in rows:
            exact[(ticker, row["date"])] = row
        (output / "current_step.txt").write_text(f"fetching_{index}_of_{len(query_keys)}\n", encoding="utf-8")

    patch: list[dict] = []
    impacts: list[dict] = []
    blocked_rows: list[dict] = []
    event_rows: list[dict] = []
    for row in blocked:
        prior = row["intended_prior_target"]
        new = row["intended_new_target"]
        execution = row["requested_execution_date"]
        prior_ready = (prior, execution) in exact
        new_ready = not new or (new, execution) in exact
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
                if not ticker:
                    continue
                patch.append({
                    "scenario": row["scenario"], "decision_date": row["decision_date"],
                    "requested_execution_date": execution, "actual_execution_date": execution,
                    "role": role, **exact[(ticker, execution)],
                })
            event_rows.append({
                "scenario": row["scenario"], "ticker": prior,
                "event_type": "false_positive_termination_inference",
                "effective_termination_date": "", "holder_treatment": "not_applicable_official_trading_continues",
                "evidence": f"official exact execution-date OHLC exists on {execution}",
                "source_url": exact[(prior, execution)]["source_url"],
                "raw_sha256": exact[(prior, execution)]["raw_sha256"],
                "future_data_violation_count": 0,
            })
        else:
            blocked_rows.append({
                **impact,
                "blocked_reason": "official exact requested execution-date price absent for prior or new target",
                "attempted_source": "TWSE_RWD_STOCK_DAY_or_TPEX_TRADING_STOCK",
                "no_last_price_or_neighbor_substitution": True,
            })

    price_fields = [
        "scenario", "decision_date", "requested_execution_date", "actual_execution_date", "role",
        "date", "ticker", "market", "open", "high", "low", "close", "volume", "turnover_value",
        "source_url", "source_route", "source_quality", "adjustment_policy", "raw_sha256",
        "raw_cache_path", "retrieval_time_utc", "future_data_violation_count",
    ]
    write_csv(output / "full_spec_v1_placebo_official_ohlcv_patch_rows.csv", patch, price_fields)
    write_csv(output / "full_spec_v1_placebo_official_unadjusted_ohlcv_rows.csv", prices, price_fields[5:])
    write_csv(output / "full_spec_v1_placebo_price_source_manifest.csv", manifests)
    write_csv(output / "full_spec_v1_placebo_path_impact_ledger.csv", impacts)
    write_csv(output / "full_spec_v1_placebo_false_termination_event_ledger.csv", event_rows)
    write_csv(output / "full_spec_v1_placebo_price_blocked_ledger.csv", blocked_rows)
    write_csv(output / "full_spec_v1_placebo_future_data_audit.csv", [{
        "audit": "exact requested execution date only; no last-price carry, neighbour substitution, benchmark reconstruction, or current-status backfill",
        "status": "pass", "future_data_violation_count": 0,
    }])

    ready = not blocked_rows and len(impacts) == 8
    readiness = {
        "task_id": TASK_ID,
        "status": "full_spec_v1_placebo_exact_execution_price_patch_ready" if ready else "full_spec_v1_placebo_price_patch_partial_blocked",
        "source": "official selected ticker-month TWSE STOCK_DAY / TPEx tradingStock",
        "coverage": "Core full_spec_v1 incremental blocked episodes only; 8 episodes / 15 tickers",
        "input_gap_episodes": len(blocked), "official_patch_rows": len(patch),
        "resolved_episodes": sum(row["exact_same_day_transition_ready"] for row in impacts),
        "blocked_episodes": len(blocked_rows), "new_download_query_count": len(query_keys),
        "ready_for_core_p3_phase_b_full_spec_v1_placebo_price_absorption": ready,
        "ready_for_core_rerun": ready, "ready_for_experiments": False,
        "future_data_violation_count": 0, **FLAGS,
    }
    (output / "readiness_for_core_p3_full_spec_v1_placebo_price_absorption.json").write_text(json.dumps(readiness, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    summary = f"""# P3 Phase B full_spec_v1 placebo price gap fill 002

- incremental episodes：{len(blocked)}。
- exact requested-date resolved：{readiness['resolved_episodes']}。
- official patch rows：{len(patch)}。
- blocked episodes：{len(blocked_rows)}。
- 這批若解開，代表active-scope compact漏列，不是終止交易；未使用最後價或鄰日替代。
- ready_for_core_p3_phase_b_full_spec_v1_placebo_price_absorption={str(ready).lower()}。
- future_data_violation_count=0。

下一棒：交 Core/Data absorption/rechain，不直接交 Experiments、不計績效。
"""
    (output / "final_summary_zh.md").write_text(summary, encoding="utf-8")
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
