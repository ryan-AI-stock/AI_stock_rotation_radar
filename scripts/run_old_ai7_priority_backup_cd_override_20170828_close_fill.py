from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

try:
    from scripts.run_weekly_ai_diffusion_switch_close_fill import FLAGS, REPO, atomic_csv, atomic_json, atomic_text, now, read_checkpoint, sha256_file
except ModuleNotFoundError:
    from run_weekly_ai_diffusion_switch_close_fill import FLAGS, REPO, atomic_csv, atomic_json, atomic_text, now, read_checkpoint, sha256_file


TASK = "TASK-RADAR-DATA-VNEXT-P1-P2-OLD-AI7-PRIORITY-00631L-BACKUP-CD-OVERRIDE-20170828-EXACT-CLOSE-FILL-002"
CORE_OUTPUT = Path(r"C:\Users\zergv\Documents\Codex\2026-05-30\ep05-chat-ai-stock-backtest-lab\outputs\vnext_p1_p2_old_ai7_priority_00631l_backup_cd_override_contract_20260720")
AUTHORITY = CORE_OUTPUT / "path_independent_close_gap_union.csv"
OUTPUT = REPO / "outputs/radar_vnext_p1_p2_old_ai7_priority_00631l_backup_cd_override_20170828_close_fill_20260720"
TARGET = ("00631L", "2017-08-28")
REUSE = REPO / "outputs/radar_vnext_p1_p2_sleeve_internal_timing_close_fill_20260718/checkpoints/00631L/2017-08.json.gz"


def load_authority(path: Path) -> pd.DataFrame:
    frame = pd.read_csv(path, dtype=str, low_memory=False)[["ticker", "date"]].drop_duplicates()
    frame["ticker"] = frame["ticker"].astype(str).str.strip().str.upper()
    frame["date"] = frame["date"].astype(str).str[:10]
    if frame.to_dict("records") != [{"ticker": TARGET[0], "date": TARGET[1]}]:
        raise RuntimeError(f"authority_scope_changed:{frame.to_dict('records')}")
    return frame


def write_manifest(output: Path, readiness: dict) -> None:
    files = sorted(path for path in output.rglob("*") if path.is_file() and path.name not in {"manifest.json", "checksum_manifest.csv"})
    checks = pd.DataFrame([{"file": str(path.relative_to(output)).replace("\\", "/"), "bytes": path.stat().st_size, "sha256": sha256_file(path)} for path in files])
    atomic_csv(output / "checksum_manifest.csv", checks)
    atomic_json(output / "manifest.json", {"task": TASK, "generated_at": now(), "authority_path": str(AUTHORITY), "authority_sha256": sha256_file(AUTHORITY), "files": checks.to_dict("records"), "readiness": readiness, "future_data_violation_count": 0, **FLAGS})


def run(args: argparse.Namespace) -> dict:
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    load_authority(args.authority)
    item = read_checkpoint(REUSE)
    if item.get("status") != "accepted":
        raise RuntimeError(f"reuse_checkpoint_not_accepted:{REUSE}")
    matched = next((row for row in item.get("rows", []) if row.get("date") == TARGET[1] and row.get("close") is not None), None)
    patch_rows = [] if matched is None else [{"ticker": TARGET[0], "date": TARGET[1], "market": "TWSE", "close": matched["close"], "source_quality": "official_twse_selected_ticker_month_close_only", "adjustment_policy": "official_unadjusted_execution_close_only", "source_url": item.get("source_url", ""), "source_hash": item.get("source_hash", ""), "retrieved_at": item.get("retrieved_at", ""), "source_reuse": "previous_accepted_official_ticker_month_checkpoint", "future_data_violation_count": 0}]
    no_trade_rows = [] if patch_rows else [{"ticker": TARGET[0], "date": TARGET[1], "market": "TWSE", "classification": "official_no_trade", "reason": "accepted_official_ticker_month_response_has_no_exact_trade_row", "source_url": item.get("source_url", ""), "source_hash": item.get("source_hash", ""), "retrieved_at": item.get("retrieved_at", ""), "future_data_violation_count": 0}]
    prefix = "old_ai7_priority_backup_cd_override_20170828_exact_close"
    atomic_csv(output / f"{prefix}_patch.csv", pd.DataFrame(patch_rows))
    atomic_csv(output / f"{prefix}_no_trade.csv", pd.DataFrame(no_trade_rows))
    atomic_csv(output / f"{prefix}_blocked.csv", pd.DataFrame(columns=["ticker", "date", "classification", "reason"]))
    atomic_csv(output / "future_data_audit.csv", pd.DataFrame([{"audit": "exact_authority_close_only", "status": "pass", "future_data_violation_count": 0}, {"audit": "neighbor_last_adjusted_benchmark_substitution", "status": "false", "future_data_violation_count": 0}, {"audit": "performance_calculation", "status": "false", "future_data_violation_count": 0}]))
    readiness = {"task": TASK, "status": "complete_ready_for_core_absorption", "requested_exact_keys": 1, "official_raw_close_ready_rows": len(patch_rows), "official_no_trade_rows": len(no_trade_rows), "blocked_rows": 0, "partition_rows": len(patch_rows) + len(no_trade_rows), "partition_matches_authority": len(patch_rows) + len(no_trade_rows) == 1, "duplicate_exact_keys": 0, "network_routes": 0, "local_accepted_checkpoint_reuse_routes": 1, "network_outside_authority_rows": 0, "non_close_family_download_rows": 0, "ready_for_core_old_ai7_priority_backup_cd_override_20170828_close_absorption": True, "ready_for_experiments": False, "future_data_violation_count": 0, **FLAGS}
    atomic_csv(output / "requested_vs_actual_coverage.csv", pd.DataFrame([{"classification": "requested_exact_keys", "rows": 1}, {"classification": "official_raw_close_ready", "rows": len(patch_rows)}, {"classification": "official_no_trade", "rows": len(no_trade_rows)}, {"classification": "blocked", "rows": 0}]))
    # Keep the readiness name short enough for Windows atomic replacement.
    atomic_json(output / "readiness_for_core.json", readiness)
    atomic_json(output / "progress.json", {**readiness, "updated_at": now()})
    atomic_text(output / "current_step.txt", "status=complete\nresume_step=none\nnext_owner=Core_Data_priority_backup_cd_override_rechain\n")
    atomic_text(output / "final_summary_zh.md", f"# old AI7 priority 00631L backup CD override 20170828 exact close fill\n\n- authority=1；official raw close={len(patch_rows)}；official no-trade={len(no_trade_rows)}；blocked=0。\n- local accepted official checkpoint reuse only；未啟動新網路。\n")
    write_manifest(output, readiness)
    print(json.dumps(readiness, ensure_ascii=False, indent=2))
    return readiness


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--authority", type=Path, default=AUTHORITY)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    run(parser.parse_args())


if __name__ == "__main__":
    main()
