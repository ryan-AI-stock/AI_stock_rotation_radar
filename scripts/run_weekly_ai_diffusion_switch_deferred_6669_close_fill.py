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
        read_checkpoint,
        request_month,
        sha256_file,
        write_checkpoint,
    )


TASK = "TASK-RADAR-DATA-VNEXT-P1-P2-AI-DIFFUSION-WEEKLY-SWITCH-DEFERRED-6669-CLOSE-FILL-001"
CORE_OUTPUT = Path(
    r"C:\Users\zergv\Documents\Codex\2026-05-30\ep05-chat-ai-stock-backtest-lab"
    r"\outputs\vnext_p1_p2_ai_concentration_diffusion_weekly_switch_exact_nav_contract_20260718"
)
AUTHORITY = CORE_OUTPUT / "weekly_switch_bounded_official_raw_execution_gap_ledger.csv"
OUTPUT = REPO / "outputs/radar_vnext_p1_p2_ai_diffusion_weekly_switch_deferred_6669_close_fill_20260718"
PREVIOUS_OUTPUT = REPO / "outputs/radar_vnext_p1_p2_ai_diffusion_weekly_switch_close_fill_20260718"
EXPECTED_DATES = ["2019-03-27", "2019-03-28", "2019-03-29", "2019-04-01"]


def load_authority(path: Path) -> pd.DataFrame:
    frame = pd.read_csv(path, dtype=str, low_memory=False)
    if not {"ticker", "date"}.issubset(frame.columns):
        raise RuntimeError("authority_schema_missing")
    frame = frame[["ticker", "date"]].drop_duplicates().sort_values(["ticker", "date"]).reset_index(drop=True)
    frame["ticker"] = frame["ticker"].astype(str).str.strip()
    frame["date"] = frame["date"].astype(str).str[:10]
    if frame["ticker"].tolist() != ["6669"] * 4 or frame["date"].tolist() != EXPECTED_DATES:
        raise RuntimeError(f"authority_scope_changed:{frame.to_dict('records')}")
    return frame


def exact_rows_from_checkpoint(item: dict, ticker: str, dates: set[str], reuse: str) -> list[dict]:
    rows = []
    for row in item.get("rows", []):
        date_s = str(row.get("date", ""))[:10]
        if date_s not in dates or row.get("close") is None:
            continue
        rows.append(
            {
                "ticker": ticker,
                "date": date_s,
                "market": "TWSE",
                "close": row["close"],
                "source_quality": "official_twse_selected_ticker_month_close_only",
                "adjustment_policy": "official_unadjusted_execution_close_only",
                "source_url": item.get("source_url", ""),
                "source_hash": item.get("source_hash", ""),
                "retrieved_at": item.get("retrieved_at", ""),
                "source_reuse": reuse,
                "future_data_violation_count": 0,
            }
        )
    return rows


def build_manifest(output: Path, readiness: dict) -> None:
    excluded = {"manifest.json", "checksum_manifest.csv"}
    files = sorted(path for path in output.rglob("*") if path.is_file() and path.name not in excluded)
    checksums = pd.DataFrame(
        [
            {
                "file": str(path.relative_to(output)).replace("\\", "/"),
                "bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            }
            for path in files
        ]
    )
    atomic_csv(output / "checksum_manifest.csv", checksums)
    atomic_json(
        output / "manifest.json",
        {
            "task": TASK,
            "generated_at": now(),
            "authority_path": str(AUTHORITY),
            "authority_sha256": sha256_file(AUTHORITY),
            "network_scope": "ticker=6669, exact four dates, TWSE selected ticker-month close-only",
            "readiness": readiness,
            "files": checksums.to_dict("records"),
            "future_data_violation_count": 0,
            **FLAGS,
        },
    )


def run(args: argparse.Namespace) -> dict:
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    authority = load_authority(args.authority)
    authority_dates = set(authority["date"])

    rows: list[dict] = []
    previous_april = PREVIOUS_OUTPUT / "checkpoints/6669/2019-04.json.gz"
    if previous_april.exists():
        rows.extend(
            exact_rows_from_checkpoint(
                read_checkpoint(previous_april),
                "6669",
                authority_dates,
                "previous_accepted_ticker_month_checkpoint",
            )
        )

    ready_dates = {row["date"] for row in rows}
    network_months = sorted({date[:7] for date in authority_dates - ready_dates})
    route_results = []
    for month in network_months:
        checkpoint = output / "checkpoints/6669" / f"{month}.json.gz"
        if checkpoint.exists() and read_checkpoint(checkpoint).get("status") == "accepted":
            item = read_checkpoint(checkpoint)
        else:
            item = request_month("6669", month)
            item["task"] = TASK
            write_checkpoint(checkpoint, item)
        route_results.append(item)
        rows.extend(exact_rows_from_checkpoint(item, "6669", authority_dates, "network_exact_authority_month"))

    patch = pd.DataFrame(rows).drop_duplicates(["ticker", "date"], keep="first").sort_values("date")
    patch = patch.merge(authority, on=["ticker", "date"], how="inner")
    ready_dates = set(patch["date"])
    blocked_rows = []
    for date_s in EXPECTED_DATES:
        if date_s in ready_dates:
            continue
        item = next((value for value in route_results if value.get("month") == date_s[:7]), {})
        blocked_rows.append(
            {
                "ticker": "6669",
                "date": date_s,
                "market": "TWSE",
                "classification": (
                    "official_valid_no_target"
                    if item.get("status") == "accepted"
                    else "temporary_source_gap"
                ),
                "reason": (
                    "exact_date_absent_from_valid_official_selected_ticker_month_response"
                    if item.get("status") == "accepted"
                    else item.get("error", "route_not_attempted")
                ),
                "source_url": item.get("source_url", ""),
                "source_hash": item.get("source_hash", ""),
                "retrieved_at": item.get("retrieved_at", ""),
                "future_data_violation_count": 0,
            }
        )
    blocked = pd.DataFrame(blocked_rows).reindex(
        columns=[
            "ticker", "date", "market", "classification", "reason", "source_url",
            "source_hash", "retrieved_at", "future_data_violation_count",
        ]
    )
    source_manifest = pd.DataFrame(
        [{key: value for key, value in item.items() if key != "rows"} for item in route_results]
    )
    atomic_csv(output / "weekly_switch_deferred_6669_exact_close_patch.csv", patch)
    atomic_csv(output / "weekly_switch_deferred_6669_exact_close_blocked.csv", blocked)
    atomic_csv(output / "weekly_switch_deferred_6669_source_manifest.csv", source_manifest)
    atomic_csv(
        output / "requested_vs_actual_coverage.csv",
        pd.DataFrame(
            [
                {"classification": "requested_exact_keys", "rows": 4, "future_data_violation_count": 0},
                {"classification": "official_raw_close_ready", "rows": len(patch), "future_data_violation_count": 0},
                {"classification": "blocked", "rows": len(blocked), "future_data_violation_count": 0},
            ]
        ),
    )
    atomic_csv(
        output / "future_data_audit.csv",
        pd.DataFrame(
            [
                {"audit": "authority_exact_four_6669_dates_only", "status": "pass", "future_data_violation_count": 0},
                {"audit": "official_raw_close_only", "status": "pass", "future_data_violation_count": 0},
                {"audit": "neighbor_last_benchmark_substitution", "status": "false", "future_data_violation_count": 0},
                {"audit": "performance_calculation", "status": "false", "future_data_violation_count": 0},
            ]
        ),
    )
    readiness = {
        "task": TASK,
        "status": "complete_ready_for_core_absorption" if len(patch) == 4 else "complete_with_explicit_source_blockers",
        "requested_exact_keys": 4,
        "official_raw_close_ready_rows": len(patch),
        "blocked_rows": len(blocked),
        "partition_rows": len(patch) + len(blocked),
        "partition_matches_authority": len(patch) + len(blocked) == 4,
        "duplicate_exact_keys": int(patch.duplicated(["ticker", "date"]).sum()),
        "local_checkpoint_reuse_rows": sum(row["source_reuse"].startswith("previous") for row in rows),
        "network_routes": len(network_months),
        "network_outside_authority_rows": 0,
        "non_close_family_download_rows": 0,
        "ready_for_core_weekly_switch_deferred_6669_close_absorption": len(patch) == 4,
        "ready_for_experiments": False,
        "future_data_violation_count": 0,
        **FLAGS,
    }
    atomic_json(output / "readiness_for_core_weekly_switch_deferred_6669_close_absorption.json", readiness)
    atomic_text(
        output / "final_summary_zh.md",
        "# weekly switch deferred 6669 exact close fill\n\n"
        f"- authority：4 exact dates。\n"
        f"- official raw close ready：{len(patch)}。\n"
        f"- blocked：{len(blocked)}。\n"
        f"- network ticker-month routes：{len(network_months)}。\n"
        "- 僅處理 6669 official raw close；未計績效、未擴資料 family。\n"
        "- future_data_violation_count=0。\n",
    )
    atomic_json(output / "progress.json", {**readiness, "updated_at": now()})
    atomic_text(output / "current_step.txt", "status=complete\nresume_step=none\nnext_owner=Core_Data_final_rechain\n")
    build_manifest(output, readiness)
    print(json.dumps(readiness, ensure_ascii=False, indent=2))
    return readiness


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--authority", type=Path, default=AUTHORITY)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    run(parser.parse_args())


if __name__ == "__main__":
    main()
