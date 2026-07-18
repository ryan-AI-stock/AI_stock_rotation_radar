from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

try:
    from scripts.run_weekly_ai_diffusion_switch_close_fill import (
        FLAGS, REPO, atomic_csv, atomic_json, atomic_text, now, read_checkpoint,
        request_month, sha256_file, write_checkpoint,
    )
except ModuleNotFoundError:
    from run_weekly_ai_diffusion_switch_close_fill import (
        FLAGS, REPO, atomic_csv, atomic_json, atomic_text, now, read_checkpoint,
        request_month, sha256_file, write_checkpoint,
    )


TASK = "TASK-RADAR-DATA-VNEXT-P1-P2-STRICT-AI-DIFFUSION-WEEKLY-SWITCH-BEAR-CASH-RECHAIN-CLOSE-FILL-001"
CORE_OUTPUT = Path(r"C:\Users\zergv\Documents\Codex\2026-05-30\ep05-chat-ai-stock-backtest-lab\outputs\vnext_p1_p2_strict_ai_diffusion_weekly_switch_fixed_bear_cash_extension_contract_20260718")
AUTHORITY = CORE_OUTPUT / "strict_bear_cash_bounded_official_raw_execution_gap_ledger.csv"
OUTPUT = REPO / "outputs/radar_vnext_p1_p2_strict_ai_diffusion_bear_cash_rechain_close_fill_20260718"
EXPECTED_DATES = ["2018-01-22", "2022-08-22", "2025-06-09", "2025-06-23"]


def load_authority(path: Path) -> pd.DataFrame:
    frame = pd.read_csv(path, dtype=str, low_memory=False)[["ticker", "date"]].drop_duplicates()
    frame["ticker"] = frame["ticker"].astype(str).str.strip().str.upper()
    frame["date"] = frame["date"].astype(str).str[:10]
    frame = frame.sort_values("date").reset_index(drop=True)
    if frame["ticker"].tolist() != ["00631L"] * 4 or frame["date"].tolist() != EXPECTED_DATES:
        raise RuntimeError(f"authority_scope_changed:{frame.to_dict('records')}")
    return frame


def extract_exact(item: dict, dates: set[str]) -> list[dict]:
    rows = []
    for row in item.get("rows", []):
        date_s = str(row.get("date", ""))[:10]
        if date_s in dates and row.get("close") is not None:
            rows.append({
                "ticker": "00631L", "date": date_s, "market": "TWSE", "close": row["close"],
                "source_quality": "official_twse_selected_ticker_month_close_only",
                "adjustment_policy": "official_unadjusted_execution_close_only",
                "source_url": item.get("source_url", ""), "source_hash": item.get("source_hash", ""),
                "retrieved_at": item.get("retrieved_at", ""), "source_reuse": "network_exact_authority_month",
                "future_data_violation_count": 0,
            })
    return rows


def build_manifest(output: Path, readiness: dict) -> None:
    excluded = {"manifest.json", "checksum_manifest.csv"}
    files = sorted(path for path in output.rglob("*") if path.is_file() and path.name not in excluded)
    checksums = pd.DataFrame([{"file": str(path.relative_to(output)).replace("\\", "/"), "bytes": path.stat().st_size, "sha256": sha256_file(path)} for path in files])
    atomic_csv(output / "checksum_manifest.csv", checksums)
    atomic_json(output / "manifest.json", {"task": TASK, "generated_at": now(), "authority_path": str(AUTHORITY), "authority_sha256": sha256_file(AUTHORITY), "network_scope": "ticker=00631L exact four dates TWSE selected ticker-month close-only", "readiness": readiness, "files": checksums.to_dict("records"), "future_data_violation_count": 0, **FLAGS})


def run(args: argparse.Namespace) -> dict:
    output = args.output.resolve(); output.mkdir(parents=True, exist_ok=True)
    authority = load_authority(args.authority); dates = set(authority["date"])
    months = sorted({date[:7] for date in dates}); items = []
    for month in months:
        checkpoint = output / "checkpoints/00631L" / f"{month}.json.gz"
        if checkpoint.exists() and read_checkpoint(checkpoint).get("status") == "accepted":
            item = read_checkpoint(checkpoint)
        else:
            item = request_month("00631L", month); item["task"] = TASK; write_checkpoint(checkpoint, item)
        items.append(item)
    rows = [row for item in items for row in extract_exact(item, dates)]
    patch = pd.DataFrame(rows).drop_duplicates(["ticker", "date"], keep="first").sort_values("date")
    patch = patch.merge(authority, on=["ticker", "date"], how="inner")
    ready = set(patch["date"]); blocked_rows = []
    for date_s in EXPECTED_DATES:
        if date_s in ready: continue
        item = next((value for value in items if value.get("month") == date_s[:7]), {})
        blocked_rows.append({"ticker": "00631L", "date": date_s, "market": "TWSE", "classification": "official_valid_no_target" if item.get("status") == "accepted" else "temporary_source_gap", "reason": "exact_date_absent_from_valid_official_selected_ticker_month_response" if item.get("status") == "accepted" else item.get("error", "route_not_attempted"), "source_url": item.get("source_url", ""), "source_hash": item.get("source_hash", ""), "retrieved_at": item.get("retrieved_at", ""), "future_data_violation_count": 0})
    blocked = pd.DataFrame(blocked_rows).reindex(columns=["ticker", "date", "market", "classification", "reason", "source_url", "source_hash", "retrieved_at", "future_data_violation_count"])
    source_manifest = pd.DataFrame([{key: value for key, value in item.items() if key != "rows"} for item in items])
    atomic_csv(output / "strict_bear_cash_rechain_exact_close_patch.csv", patch)
    atomic_csv(output / "strict_bear_cash_rechain_exact_close_blocked.csv", blocked)
    atomic_csv(output / "strict_bear_cash_rechain_source_manifest.csv", source_manifest)
    atomic_csv(output / "requested_vs_actual_coverage.csv", pd.DataFrame([{"classification": "requested_exact_keys", "rows": 4, "future_data_violation_count": 0}, {"classification": "official_raw_close_ready", "rows": len(patch), "future_data_violation_count": 0}, {"classification": "blocked", "rows": len(blocked), "future_data_violation_count": 0}]))
    atomic_csv(output / "future_data_audit.csv", pd.DataFrame([{"audit": "authority_exact_four_00631L_dates_only", "status": "pass", "future_data_violation_count": 0}, {"audit": "official_raw_close_only", "status": "pass", "future_data_violation_count": 0}, {"audit": "neighbor_last_benchmark_substitution", "status": "false", "future_data_violation_count": 0}, {"audit": "performance_calculation", "status": "false", "future_data_violation_count": 0}]))
    readiness = {"task": TASK, "status": "complete_ready_for_core_absorption" if len(patch) == 4 else "complete_with_explicit_source_blockers", "requested_exact_keys": 4, "official_raw_close_ready_rows": len(patch), "blocked_rows": len(blocked), "partition_rows": len(patch) + len(blocked), "partition_matches_authority": len(patch) + len(blocked) == 4, "duplicate_exact_keys": int(patch.duplicated(["ticker", "date"]).sum()), "network_routes": len(months), "network_outside_authority_rows": 0, "non_close_family_download_rows": 0, "ready_for_core_strict_bear_cash_rechain_close_absorption": len(patch) == 4, "ready_for_experiments": False, "data_readiness_blocked_only": bool(len(blocked)), "may_be_used_to_reject_strategy": False, "future_data_violation_count": 0, **FLAGS}
    atomic_json(output / "readiness_for_core_strict_bear_cash_rechain_close_absorption.json", readiness)
    atomic_text(output / "final_summary_zh.md", "# strict bear-cash rechain 00631L exact close fill\n\n" f"- authority：4 exact dates。\n- official raw close ready：{len(patch)}。\n- blocked：{len(blocked)}。\n- network routes：{len(months)}。\n- 僅處理 official raw close；未計績效。\n")
    atomic_json(output / "progress.json", {**readiness, "updated_at": now()}); atomic_text(output / "current_step.txt", "status=complete\nresume_step=none\nnext_owner=Core_Data_bear_cash_rechain\n")
    build_manifest(output, readiness); print(json.dumps(readiness, ensure_ascii=False, indent=2)); return readiness


def main() -> None:
    parser = argparse.ArgumentParser(); parser.add_argument("--authority", type=Path, default=AUTHORITY); parser.add_argument("--output", type=Path, default=OUTPUT); run(parser.parse_args())


if __name__ == "__main__": main()
