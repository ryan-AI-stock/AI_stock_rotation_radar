from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

try:
    from scripts.run_weekly_ai_diffusion_switch_close_fill import FLAGS, REPO, atomic_csv, atomic_json, atomic_text, now, read_checkpoint, request_month, sha256_file, write_checkpoint
except ModuleNotFoundError:
    from run_weekly_ai_diffusion_switch_close_fill import FLAGS, REPO, atomic_csv, atomic_json, atomic_text, now, read_checkpoint, request_month, sha256_file, write_checkpoint


TASK = "TASK-RADAR-DATA-VNEXT-P1-P2-STRICT-BEAR-CASH-INCREMENTAL-CLOSE-FILL-001"
CORE_OUTPUT = Path(r"C:\Users\zergv\Documents\Codex\2026-05-30\ep05-chat-ai-stock-backtest-lab\outputs\vnext_p1_p2_strict_ai_diffusion_weekly_switch_fixed_bear_cash_extension_contract_20260718")
AUTHORITY = CORE_OUTPUT / "strict_bear_cash_bounded_official_raw_execution_gap_ledger.csv"
OUTPUT = REPO / "outputs/radar_vnext_p1_p2_strict_bear_cash_final_union_close_fill_20260718"
REUSE_ROOT = REPO / "outputs/radar_vnext_p1_p2_ai_diffusion_weekly_switch_close_fill_20260718/checkpoints/00631L"


def load_authority(path: Path) -> pd.DataFrame:
    frame = pd.read_csv(path, dtype=str, low_memory=False)[["ticker", "date"]].drop_duplicates()
    frame["ticker"] = frame["ticker"].astype(str).str.strip().str.upper(); frame["date"] = frame["date"].astype(str).str[:10]
    frame = frame.sort_values(["ticker", "date"]).reset_index(drop=True)
    if len(frame) != 9 or not frame["ticker"].eq("00631L").all(): raise RuntimeError(f"authority_scope_changed:{frame.to_dict('records')}")
    return frame


def exact_rows(item: dict, dates: set[str], reuse: str) -> list[dict]:
    return [{"ticker": "00631L", "date": str(row.get("date", ""))[:10], "market": "TWSE", "close": row["close"], "source_quality": "official_twse_selected_ticker_month_close_only", "adjustment_policy": "official_unadjusted_execution_close_only", "source_url": item.get("source_url", ""), "source_hash": item.get("source_hash", ""), "retrieved_at": item.get("retrieved_at", ""), "source_reuse": reuse, "future_data_violation_count": 0} for row in item.get("rows", []) if str(row.get("date", ""))[:10] in dates and row.get("close") is not None]


def manifest(output: Path, readiness: dict) -> None:
    excluded = {"manifest.json", "checksum_manifest.csv"}; files = sorted(path for path in output.rglob("*") if path.is_file() and path.name not in excluded)
    checks = pd.DataFrame([{"file": str(path.relative_to(output)).replace("\\", "/"), "bytes": path.stat().st_size, "sha256": sha256_file(path)} for path in files])
    atomic_csv(output / "checksum_manifest.csv", checks); atomic_json(output / "manifest.json", {"task": TASK, "generated_at": now(), "authority_path": str(AUTHORITY), "authority_sha256": sha256_file(AUTHORITY), "network_scope": "current Core authority only; 00631L exact dates; TWSE selected ticker-month close-only", "readiness": readiness, "files": checks.to_dict("records"), "future_data_violation_count": 0, **FLAGS})


def run(args: argparse.Namespace) -> dict:
    output = args.output.resolve(); output.mkdir(parents=True, exist_ok=True); authority = load_authority(args.authority); dates = set(authority.date)
    rows = []
    for month in sorted({date[:7] for date in dates}):
        reuse = REUSE_ROOT / f"{month}.json.gz"; checkpoint = output / "checkpoints/00631L" / f"{month}.json.gz"
        if checkpoint.exists() and read_checkpoint(checkpoint).get("status") == "accepted": item = read_checkpoint(checkpoint); label = "resumed_exact_authority_checkpoint"
        elif reuse.exists(): item = read_checkpoint(reuse); label = "previous_accepted_ticker_month_checkpoint"
        else: item = request_month("00631L", month); item["task"] = TASK; write_checkpoint(checkpoint, item); label = "network_exact_authority_month"
        rows.extend(exact_rows(item, dates, label))
    patch = pd.DataFrame(rows).drop_duplicates(["ticker", "date"], keep="first").sort_values("date").merge(authority, on=["ticker", "date"], how="inner")
    ready = set(patch.date); blocked_rows = []
    for date_s in authority.date:
        if date_s in ready: continue
        blocked_rows.append({"ticker": "00631L", "date": date_s, "market": "TWSE", "classification": "source_gap", "reason": "exact_date_not_found_after_authorized_month_route", "source_url": "", "source_hash": "", "retrieved_at": "", "future_data_violation_count": 0})
    blocked = pd.DataFrame(blocked_rows).reindex(columns=["ticker", "date", "market", "classification", "reason", "source_url", "source_hash", "retrieved_at", "future_data_violation_count"])
    atomic_csv(output / "strict_bear_cash_incremental_exact_close_patch.csv", patch); atomic_csv(output / "strict_bear_cash_incremental_exact_close_blocked.csv", blocked)
    atomic_csv(output / "requested_vs_actual_coverage.csv", pd.DataFrame([{"classification": "requested_exact_keys", "rows": len(authority), "future_data_violation_count": 0}, {"classification": "official_raw_close_ready", "rows": len(patch), "future_data_violation_count": 0}, {"classification": "blocked", "rows": len(blocked), "future_data_violation_count": 0}]))
    atomic_csv(output / "future_data_audit.csv", pd.DataFrame([{"audit": "current_authority_exact_close_only", "status": "pass", "future_data_violation_count": 0}, {"audit": "neighbor_last_benchmark_substitution", "status": "false", "future_data_violation_count": 0}, {"audit": "performance_calculation", "status": "false", "future_data_violation_count": 0}]))
    readiness = {"task": TASK, "status": "complete_ready_for_core_absorption" if len(patch) == len(authority) else "complete_with_explicit_source_blockers", "requested_exact_keys": len(authority), "official_raw_close_ready_rows": len(patch), "blocked_rows": len(blocked), "partition_rows": len(patch) + len(blocked), "partition_matches_authority": len(patch) + len(blocked) == len(authority), "duplicate_exact_keys": int(patch.duplicated(["ticker", "date"]).sum()), "network_routes": sum(row["source_reuse"] == "network_exact_authority_month" for row in rows), "network_outside_authority_rows": 0, "non_close_family_download_rows": 0, "ready_for_core_strict_bear_cash_incremental_close_absorption": len(patch) == len(authority), "ready_for_experiments": False, "data_readiness_blocked_only": bool(len(blocked)), "may_be_used_to_reject_strategy": False, "future_data_violation_count": 0, **FLAGS}
    atomic_json(output / "readiness_for_core_strict_bear_cash_incremental_close_absorption.json", readiness); atomic_json(output / "progress.json", {**readiness, "updated_at": now()}); atomic_text(output / "current_step.txt", "status=complete\nresume_step=none\nnext_owner=Core_Data_bear_cash_rechain\n"); atomic_text(output / "final_summary_zh.md", f"# strict bear-cash incremental exact close fill\n\n- authority：{len(authority)} exact dates。\n- official raw close ready：{len(patch)}。\n- blocked：{len(blocked)}。\n- 僅處理 official raw close；未計績效。\n"); manifest(output, readiness); print(json.dumps(readiness, ensure_ascii=False, indent=2)); return readiness


def main() -> None:
    parser = argparse.ArgumentParser(); parser.add_argument("--authority", type=Path, default=AUTHORITY); parser.add_argument("--output", type=Path, default=OUTPUT); run(parser.parse_args())


if __name__ == "__main__": main()
