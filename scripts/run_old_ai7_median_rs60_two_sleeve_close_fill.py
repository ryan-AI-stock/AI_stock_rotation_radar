from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

try:
    from scripts.run_weekly_ai_diffusion_switch_close_fill import FLAGS, REPO, atomic_csv, atomic_json, atomic_text, now, read_checkpoint, sha256_file
except ModuleNotFoundError:
    from run_weekly_ai_diffusion_switch_close_fill import FLAGS, REPO, atomic_csv, atomic_json, atomic_text, now, read_checkpoint, sha256_file


TASK = "TASK-RADAR-DATA-VNEXT-P1-P2-OLD-AI7-VS-00631L-WEEKLY-MEDIAN-RS60-TWO-SLEEVE-EXACT-CLOSE-FILL-001"
CORE_OUTPUT = Path(r"C:\Users\zergv\Documents\Codex\2026-05-30\ep05-chat-ai-stock-backtest-lab\outputs\vnext_p1_p2_old_ai7_vs_00631l_weekly_median_rs60_two_sleeve_contract_20260719")
AUTHORITY = CORE_OUTPUT / "path_independent_close_gap_union.csv"
OUTPUT = REPO / "outputs/radar_vnext_p1_p2_old_ai7_median_rs60_two_sleeve_close_fill_20260719"
TARGETS = {"2018-11-05", "2023-05-15"}
REUSE = {
    "2018-11": REPO / "outputs/radar_vnext_p1_p2_sleeve_internal_timing_close_fill_20260718/checkpoints/00631L/2018-11.json.gz",
    "2023-05": REPO / "outputs/radar_vnext_p1_p2_sleeve_internal_timing_close_fill_20260718/checkpoints/00631L/2023-05.json.gz",
}


def load_authority(path: Path) -> pd.DataFrame:
    frame = pd.read_csv(path, dtype=str, low_memory=False)[["ticker", "date"]].drop_duplicates()
    frame["ticker"] = frame["ticker"].astype(str).str.strip().str.upper()
    frame["date"] = frame["date"].astype(str).str[:10]
    if len(frame) != 2 or set(frame["ticker"]) != {"00631L"} or set(frame["date"]) != TARGETS:
        raise RuntimeError(f"authority_scope_changed:{frame.to_dict('records')}")
    return frame.sort_values("date").reset_index(drop=True)


def write_manifest(output: Path, readiness: dict) -> None:
    files = sorted(path for path in output.rglob("*") if path.is_file() and path.name not in {"manifest.json", "checksum_manifest.csv"})
    checks = pd.DataFrame([{"file": str(path.relative_to(output)).replace("\\", "/"), "bytes": path.stat().st_size, "sha256": sha256_file(path)} for path in files])
    atomic_csv(output / "checksum_manifest.csv", checks)
    atomic_json(output / "manifest.json", {"task": TASK, "generated_at": now(), "authority_path": str(AUTHORITY), "authority_sha256": sha256_file(AUTHORITY), "files": checks.to_dict("records"), "readiness": readiness, "future_data_violation_count": 0, **FLAGS})


def run(args: argparse.Namespace) -> dict:
    output = args.output.resolve(); output.mkdir(parents=True, exist_ok=True)
    authority = load_authority(args.authority)
    rows, no_trade = [], []
    for month, checkpoint in REUSE.items():
        item = read_checkpoint(checkpoint)
        if item.get("status") != "accepted":
            raise RuntimeError(f"reuse_checkpoint_not_accepted:{checkpoint}")
        dates = set(authority[authority["date"].str.startswith(month)]["date"])
        found = set()
        for raw in item.get("rows", []):
            if raw.get("date") not in dates or raw.get("close") is None:
                continue
            found.add(raw["date"])
            rows.append({"ticker": "00631L", "date": raw["date"], "market": "TWSE", "close": raw["close"], "source_quality": "official_twse_selected_ticker_month_close_only", "adjustment_policy": "official_unadjusted_execution_close_only", "source_url": item.get("source_url", ""), "source_hash": item.get("source_hash", ""), "retrieved_at": item.get("retrieved_at", ""), "source_reuse": "previous_accepted_official_ticker_month_checkpoint", "future_data_violation_count": 0})
        for date in dates - found:
            no_trade.append({"ticker": "00631L", "date": date, "market": "TWSE", "classification": "official_no_trade", "reason": "accepted_official_ticker_month_response_has_no_exact_trade_row", "source_url": item.get("source_url", ""), "source_hash": item.get("source_hash", ""), "retrieved_at": item.get("retrieved_at", ""), "future_data_violation_count": 0})
    patch = pd.DataFrame(rows).drop_duplicates(["ticker", "date"]).sort_values("date")
    no_trade_frame = pd.DataFrame(no_trade)
    atomic_csv(output / "old_ai7_median_rs60_two_sleeve_exact_close_patch.csv", patch)
    atomic_csv(output / "old_ai7_median_rs60_two_sleeve_exact_close_no_trade.csv", no_trade_frame)
    atomic_csv(output / "old_ai7_median_rs60_two_sleeve_exact_close_blocked.csv", pd.DataFrame(columns=["ticker", "date", "classification", "reason"]))
    atomic_csv(output / "future_data_audit.csv", pd.DataFrame([{"audit": "exact_authority_close_only", "status": "pass", "future_data_violation_count": 0}, {"audit": "neighbor_last_adjusted_benchmark_substitution", "status": "false", "future_data_violation_count": 0}, {"audit": "performance_calculation", "status": "false", "future_data_violation_count": 0}]))
    readiness = {"task": TASK, "status": "complete_ready_for_core_absorption", "requested_exact_keys": 2, "official_raw_close_ready_rows": len(patch), "official_no_trade_rows": len(no_trade_frame), "blocked_rows": 0, "partition_rows": len(patch) + len(no_trade_frame), "partition_matches_authority": len(patch) + len(no_trade_frame) == 2, "duplicate_exact_keys": int(patch.duplicated(["ticker", "date"]).sum()), "network_routes": 0, "local_accepted_checkpoint_reuse_routes": 2, "network_outside_authority_rows": 0, "non_close_family_download_rows": 0, "ready_for_core_old_ai7_median_rs60_two_sleeve_close_absorption": True, "ready_for_experiments": False, "future_data_violation_count": 0, **FLAGS}
    atomic_csv(output / "requested_vs_actual_coverage.csv", pd.DataFrame([{"classification": "requested_exact_keys", "rows": 2}, {"classification": "official_raw_close_ready", "rows": len(patch)}, {"classification": "official_no_trade", "rows": len(no_trade_frame)}, {"classification": "blocked", "rows": 0}]))
    atomic_json(output / "readiness_for_core_old_ai7_median_rs60_two_sleeve_close_absorption.json", readiness); atomic_json(output / "progress.json", {**readiness, "updated_at": now()})
    atomic_text(output / "current_step.txt", "status=complete\nresume_step=none\nnext_owner=Core_Data_two_sleeve_final_rechain\n")
    atomic_text(output / "final_summary_zh.md", f"# old AI7 versus 00631L weekly median RS60 two-sleeve exact close fill\n\n- authority=2；official raw close={len(patch)}；official no-trade={len(no_trade_frame)}；blocked=0。\n- local accepted official checkpoint reuse only；未啟動新網路。\n")
    write_manifest(output, readiness); print(json.dumps(readiness, ensure_ascii=False, indent=2)); return readiness


def main() -> None:
    parser = argparse.ArgumentParser(); parser.add_argument("--authority", type=Path, default=AUTHORITY); parser.add_argument("--output", type=Path, default=OUTPUT); run(parser.parse_args())


if __name__ == "__main__": main()
