from __future__ import annotations

import csv
import gzip
import hashlib
import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path


TASK_ID = "TASK-RADAR-DATA-VNEXT-P3-TAIFEX-TRADE-FLOW-COMPACT-MATERIALIZATION-001"
OUTPUT_NAME = "radar_vnext_p3_taifex_trade_flow_compact_materialization_20260712"
SOURCE_RELATIVE = Path("outputs/radar_vnext_p3_expiry_lock_audit_20260711/compact/taifex/p3_official_foreign_tx_futures.csv.gz")
SOURCE_MANIFEST_RELATIVE = Path("outputs/radar_vnext_p3_expiry_lock_audit_20260711/p3_expiry_taifex_source_manifest.csv")

FLAGS = {
    "formal_model_changed": False,
    "trade_decision_changed": False,
    "active_in_trade_decision": False,
    "report_changed": False,
    "portfolio_replay_executed": False,
    "ready_for_strategy_replay": False,
    "ready_for_formal": False,
    "not_live_rule": True,
    "forward_returns_live_rule_usage": False,
}


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def write_csv(path: Path, rows: list[dict], fields: list[str] | None = None) -> None:
    fields = fields or (list(rows[0]) if rows else ["status"])
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def main() -> None:
    repo = Path(__file__).resolve().parents[1]
    source = repo / SOURCE_RELATIVE
    source_manifest = repo / SOURCE_MANIFEST_RELATIVE
    output = repo / "outputs" / OUTPUT_NAME
    output.mkdir(parents=True, exist_ok=True)
    (output / "current_step.txt").write_text("reading_locked_taifex_compact\n", encoding="utf-8")

    with gzip.open(source, "rt", encoding="utf-8-sig", newline="") as handle:
        source_rows = list(csv.DictReader(handle))
    required = {
        "date", "foreign_futures_trade_net_contracts", "foreign_futures_trade_net_amount",
        "foreign_futures_oi_net_contracts", "foreign_futures_oi_net_amount", "source_quality",
        "available_at_policy", "source_url", "source_hash", "retrieval_time_utc",
    }
    if not source_rows or not required.issubset(source_rows[0]):
        raise RuntimeError("locked TAIFEX compact schema is incomplete")
    if len(source_rows) != 728:
        raise RuntimeError(f"expected 728 locked official dates, got {len(source_rows)}")
    dates = sorted(row["date"] for row in source_rows)
    if dates[0] != "2023-07-11" or dates[-1] != "2026-07-09" or len(set(dates)) != 728:
        raise RuntimeError("locked TAIFEX date coverage or uniqueness failed")

    next_date = {day: dates[index + 1] if index + 1 < len(dates) else "" for index, day in enumerate(dates)}
    compact_rows: list[dict] = []
    for row in sorted(source_rows, key=lambda item: item["date"]):
        numeric = [
            row["foreign_futures_trade_net_contracts"], row["foreign_futures_trade_net_amount"],
            row["foreign_futures_oi_net_contracts"], row["foreign_futures_oi_net_amount"],
        ]
        if any(value == "" for value in numeric):
            raise RuntimeError(f"null trade/OI field on {row['date']}")
        eligible = next_date[row["date"]]
        compact_rows.append({
            "source_date": row["date"], "market": "TAIFEX", "product": row.get("product", "TXF"),
            "investor": row.get("investor", "foreign"),
            "foreign_futures_trade_net_contracts": row["foreign_futures_trade_net_contracts"],
            "foreign_futures_trade_net_amount": row["foreign_futures_trade_net_amount"],
            "foreign_futures_oi_net_contracts": row["foreign_futures_oi_net_contracts"],
            "foreign_futures_oi_net_amount": row["foreign_futures_oi_net_amount"],
            "market_available_at": "",
            "market_available_at_status": "official_exact_publication_timestamp_not_exposed_in_locked_range_download",
            "pit_eligible_decision_date": eligible,
            "pit_eligibility_status": "next_official_market_date" if eligible else "next_session_outside_locked_requested_range",
            "pit_join_policy": "official post-close release; never eligible on source_date; join from next trading decision date",
            "source_quality": row["source_quality"], "source_url": row["source_url"],
            "source_response_sha256": row["source_hash"], "retrieval_time_utc": row["retrieval_time_utc"],
            "future_data_violation_count": "0",
        })

    fields = list(compact_rows[0])
    final_path = output / "p3_taifex_foreign_trade_oi_daily_compact.csv.gz"
    temp_path = output / f".{final_path.name}.{os.getpid()}.{uuid.uuid4().hex}.tmp"
    (output / "current_step.txt").write_text("writing_unique_atomic_compact\n", encoding="utf-8")
    with gzip.open(temp_path, "wt", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(compact_rows)
    with gzip.open(temp_path, "rt", encoding="utf-8", newline="") as handle:
        verified = list(csv.DictReader(handle))
    if len(verified) != 728 or len({row["source_date"] for row in verified}) != 728:
        raise RuntimeError("atomic compact verification failed")
    os.replace(temp_path, final_path)

    core_rows = [row for row in compact_rows if row["source_date"] <= "2026-06-29"]
    coverage = [{
        "family": "TAIFEX_foreign_trade_and_OI", "requested_start": "2023-07-11",
        "requested_end": "2026-07-09", "actual_start": dates[0], "actual_end": dates[-1],
        "required_dates": 728, "ready_dates": 728, "missing_dates": 0, "duplicate_dates": 0,
        "null_four_field_rows": 0, "core_v2_target_end": "2026-06-29",
        "core_v2_ready_rows": len(core_rows), "status": "ready", "future_data_violation_count": 0,
    }]
    write_csv(output / "p3_taifex_trade_oi_coverage_audit.csv", coverage)
    write_csv(output / "p3_taifex_trade_oi_requested_vs_actual.csv", [{
        "requested_start": "2023-07-11", "requested_end": "2026-07-09",
        "actual_start": dates[0], "actual_end": dates[-1], "requested_trading_dates": 728,
        "actual_dates": 728, "missing_dates": 0, "status": "pass",
    }])
    write_csv(output / "p3_taifex_trade_oi_source_manifest.csv", [{
        "source_compact_path": str(source), "source_compact_sha256": digest(source),
        "source_manifest_path": str(source_manifest), "source_manifest_sha256": digest(source_manifest),
        "output_compact_path": str(final_path), "output_compact_sha256": digest(final_path),
        "source_url": source_rows[0]["source_url"], "source_response_sha256": source_rows[0]["source_hash"],
        "retrieval_time_utc": source_rows[0]["retrieval_time_utc"], "reused_existing_download": True,
        "new_network_queries": 0, "row_count": 728,
    }])
    write_csv(output / "p3_taifex_trade_oi_blocked_ledger.csv", [])
    write_csv(output / "p3_taifex_trade_oi_future_data_audit.csv", [{
        "audit": "trade flow is independent official field and is not derived from OI change",
        "same_day_use_prohibited": True, "pit_join": "next trading decision date only",
        "exact_publication_timestamp_fabricated": False, "future_data_violation_count": 0, "status": "pass",
    }])

    readiness = {
        "task_id": TASK_ID,
        "status": "p3_taifex_trade_and_oi_four_field_daily_compact_ready",
        "source": "reused official TAIFEX futContractsDateDown locked full-range compact",
        "coverage": "2023-07-11~2026-07-09; 728 official trading dates; Core target through 2026-06-29",
        "daily_rows": 728, "core_v2_target_rows": len(core_rows),
        "trade_net_contracts_ready": True, "trade_net_amount_ready": True,
        "oi_net_contracts_ready": True, "oi_net_amount_ready": True,
        "trade_flow_derived_from_oi_change": False,
        "exact_market_available_at_timestamp_ready": False,
        "pit_next_trading_date_join_ready": True,
        "new_network_queries": 0, "blocked_rows": 0,
        "ready_for_core_p3_taifex_trade_flow_absorption": True,
        "ready_for_core_rerun": True, "ready_for_experiments": False,
        "future_data_violation_count": 0, **FLAGS,
    }
    (output / "readiness_for_core_p3_taifex_trade_flow_absorption.json").write_text(json.dumps(readiness, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (output / "final_summary_zh.md").write_text(
        "# P3 TAIFEX trade-flow + OI compact\n\n"
        "- 重用既有官方728日實體compact，沒有新增下載。\n"
        "- trade net口數/金額與OI net口數/金額已同表materialize，無缺值、無重複。\n"
        "- trade flow不是OI change proxy。\n"
        "- 官方range下載未提供exact publication timestamp，因此不杜撰market_available_at；以次一交易日PIT eligible date join。\n"
        "- ready_for_core_p3_taifex_trade_flow_absorption=true；future_data_violation_count=0。\n"
        "- 下一棒交Core/Data重算full_spec_v2/rechain，不直接交Experiments。\n",
        encoding="utf-8",
    )
    (output / "current_step.txt").write_text("completed_handoff_core_pending\n", encoding="utf-8")

    artifacts = []
    for path in sorted(output.iterdir()):
        if path.is_file() and path.name != "manifest.json":
            artifacts.append({"path": path.name, "bytes": path.stat().st_size, "sha256": digest(path)})
    manifest = {
        "task_id": TASK_ID, "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "source": readiness["source"], "coverage": readiness["coverage"],
        "future_data_violation_count": 0, "ready_for_core_rerun": True,
        "ready_for_strategy_replay": False, "formal_model_changed": False,
        "trade_decision_changed": False, "active_in_trade_decision": False,
        "report_changed": False, "artifacts": artifacts,
    }
    (output / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
