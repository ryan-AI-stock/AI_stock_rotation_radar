from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

try:
    from scripts.run_weekly_ai_diffusion_switch_close_fill import FLAGS, REPO, atomic_csv, atomic_json, atomic_text, now, read_checkpoint, request_month, sha256_file, write_checkpoint
except ModuleNotFoundError:
    from run_weekly_ai_diffusion_switch_close_fill import FLAGS, REPO, atomic_csv, atomic_json, atomic_text, now, read_checkpoint, request_month, sha256_file, write_checkpoint


TASK = "TASK-RADAR-DATA-VNEXT-P1-P2-OLD-AI7-PRIORITY-00631L-BACKUP-CD-OVERRIDE-PATH-INDEPENDENT-00631L-CLOSE-UNION-FILL-003"
CORE_OUTPUT = Path(r"C:\Users\zergv\Documents\Codex\2026-05-30\ep05-chat-ai-stock-backtest-lab\outputs\vnext_p1_p2_old_ai7_priority_00631l_backup_cd_override_contract_20260720")
AUTHORITY = CORE_OUTPUT / "path_independent_close_gap_union.csv"
OUTPUT = REPO / "outputs/radar_vnext_p1_p2_old_ai7_priority_00631l_backup_cd_override_execution_union_close_fill_20260720"


def load_authority(path: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    raw = pd.read_csv(path, dtype=str, low_memory=False)
    if not {"ticker", "date"}.issubset(raw.columns):
        raise RuntimeError("authority_schema_missing")
    raw = raw[["ticker", "date"]].copy()
    raw["ticker"] = raw["ticker"].astype(str).str.strip().str.upper()
    raw["date"] = raw["date"].astype(str).str[:10]
    if len(raw) != 2228 or set(raw["ticker"]) != {"00631L"}:
        raise RuntimeError(f"authority_scope_changed:{len(raw)}:{raw['ticker'].unique().tolist()}")
    duplicates = raw[raw.duplicated(["ticker", "date"], keep=False)].sort_values(["ticker", "date"])
    authority = raw.drop_duplicates(["ticker", "date"]).sort_values(["ticker", "date"]).reset_index(drop=True)
    if len(authority) != 2227 or len(duplicates) != 2:
        raise RuntimeError(f"authority_duplicate_contract_changed:{len(authority)}:{len(duplicates)}")
    return authority, duplicates


def source_row(date: str, checkpoint: Path, item: dict, reuse: str) -> dict | None:
    for row in item.get("rows", []):
        if row.get("date") == date and row.get("close") is not None:
            return {"ticker": "00631L", "date": date, "market": "TWSE", "close": row["close"], "source_quality": "official_twse_selected_ticker_month_close_only", "adjustment_policy": "official_unadjusted_execution_close_only", "source_url": item.get("source_url", ""), "source_hash": item.get("source_hash", ""), "retrieved_at": item.get("retrieved_at", ""), "checkpoint_path": str(checkpoint), "source_reuse": reuse, "future_data_violation_count": 0}
    return None


def local_checkpoint_index(authority: pd.DataFrame) -> dict[str, dict]:
    targets = set(authority["date"])
    found: dict[str, dict] = {}
    for checkpoint in sorted(REPO.glob("outputs/**/checkpoints/00631L/*.json.gz")):
        try:
            item = read_checkpoint(checkpoint)
        except (OSError, ValueError, json.JSONDecodeError):
            continue
        if item.get("status") != "accepted":
            continue
        for row in item.get("rows", []):
            date = row.get("date")
            if date not in targets or date in found or row.get("close") is None:
                continue
            found[date] = source_row(date, checkpoint, item, "previous_accepted_official_ticker_month_checkpoint")
    return found


def write_progress(output: Path, total_routes: int, completed_routes: int, ready: int, no_trade: int, blocked: int, phase: str) -> None:
    atomic_json(output / "progress.json", {"task": TASK, "phase": phase, "completed_routes": completed_routes, "total_routes": total_routes, "accepted_keys": ready, "official_no_trade_keys": no_trade, "blocked_keys": blocked, "updated_at": now(), "future_data_violation_count": 0})
    atomic_text(output / "current_step.txt", f"status={phase}\ncompleted_routes={completed_routes}/{total_routes}\nresume_step=python -X utf8 scripts/run_old_ai7_priority_backup_cd_override_execution_union_close_fill.py\n")


def fetch_authorized_months(authority: pd.DataFrame, found: dict[str, dict], output: Path) -> tuple[dict[str, dict], list[dict], list[dict], int]:
    remaining = authority[~authority["date"].isin(found)].copy()
    grouped = list(remaining.groupby(remaining["date"].str[:7], sort=True))
    no_trade, blocked = [], []
    write_progress(output, len(grouped), 0, len(found), 0, 0, "authorized_month_routes_running")
    for index, (month, group) in enumerate(grouped, start=1):
        checkpoint = output / "checkpoints" / "00631L" / f"{month}.json.gz"
        item = read_checkpoint(checkpoint) if checkpoint.exists() else request_month("00631L", month)
        if not checkpoint.exists():
            write_checkpoint(checkpoint, item)
        if item.get("status") == "accepted":
            for date in group["date"]:
                row = source_row(date, checkpoint, item, "new_authorized_official_ticker_month_route")
                if row:
                    found[date] = row
                else:
                    no_trade.append({"ticker": "00631L", "date": date, "market": "TWSE", "classification": "official_no_trade", "reason": "accepted_official_ticker_month_response_has_no_exact_trade_row", "source_url": item.get("source_url", ""), "source_hash": item.get("source_hash", ""), "retrieved_at": item.get("retrieved_at", ""), "future_data_violation_count": 0})
        else:
            for date in group["date"]:
                blocked.append({"ticker": "00631L", "date": date, "market": "TWSE", "classification": "temporary_source_gap", "reason": item.get("error", "official_month_route_not_accepted"), "source_url": item.get("source_url", ""), "source_hash": item.get("source_hash", ""), "retrieved_at": item.get("retrieved_at", ""), "future_data_violation_count": 0})
        write_progress(output, len(grouped), index, len(found), len(no_trade), len(blocked), "authorized_month_routes_running")
    return found, no_trade, blocked, len(grouped)


def write_manifest(output: Path, readiness: dict) -> None:
    files = sorted(path for path in output.rglob("*") if path.is_file() and path.name not in {"manifest.json", "checksum_manifest.csv"})
    checks = pd.DataFrame([{"file": str(path.relative_to(output)).replace("\\", "/"), "bytes": path.stat().st_size, "sha256": sha256_file(path)} for path in files])
    atomic_csv(output / "checksum_manifest.csv", checks)
    atomic_json(output / "manifest.json", {"task": TASK, "generated_at": now(), "authority_path": str(AUTHORITY), "authority_sha256": sha256_file(AUTHORITY), "files": checks.to_dict("records"), "readiness": readiness, "future_data_violation_count": 0, **FLAGS})


def run(args: argparse.Namespace) -> dict:
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    authority, duplicates = load_authority(args.authority)
    found = local_checkpoint_index(authority)
    found, no_trade, blocked, routes = fetch_authorized_months(authority, found, output)
    patch = pd.DataFrame(list(found.values())).drop_duplicates(["ticker", "date"]).sort_values("date")
    no_trade_frame = pd.DataFrame(no_trade)
    blocked_frame = pd.DataFrame(blocked)
    atomic_csv(output / "exact_close_patch.csv", patch)
    atomic_csv(output / "official_no_trade.csv", no_trade_frame)
    atomic_csv(output / "blocked.csv", blocked_frame)
    atomic_csv(output / "authority_duplicate_audit.csv", duplicates.assign(classification="duplicate_authority_key_not_extra_download_requirement"))
    atomic_csv(output / "future_data_audit.csv", pd.DataFrame([{"audit": "exact_authority_close_only", "status": "pass", "future_data_violation_count": 0}, {"audit": "neighbor_last_adjusted_benchmark_substitution", "status": "false", "future_data_violation_count": 0}, {"audit": "performance_calculation", "status": "false", "future_data_violation_count": 0}]))
    readiness = {"task": TASK, "status": "complete_ready_for_core_absorption" if len(blocked_frame) == 0 else "partial_source_gap", "authority_rows": 2228, "authority_unique_exact_keys": len(authority), "authority_duplicate_rows": len(duplicates), "official_raw_close_ready_rows": len(patch), "official_no_trade_rows": len(no_trade_frame), "blocked_rows": len(blocked_frame), "partition_matches_unique_authority": len(patch) + len(no_trade_frame) + len(blocked_frame) == len(authority), "duplicate_exact_keys": int(patch.duplicated(["ticker", "date"]).sum()), "network_routes": routes, "local_accepted_checkpoint_reuse_rows": int((patch["source_reuse"] == "previous_accepted_official_ticker_month_checkpoint").sum()), "network_outside_authority_rows": 0, "non_close_family_download_rows": 0, "ready_for_core_old_ai7_priority_backup_cd_override_execution_union_close_absorption": len(blocked_frame) == 0, "ready_for_experiments": False, "future_data_violation_count": 0, **FLAGS}
    atomic_csv(output / "coverage.csv", pd.DataFrame([{"classification": "authority_rows", "rows": 2228}, {"classification": "authority_unique_exact_keys", "rows": len(authority)}, {"classification": "official_raw_close_ready", "rows": len(patch)}, {"classification": "official_no_trade", "rows": len(no_trade_frame)}, {"classification": "blocked", "rows": len(blocked_frame)}]))
    atomic_json(output / "readiness_for_core.json", readiness)
    write_progress(output, routes, routes, len(patch), len(no_trade_frame), len(blocked_frame), "complete")
    atomic_text(output / "final_summary_zh.md", f"# old AI7 priority 00631L backup CD override execution close union\n\n- authority rows=2228；unique exact keys={len(authority)}；duplicate authority rows={len(duplicates)}。\n- official raw close={len(patch)}；official no-trade={len(no_trade_frame)}；blocked={len(blocked_frame)}。\n- local checkpoint reuse rows={readiness['local_accepted_checkpoint_reuse_rows']}；new authorized TWSE month routes={routes}。\n")
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
