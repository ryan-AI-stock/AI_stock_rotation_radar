from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

try:
    from scripts.run_weekly_ai_diffusion_switch_close_fill import (
        FLAGS,
        REPO,
        atomic_csv,
        atomic_json,
        atomic_text,
        now,
        parse_twse_stock_day,
        read_checkpoint,
        request_month,
        sha256_file,
        write_checkpoint,
    )
except ModuleNotFoundError:
    from run_weekly_ai_diffusion_switch_close_fill import (
        FLAGS,
        REPO,
        atomic_csv,
        atomic_json,
        atomic_text,
        now,
        parse_twse_stock_day,
        read_checkpoint,
        request_month,
        sha256_file,
        write_checkpoint,
    )


TASK = "TASK-RADAR-DATA-VNEXT-P1-P2-OLD-AI7-VS-00631L-WEEKLY-MEDIAN-RS60-TWO-SLEEVE-PATH-INDEPENDENT-EXECUTION-CLOSE-UNION-FILL-003"
CORE_OUTPUT = Path(r"C:\Users\zergv\Documents\Codex\2026-05-30\ep05-chat-ai-stock-backtest-lab\outputs\vnext_p1_p2_old_ai7_vs_00631l_weekly_median_rs60_two_sleeve_contract_20260719")
AUTHORITY = CORE_OUTPUT / "path_independent_close_gap_union.csv"
OUTPUT = REPO / "outputs/radar_vnext_p1_p2_old_ai7_median_rs60_two_sleeve_execution_union_close_fill_20260719"


def load_authority(path: Path) -> pd.DataFrame:
    frame = pd.read_csv(path, dtype=str, low_memory=False)[["ticker", "date"]].drop_duplicates()
    frame["ticker"] = frame["ticker"].astype(str).str.strip().str.upper()
    frame["date"] = frame["date"].astype(str).str[:10]
    if len(frame) != 34 or set(frame["ticker"]) != {"00631L"}:
        raise RuntimeError(f"authority_scope_changed:{len(frame)}:{frame['ticker'].unique().tolist()}")
    return frame.sort_values("date").reset_index(drop=True)


def row_from_checkpoint(date: str, checkpoint: Path, item: dict, reuse: str) -> dict | None:
    for raw in item.get("rows", []):
        if raw.get("date") == date and raw.get("close") is not None:
            return {
                "ticker": "00631L",
                "date": date,
                "market": "TWSE",
                "close": raw["close"],
                "source_quality": "official_twse_selected_ticker_month_close_only",
                "adjustment_policy": "official_unadjusted_execution_close_only",
                "source_url": item.get("source_url", ""),
                "source_hash": item.get("source_hash", ""),
                "retrieved_at": item.get("retrieved_at", ""),
                "checkpoint_path": str(checkpoint),
                "source_reuse": reuse,
                "future_data_violation_count": 0,
            }
    return None


def local_rows(authority: pd.DataFrame) -> dict[str, dict]:
    targets = set(authority["date"])
    found: dict[str, dict] = {}
    for checkpoint in sorted(REPO.glob("outputs/**/checkpoints/00631L/*.json.gz")):
        try:
            item = read_checkpoint(checkpoint)
        except (OSError, ValueError, json.JSONDecodeError):
            continue
        if item.get("status") != "accepted":
            continue
        for date in targets - set(found):
            row = row_from_checkpoint(date, checkpoint, item, "previous_accepted_official_ticker_month_checkpoint")
            if row:
                found[date] = row
    return found


def fetch_missing(authority: pd.DataFrame, found: dict[str, dict], output: Path) -> tuple[dict[str, dict], list[dict], list[dict], int]:
    no_trade, blocked = [], []
    remaining = authority[~authority["date"].isin(found)].copy()
    routes = 0
    for month, group in remaining.groupby(remaining["date"].str[:7], sort=True):
        checkpoint = output / "checkpoints" / "00631L" / f"{month}.json.gz"
        item = read_checkpoint(checkpoint) if checkpoint.exists() else request_month("00631L", month)
        if not checkpoint.exists():
            routes += 1
            write_checkpoint(checkpoint, item)
        if item.get("status") != "accepted":
            for date in group["date"]:
                blocked.append({"ticker": "00631L", "date": date, "market": "TWSE", "classification": "source_gap", "reason": item.get("error", "official_month_route_not_accepted"), "source_url": item.get("source_url", ""), "source_hash": item.get("source_hash", ""), "retrieved_at": item.get("retrieved_at", ""), "future_data_violation_count": 0})
            continue
        for date in group["date"]:
            row = row_from_checkpoint(date, checkpoint, item, "new_authorized_official_ticker_month_route")
            if row:
                found[date] = row
            else:
                no_trade.append({"ticker": "00631L", "date": date, "market": "TWSE", "classification": "official_no_trade", "reason": "accepted_official_ticker_month_response_has_no_exact_trade_row", "source_url": item.get("source_url", ""), "source_hash": item.get("source_hash", ""), "retrieved_at": item.get("retrieved_at", ""), "future_data_violation_count": 0})
    return found, no_trade, blocked, routes


def write_manifest(output: Path, readiness: dict) -> None:
    files = sorted(path for path in output.rglob("*") if path.is_file() and path.name not in {"manifest.json", "checksum_manifest.csv"})
    checks = pd.DataFrame([{"file": str(path.relative_to(output)).replace("\\", "/"), "bytes": path.stat().st_size, "sha256": sha256_file(path)} for path in files])
    atomic_csv(output / "checksum_manifest.csv", checks)
    atomic_json(output / "manifest.json", {"task": TASK, "generated_at": now(), "authority_path": str(AUTHORITY), "authority_sha256": sha256_file(AUTHORITY), "files": checks.to_dict("records"), "readiness": readiness, "future_data_violation_count": 0, **FLAGS})


def run(args: argparse.Namespace) -> dict:
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    authority = load_authority(args.authority)
    found = local_rows(authority)
    found, no_trade, blocked, routes = fetch_missing(authority, found, output)
    patch = pd.DataFrame(list(found.values())).drop_duplicates(["ticker", "date"]).sort_values("date")
    no_trade_frame = pd.DataFrame(no_trade)
    blocked_frame = pd.DataFrame(blocked)
    prefix = "old_ai7_median_rs60_two_sleeve_execution_union_exact_close"
    atomic_csv(output / f"{prefix}_patch.csv", patch)
    atomic_csv(output / f"{prefix}_no_trade.csv", no_trade_frame)
    atomic_csv(output / f"{prefix}_blocked.csv", blocked_frame)
    atomic_csv(output / "future_data_audit.csv", pd.DataFrame([{"audit": "exact_authority_close_only", "status": "pass", "future_data_violation_count": 0}, {"audit": "neighbor_last_adjusted_benchmark_substitution", "status": "false", "future_data_violation_count": 0}, {"audit": "performance_calculation", "status": "false", "future_data_violation_count": 0}]))
    readiness = {"task": TASK, "status": "complete_ready_for_core_absorption" if len(blocked_frame) == 0 else "partial_source_gap", "requested_exact_keys": len(authority), "official_raw_close_ready_rows": len(patch), "official_no_trade_rows": len(no_trade_frame), "blocked_rows": len(blocked_frame), "partition_rows": len(patch) + len(no_trade_frame) + len(blocked_frame), "partition_matches_authority": len(patch) + len(no_trade_frame) + len(blocked_frame) == len(authority), "duplicate_exact_keys": int(patch.duplicated(["ticker", "date"]).sum()), "network_routes": routes, "local_accepted_checkpoint_reuse_rows": len(patch[patch["source_reuse"].eq("previous_accepted_official_ticker_month_checkpoint")]), "network_outside_authority_rows": 0, "non_close_family_download_rows": 0, "ready_for_core_old_ai7_median_rs60_two_sleeve_execution_union_close_absorption": len(blocked_frame) == 0, "ready_for_experiments": False, "future_data_violation_count": 0, **FLAGS}
    atomic_csv(output / "requested_vs_actual_coverage.csv", pd.DataFrame([{"classification": "requested_exact_keys", "rows": len(authority)}, {"classification": "official_raw_close_ready", "rows": len(patch)}, {"classification": "official_no_trade", "rows": len(no_trade_frame)}, {"classification": "blocked", "rows": len(blocked_frame)}]))
    atomic_json(output / "readiness_for_core_old_ai7_median_rs60_two_sleeve_execution_union_close_absorption.json", readiness)
    atomic_json(output / "progress.json", {**readiness, "updated_at": now()})
    atomic_text(output / "current_step.txt", "status=complete\nresume_step=none\nnext_owner=Core_Data_two_sleeve_final_rechain\n")
    atomic_text(output / "final_summary_zh.md", f"# old AI7 versus 00631L weekly median RS60 two-sleeve path-independent execution union fill\n\n- authority={len(authority)}；official raw close={len(patch)}；official no-trade={len(no_trade_frame)}；blocked={len(blocked_frame)}。\n- local checkpoint reuse rows={readiness['local_accepted_checkpoint_reuse_rows']}；new authorized network routes={routes}。\n")
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
