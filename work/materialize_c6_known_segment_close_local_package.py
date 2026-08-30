"""Materialize Core's known C6 segment from local official raw-cache reuse only."""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

import pandas as pd


CORE = Path(r"C:\Users\zergv\Documents\Codex\2026-07-06\backtest-lab-core-production-grade-contract")
STRATEGY = Path(r"C:\Users\zergv\Documents\Codex\2026-07-06\strategy-center-core-experiments-research-materials")
PRECHECK = CORE / "work" / "c6_forward_replay_preflight_20260830"
SNAPSHOT = STRATEGY / "outputs" / "ai_pool_c_snapshot_20260826_20260828"
OUT = Path("outputs/radar_c6_forward_known_segment_official_close_local_partition_20260830")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_csv(path: Path, frame: pd.DataFrame, columns: list[str]) -> None:
    frame.reindex(columns=columns).to_csv(path, index=False, encoding="utf-8-sig", quoting=csv.QUOTE_MINIMAL)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    authority_path = PRECHECK / "known_segment_official_close_requirement_union.csv"
    pit_gap_path = PRECHECK / "forward_pit_gap_ledger.csv"
    cache_path = SNAPSHOT / "source" / "official_daily_cache" / "official_recent_full_market.csv.gz"
    gate_path = SNAPSHOT / "candidate_gate_rows.csv.gz"
    selected_market_path = SNAPSHOT / "official_market_rows.csv.gz"

    authority = pd.read_csv(authority_path, dtype={"ticker": str})
    authority["ticker"] = authority["ticker"].str.zfill(4)
    authority["date"] = authority["date"].astype(str)
    cache = pd.read_csv(cache_path, dtype={"ticker": str}, low_memory=False)
    cache["ticker"] = cache["ticker"].str.zfill(4)
    cache["date"] = cache["date"].astype(str)
    cache = cache.drop_duplicates(["ticker", "date"], keep="last")
    joined = authority.merge(cache, how="left", on=["ticker", "date"], suffixes=("", "_cache"), indicator=True)
    accepted = joined.loc[joined["_merge"].eq("both") & joined["close"].notna()].copy()
    accepted["status"] = "accepted_exact_official_raw_close"
    accepted["raw_close"] = accepted["close"]
    accepted["source_quality"] = "official_raw_market_bulk_local_reuse"
    accepted["classification_reason"] = "exact_ticker_date_found_in_persisted_official_market_cache"
    accepted["availability_policy"] = "official_market_close_on_required_execution_or_mark_date"
    accepted["future_data_violation"] = False
    blocked = joined.loc[~joined.index.isin(accepted.index), ["ticker", "date", "role", "action", "signal_date"]].copy()
    if not blocked.empty:
        blocked["status"] = "source_blocked"
        blocked["classification_reason"] = "no_exact_row_in_local_official_cache; network_not_authorized_for_known_segment"

    accepted_cols = [
        "ticker", "date", "role", "action", "signal_date", "status", "raw_close", "market", "name",
        "source_url", "source_hash", "retrieved_at_utc", "source_quality", "availability_policy",
        "classification_reason", "future_data_violation",
    ]
    blocked_cols = ["ticker", "date", "role", "action", "signal_date", "status", "classification_reason"]
    write_csv(OUT / "c6_known_segment_official_raw_close_accepted_rows.csv", accepted, accepted_cols)
    write_csv(OUT / "c6_known_segment_official_raw_close_official_no_trade.csv", pd.DataFrame(), accepted_cols)
    write_csv(OUT / "c6_known_segment_official_raw_close_blocked_rows.csv", blocked, blocked_cols)
    coverage = authority.copy()
    coverage["partition"] = "accepted_exact_official_raw_close"
    coverage.loc[~coverage.index.isin(accepted.index), "partition"] = "source_blocked"
    write_csv(
        OUT / "c6_known_segment_official_raw_close_coverage_audit.csv",
        coverage,
        ["ticker", "date", "role", "action", "signal_date", "authority_status", "partition"],
    )
    future_audit = accepted[["ticker", "date", "role", "action", "signal_date", "source_url", "source_hash"]].copy()
    future_audit["audit_result"] = "pass_exact_required_date_only"
    future_audit["future_data_violation"] = False
    write_csv(
        OUT / "c6_known_segment_official_raw_close_future_data_audit.csv",
        future_audit,
        ["ticker", "date", "role", "action", "signal_date", "source_url", "source_hash", "audit_result", "future_data_violation"],
    )

    gaps = pd.read_csv(pit_gap_path)
    gate = pd.read_csv(gate_path, usecols=["signal_date"], low_memory=False)
    selected_market = pd.read_csv(selected_market_path, usecols=["date"], low_memory=False)
    cache_dates = set(cache["date"])
    gate_dates = set(gate["signal_date"].astype(str))
    selected_market_dates = set(selected_market["date"].astype(str))
    pit_rows: list[dict] = []
    for row in gaps.itertuples(index=False):
        signal_date = str(row.signal_date)
        pit_rows.append({
            "signal_date": signal_date,
            "status": "source_blocked_for_complete_forward_PIT_action_state",
            "missing_fields": row.missing_fields,
            "candidate_gate_rows_present": signal_date in gate_dates,
            "selected_market_rows_present": signal_date in selected_market_dates,
            "official_raw_market_cache_present": signal_date in cache_dates,
            "classification_reason": (
                "ranking_top3_and_partial_gate_source_do_not_prove_full_candidate_completeness_or_active_slot_exit_state; "
                "do_not_infer_empty_candidate_or_execution"
            ),
            "network_authority": False,
            "future_data_violation": False,
        })
    pit = pd.DataFrame(pit_rows)
    pit_cols = [
        "signal_date", "status", "missing_fields", "candidate_gate_rows_present", "selected_market_rows_present",
        "official_raw_market_cache_present", "classification_reason", "network_authority", "future_data_violation",
    ]
    write_csv(OUT / "c6_forward_pit_local_source_blocker_audit.csv", pit, pit_cols)

    source_files = [authority_path, pit_gap_path, cache_path, gate_path, selected_market_path]
    manifest_rows = [{"path": str(path), "sha256": sha256(path), "role": role} for path, role in zip(source_files, [
        "core_exact_known_segment_authority", "core_forward_pit_gap_authority", "official_raw_market_cache",
        "candidate_gate_partial_source", "selected_market_partial_source",
    ])]
    manifest = pd.DataFrame(manifest_rows)
    write_csv(OUT / "source_manifest.csv", manifest, ["path", "sha256", "role"])

    artifacts = [
        "c6_known_segment_official_raw_close_accepted_rows.csv",
        "c6_known_segment_official_raw_close_official_no_trade.csv",
        "c6_known_segment_official_raw_close_blocked_rows.csv",
        "c6_known_segment_official_raw_close_coverage_audit.csv",
        "c6_known_segment_official_raw_close_future_data_audit.csv",
        "c6_forward_pit_local_source_blocker_audit.csv",
        "source_manifest.csv",
    ]
    checksums = pd.DataFrame([
        {"artifact": name, "sha256": sha256(OUT / name)} for name in artifacts
    ])
    write_csv(OUT / "checksum_manifest.csv", checksums, ["artifact", "sha256"])
    readiness = {
        "task": "C6_known_segment_official_close_local_partition",
        "network_calls": 0,
        "known_segment_authority_keys": int(len(authority)),
        "accepted_exact_official_raw_close_rows": int(len(accepted)),
        "official_no_trade_rows": 0,
        "source_blocked_rows": int(len(blocked)),
        "ready_for_core_known_segment_official_close_absorption": len(blocked) == 0,
        "forward_pit_gap_dates": int(len(gaps)),
        "complete_forward_whole_share_replay_ready": False,
        "complete_forward_blocker": "2026-08-13_to_2026-08-28_need_full_C6_PIT_action_state_not_just_top3_ranking_or_raw_close",
        "future_data_violation_count": 0,
        "formal_model_changed": False,
        "trade_decision_changed": False,
        "active_in_trade_decision": False,
        "report_changed": False,
        "not_live_rule": True,
    }
    (OUT / "readiness_for_core_c6_forward_known_segment_close_absorption.json").write_text(
        json.dumps(readiness, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (OUT / "manifest.json").write_text(
        json.dumps({
            "task": readiness["task"],
            "source_manifest": "source_manifest.csv",
            "checksum_manifest": "checksum_manifest.csv",
            "accepted_rows": int(len(accepted)),
            "official_no_trade_rows": 0,
            "source_blocked_rows": int(len(blocked)),
            "forward_pit_blocker_dates": int(len(gaps)),
            "network_calls": 0,
            "future_data_violation_count": 0,
        }, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (OUT / "current_step.txt").write_text(
        "complete_local_known_segment_close_partition; await_core_deduplicated_full_forward_price_event_authority\n",
        encoding="utf-8",
    )
    (OUT / "final_summary_zh.md").write_text(
        "# C6 known segment local close partition\n\n"
        f"- 12 exact authority rows: {len(accepted)} accepted official raw close, 0 official no-trade, {len(blocked)} blocked.\n"
        "- Network calls: 0; all accepted rows reuse persisted TWSE/TPEx official market cache.\n"
        f"- Forward PIT dates 2026-08-13..28: {len(gaps)} retained as source blockers for complete action-state materialization.\n"
        "- This package does not make the whole-share forward replay ready.\n",
        encoding="utf-8",
    )
    print(json.dumps(readiness, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
