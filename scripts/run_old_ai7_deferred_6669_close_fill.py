from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

try:
    from scripts.run_weekly_ai_diffusion_switch_close_fill import FLAGS, REPO, atomic_csv, atomic_json, atomic_text, now, read_checkpoint, sha256_file
except ModuleNotFoundError:
    from run_weekly_ai_diffusion_switch_close_fill import FLAGS, REPO, atomic_csv, atomic_json, atomic_text, now, read_checkpoint, sha256_file


TASK = "TASK-RADAR-DATA-VNEXT-P1-P2-00631L-OLD-AI7-RELATIVE-MA-SLOPE-SWITCH-DEFERRED-6669-20190416-CLOSE-FILL-001"
CORE_OUTPUT = Path(r"C:\Users\zergv\Documents\Codex\2026-05-30\ep05-chat-ai-stock-backtest-lab\outputs\vnext_p1_p2_00631l_old_ai7_relative_ma_slope_switch_contract_20260719")
AUTHORITY = CORE_OUTPUT / "path_independent_close_gap_union.csv"
REUSE = REPO / "outputs/radar_vnext_p1_p2_ai_diffusion_weekly_switch_close_fill_20260718/checkpoints/6669/2019-04.json.gz"
OUTPUT = REPO / "outputs/radar_vnext_p1_p2_old_ai7_relative_deferred_6669_close_fill_20260719"
TARGET = {"ticker": "6669", "date": "2019-04-16", "role": "sell", "action": "atomic_switch"}


def load_authority(path: Path) -> dict:
    frame = pd.read_csv(path, dtype=str, low_memory=False)
    if len(frame) != 1 or frame.iloc[0]["ticker"] != TARGET["ticker"] or frame.iloc[0]["date"][:10] != TARGET["date"]:
        raise RuntimeError(f"authority_scope_changed:{frame.to_dict('records')}")
    return {**TARGET, "authority_path": str(path), "authority_sha256": sha256_file(path)}


def write_manifest(output: Path, readiness: dict, authority: dict) -> None:
    files = sorted(path for path in output.rglob("*") if path.is_file() and path.name not in {"manifest.json", "checksum_manifest.csv"})
    checks = pd.DataFrame([{"file": str(path.relative_to(output)).replace("\\", "/"), "bytes": path.stat().st_size, "sha256": sha256_file(path)} for path in files])
    atomic_csv(output / "checksum_manifest.csv", checks)
    atomic_json(output / "manifest.json", {"task": TASK, "generated_at": now(), "authority": authority, "files": checks.to_dict("records"), "readiness": readiness, "future_data_violation_count": 0, **FLAGS})


def run(args: argparse.Namespace) -> dict:
    output = args.output.resolve(); output.mkdir(parents=True, exist_ok=True)
    authority = load_authority(args.authority)
    item = read_checkpoint(args.reuse)
    if item.get("status") != "accepted":
        raise RuntimeError("local_official_reuse_checkpoint_not_accepted")
    matched = [row for row in item.get("rows", []) if row.get("date") == TARGET["date"] and row.get("close") is not None]
    patch = pd.DataFrame([{
        **TARGET, "market": "TWSE", "close": matched[0]["close"],
        "source_quality": "official_twse_selected_ticker_month_close_only",
        "adjustment_policy": "official_unadjusted_execution_close_only",
        "source_url": item.get("source_url", ""), "source_hash": item.get("source_hash", ""), "retrieved_at": item.get("retrieved_at", ""),
        "source_reuse": "previous_accepted_official_ticker_month_checkpoint", "future_data_violation_count": 0,
    }] if matched else [])
    no_trade = pd.DataFrame([] if matched else [{
        **TARGET, "market": "TWSE", "classification": "official_no_trade",
        "reason": "accepted_official_ticker_month_response_has_no_exact_trade_row", "source_url": item.get("source_url", ""),
        "source_hash": item.get("source_hash", ""), "retrieved_at": item.get("retrieved_at", ""), "future_data_violation_count": 0,
    }])
    atomic_csv(output / "old_ai7_deferred_6669_exact_close_patch.csv", patch)
    atomic_csv(output / "old_ai7_deferred_6669_exact_close_no_trade.csv", no_trade)
    atomic_csv(output / "old_ai7_deferred_6669_exact_close_blocked.csv", pd.DataFrame(columns=["ticker", "date", "classification", "reason"]))
    atomic_csv(output / "future_data_audit.csv", pd.DataFrame([
        {"audit": "exact_authority_close_only", "status": "pass", "future_data_violation_count": 0},
        {"audit": "neighbor_last_adjusted_benchmark_substitution", "status": "false", "future_data_violation_count": 0},
        {"audit": "performance_calculation", "status": "false", "future_data_violation_count": 0},
    ]))
    readiness = {
        "task": TASK, "status": "complete_ready_for_core_absorption", "requested_exact_keys": 1,
        "official_raw_close_ready_rows": len(patch), "official_no_trade_rows": len(no_trade), "blocked_rows": 0,
        "partition_rows": len(patch) + len(no_trade), "partition_matches_authority": len(patch) + len(no_trade) == 1,
        "network_routes": 0, "local_accepted_checkpoint_reuse_routes": 1, "network_outside_authority_rows": 0,
        "non_close_family_download_rows": 0, "ready_for_core_old_ai7_deferred_6669_close_absorption": True,
        "ready_for_experiments": False, "future_data_violation_count": 0, **FLAGS,
    }
    atomic_csv(output / "requested_vs_actual_coverage.csv", pd.DataFrame([
        {"classification": "requested_exact_keys", "rows": 1}, {"classification": "official_raw_close_ready", "rows": len(patch)},
        {"classification": "official_no_trade", "rows": len(no_trade)}, {"classification": "blocked", "rows": 0},
    ]))
    atomic_json(output / "readiness_for_core_old_ai7_deferred_6669_close_absorption.json", readiness)
    atomic_json(output / "progress.json", {**readiness, "updated_at": now()})
    atomic_text(output / "current_step.txt", "status=complete\nresume_step=none\nnext_owner=Core_Data_old_ai7_final_rechain\n")
    atomic_text(output / "final_summary_zh.md", f"# old AI7 deferred 6669 exact close fill\n\n- authority：6669 / 2019-04-16 sell atomic_switch。\n- official raw close：{len(patch)}。\n- official no-trade：{len(no_trade)}。\n- local accepted official checkpoint reuse only；未啟動新網路。\n")
    write_manifest(output, readiness, authority)
    print(json.dumps(readiness, ensure_ascii=False, indent=2))
    return readiness


def main() -> None:
    parser = argparse.ArgumentParser(); parser.add_argument("--authority", type=Path, default=AUTHORITY); parser.add_argument("--reuse", type=Path, default=REUSE); parser.add_argument("--output", type=Path, default=OUTPUT)
    run(parser.parse_args())


if __name__ == "__main__":
    main()
