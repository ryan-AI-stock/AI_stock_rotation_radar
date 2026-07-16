from __future__ import annotations

import gzip
import hashlib
import json
import os
import uuid
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd


TASK = "TASK-RADAR-DATA-VNEXT-P1-P2-MA-SLOPE-CD50-SHIFTED-PATH-LOCAL-CLOSE-EXTRACTION-001"
RADAR = Path(r"C:\Users\zergv\Documents\Codex\2026-05-23\ai-stock-rotation-radar-https-docs")
CORE = Path(
    r"C:\Users\zergv\Documents\Codex\2026-05-30\ep05-chat-ai-stock-backtest-lab\outputs"
    r"\vnext_p1_p2_layer4_primary80_individual_MA_slope_CD50_action_legs_20260715"
)
PREVIOUS = RADAR / "outputs/radar_vnext_p1_p2_primary80_ma_slope_cd50_one_shot_close_fill_20260716"
PREVIOUS_CORE = Path(
    r"C:\Users\zergv\Documents\Codex\2026-05-30\ep05-chat-ai-stock-backtest-lab\outputs"
    r"\vnext_p1_p2_primary80_MA_slope_CD50_one_shot_close_authority_20260716"
)
OUTPUT = RADAR / "outputs/radar_vnext_p1_p2_ma_slope_cd50_shifted_path_local_close_extraction_20260716"
KEY = ["period", "ticker", "date"]
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


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def atomic_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.parent / f"._tmp_{os.getpid()}_{uuid.uuid4().hex}.tmp"
    temp.write_text(text, encoding="utf-8")
    os.replace(temp, path)


def atomic_json(path: Path, value: object) -> None:
    atomic_text(path, json.dumps(value, ensure_ascii=False, indent=2, default=str) + "\n")


def atomic_csv(path: Path, frame: pd.DataFrame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.parent / f"._tmp_{os.getpid()}_{uuid.uuid4().hex}.tmp"
    frame.to_csv(temp, index=False, encoding="utf-8-sig", compression="gzip" if path.suffix == ".gz" else None)
    os.replace(temp, path)


def step(output: Path, value: str, **extra: object) -> None:
    atomic_text(output / "current_step.txt", value + "\n")
    atomic_json(output / "progress.json", {
        "task": TASK,
        "status": "running" if not value.startswith("completed") else "completed",
        "current_step": value,
        "updated_at": now(),
        "network_requests": 0,
        "future_data_violation_count": 0,
        **extra,
    })


def read_checkpoint_rows(folder: Path) -> tuple[pd.DataFrame, dict[str, int]]:
    rows: list[dict] = []
    statuses: Counter[str] = Counter()
    files = sorted(folder.rglob("*.json.gz"))
    for path in files:
        with gzip.open(path, "rt", encoding="utf-8") as handle:
            item = json.load(handle)
        statuses[str(item.get("status") or "")] += 1
        rows.extend(item.get("rows") or [])
    return pd.DataFrame(rows), {"files": len(files), **dict(statuses)}


def normalize_keys(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.copy()
    for column in KEY:
        out[column] = out[column].astype(str).str.strip()
    out["date"] = out["date"].str[:10]
    return out


def adjusted_authority() -> pd.DataFrame:
    frame = pd.read_csv(CORE / "p1_p2_MA_slope_CD50_incumbent_analysis_gap_audit.csv.gz", dtype=str)
    accepted = {
        "one_shot_strict_adjusted_authority_not_materialized",
        "one_shot_adjusted_analysis_source_blocked",
    }
    frame = frame[frame["classification"].isin(accepted)].copy()
    frame = frame.rename(columns={"decision_date": "date"})
    return normalize_keys(frame[["period", "ticker", "date", "classification", "one_shot_adjusted_blocked_reason"]]) \
        .drop_duplicates(KEY).sort_values(KEY).reset_index(drop=True)


def raw_authority() -> pd.DataFrame:
    frame = pd.read_csv(CORE / "p1_p2_MA_slope_CD50_final_official_raw_blocked_ledger.csv", dtype=str)
    frame = frame.rename(columns={"requested_execution_date": "date"})
    keep = ["period", "ticker", "date", "variant_id", "decision_date", "role", "reason"]
    return normalize_keys(frame[keep]).drop_duplicates(KEY).sort_values(KEY).reset_index(drop=True)


def adjusted_sources(authority: pd.DataFrame, checkpoint: pd.DataFrame) -> pd.DataFrame:
    normalized = pd.read_csv(PREVIOUS_CORE / "normalized_local_close_index.csv.gz", dtype=str)
    normalized = normalize_keys(normalized)
    normalized = normalized[normalized["adjusted_analysis_close"].notna()][KEY + ["adjusted_analysis_close", "adjusted_source"]]
    normalized["source_priority"] = 1
    normalized["source_component"] = "normalized_local_close_index"

    patch = normalize_keys(pd.read_csv(PREVIOUS / "one_shot_adjusted_analysis_close_patch.csv.gz", dtype=str))
    patch = patch[KEY + ["adjusted_analysis_close", "source_quality", "source_url", "source_hash", "retrieved_at"]]
    patch = patch.rename(columns={"source_quality": "adjusted_source"})
    patch["source_priority"] = 2
    patch["source_component"] = "one_shot_adjusted_patch"

    if checkpoint.empty:
        checkpoint = pd.DataFrame(columns=KEY + ["adjusted_analysis_close"])
    checkpoint = normalize_keys(checkpoint)
    checkpoint = checkpoint[KEY + [column for column in [
        "adjusted_analysis_close", "source_quality", "source_url", "source_hash", "retrieved_at"
    ] if column in checkpoint.columns]]
    checkpoint = checkpoint.rename(columns={"source_quality": "adjusted_source"})
    checkpoint["source_priority"] = 3
    checkpoint["source_component"] = "one_shot_adjusted_checkpoint_target_rows"

    source = pd.concat([normalized, patch, checkpoint], ignore_index=True, sort=False)
    source = source[source["adjusted_analysis_close"].notna()].sort_values("source_priority").drop_duplicates(KEY)
    return authority.merge(source, on=KEY, how="left", validate="one_to_one")


def raw_sources(authority: pd.DataFrame, checkpoint: pd.DataFrame) -> pd.DataFrame:
    normalized = normalize_keys(pd.read_csv(PREVIOUS_CORE / "normalized_local_close_index.csv.gz", dtype=str))
    normalized = normalized[normalized["official_raw_close"].notna()][KEY + ["official_raw_close", "raw_source", "market"]]
    normalized["source_priority"] = 1
    normalized["source_component"] = "normalized_local_close_index"

    patch = normalize_keys(pd.read_csv(PREVIOUS / "one_shot_official_raw_execution_close_patch.csv.gz", dtype=str))
    patch = patch[KEY + ["official_raw_execution_close", "source_quality", "market", "source_url", "source_hash", "retrieved_at"]]
    patch = patch.rename(columns={"official_raw_execution_close": "official_raw_close", "source_quality": "raw_source"})
    patch["source_priority"] = 2
    patch["source_component"] = "one_shot_raw_patch"

    if checkpoint.empty:
        expanded = pd.DataFrame(columns=KEY + ["official_raw_close"])
    else:
        checkpoint = checkpoint.copy()
        checkpoint["ticker"] = checkpoint["ticker"].astype(str).str.strip()
        checkpoint["date"] = checkpoint["date"].astype(str).str[:10]
        expanded = authority[KEY].merge(checkpoint, on=["ticker", "date"], how="inner")
    expanded = expanded[KEY + [column for column in [
        "official_raw_execution_close", "source_quality", "market", "source_url", "source_hash", "retrieved_at"
    ] if column in expanded.columns]]
    expanded = expanded.rename(columns={"official_raw_execution_close": "official_raw_close", "source_quality": "raw_source"})
    expanded["source_priority"] = 3
    expanded["source_component"] = "one_shot_raw_checkpoint_target_rows"

    source = pd.concat([normalized, patch, expanded], ignore_index=True, sort=False)
    source = source[source["official_raw_close"].notna()].sort_values("source_priority").drop_duplicates(KEY)
    return authority.merge(source, on=KEY, how="left", validate="one_to_one")


def reusable_index() -> pd.DataFrame:
    base = normalize_keys(pd.read_csv(PREVIOUS_CORE / "normalized_local_close_index.csv.gz", dtype=str))
    adjusted = normalize_keys(pd.read_csv(PREVIOUS / "one_shot_adjusted_analysis_close_patch.csv.gz", dtype=str))
    adjusted = adjusted[KEY + ["adjusted_analysis_close", "source_quality"]].rename(columns={
        "adjusted_analysis_close": "adjusted_analysis_close_patch",
        "source_quality": "adjusted_source_patch",
    })
    raw = normalize_keys(pd.read_csv(PREVIOUS / "one_shot_official_raw_execution_close_patch.csv.gz", dtype=str))
    raw = raw[KEY + ["official_raw_execution_close", "source_quality", "market"]].rename(columns={
        "official_raw_execution_close": "official_raw_close_patch", "source_quality": "raw_source_patch", "market": "market_patch",
    })
    result = base.merge(adjusted, on=KEY, how="outer").merge(raw, on=KEY, how="outer")
    result["adjusted_analysis_close"] = result["adjusted_analysis_close_patch"].combine_first(result["adjusted_analysis_close"])
    result["adjusted_source"] = result["adjusted_source_patch"].combine_first(result["adjusted_source"])
    result["official_raw_close"] = result["official_raw_close_patch"].combine_first(result["official_raw_close"])
    result["raw_source"] = result["raw_source_patch"].combine_first(result["raw_source"])
    result["market"] = result["market_patch"].combine_first(result["market"])
    result = result[KEY + ["adjusted_analysis_close", "adjusted_source", "official_raw_close", "raw_source", "market"]]
    return result.drop_duplicates(KEY).sort_values(KEY).reset_index(drop=True)


def rebuild_manifest(output: Path, task: str = TASK, network_requests: int = 0) -> None:
    excluded = {"manifest.json", "checksum_manifest.csv"}
    files = sorted(
        path for path in output.rglob("*")
        if path.is_file() and path.name not in excluded and path.suffix != ".lock"
    )
    checksums = pd.DataFrame([{
        "file": str(path.relative_to(output)).replace("\\", "/"),
        "bytes": path.stat().st_size,
        "sha256": sha256(path),
    } for path in files])
    atomic_csv(output / "checksum_manifest.csv", checksums)
    atomic_json(output / "manifest.json", {
        "task": task,
        "generated_at": now(),
        "output_path": str(output),
        "files": checksums.to_dict("records"),
        "network_requests": network_requests,
        "future_data_violation_count": 0,
        **FLAGS,
    })


def run(output: Path = OUTPUT) -> None:
    output.mkdir(parents=True, exist_ok=True)
    lock = output / "local_extraction.lock"
    if lock.exists():
        try:
            pid = int(lock.read_text(encoding="utf-8").strip())
            os.kill(pid, 0)
            raise RuntimeError(f"runner_already_active_pid_{pid}")
        except (ValueError, ProcessLookupError, PermissionError, OSError):
            lock.unlink(missing_ok=True)
    atomic_text(lock, str(os.getpid()))
    try:
        step(output, "loading_exact_authority")
        adjusted_auth = adjusted_authority()
        raw_auth = raw_authority()
        atomic_csv(output / "shifted_path_adjusted_exact_authority.csv.gz", adjusted_auth)
        atomic_csv(output / "shifted_path_raw_exact_authority.csv", raw_auth)

        step(output, "reading_each_one_shot_checkpoint_once", adjusted_authority_rows=len(adjusted_auth), raw_authority_rows=len(raw_auth))
        adjusted_checkpoint, adjusted_status = read_checkpoint_rows(PREVIOUS / "checkpoints/adjusted")
        raw_checkpoint, raw_status = read_checkpoint_rows(PREVIOUS / "checkpoints/raw")

        step(output, "extracting_exact_local_keys")
        adjusted = adjusted_sources(adjusted_auth, adjusted_checkpoint)
        raw = raw_sources(raw_auth, raw_checkpoint)
        adjusted_ready = adjusted[adjusted["adjusted_analysis_close"].notna()].copy()
        adjusted_blocked = adjusted[adjusted["adjusted_analysis_close"].isna()].copy()
        adjusted_blocked["blocked_reason"] = "exact_key_absent_from_normalized_index_and_target_only_checkpoints"
        raw_ready = raw[raw["official_raw_close"].notna()].copy()
        raw_blocked = raw[raw["official_raw_close"].isna()].copy()
        raw_blocked["blocked_reason"] = "exact_key_absent_from_normalized_index_and_target_only_checkpoints"

        atomic_csv(output / "shifted_path_adjusted_local_extraction_patch.csv.gz", adjusted_ready)
        atomic_csv(output / "shifted_path_adjusted_local_remaining_blocked.csv.gz", adjusted_blocked)
        atomic_csv(output / "shifted_path_raw_local_extraction_patch.csv.gz", raw_ready)
        atomic_csv(output / "shifted_path_raw_local_remaining_blocked.csv", raw_blocked)

        step(output, "materializing_reusable_close_index")
        index = reusable_index()
        atomic_csv(output / "reusable_one_shot_close_index.csv.gz", index)

        audit = pd.DataFrame([
            {
                "family": "adjusted_analysis_close",
                "checkpoint_files_read_once": adjusted_status.pop("files"),
                "checkpoint_status_counts": json.dumps(adjusted_status, ensure_ascii=False, sort_keys=True),
                "full_route_payload_retained": False,
                "retained_content": "prior_authority_target_rows_only",
                "network_requests": 0,
            },
            {
                "family": "official_raw_execution_close",
                "checkpoint_files_read_once": raw_status.pop("files"),
                "checkpoint_status_counts": json.dumps(raw_status, ensure_ascii=False, sort_keys=True),
                "full_route_payload_retained": False,
                "retained_content": "prior_authority_target_rows_only",
                "network_requests": 0,
            },
        ])
        atomic_csv(output / "one_shot_checkpoint_reusability_audit.csv", audit)

        coverage = pd.DataFrame([
            {"family": "adjusted_analysis_close", "requested_rows": len(adjusted_auth), "locally_filled_rows": len(adjusted_ready), "remaining_rows": len(adjusted_blocked)},
            {"family": "official_raw_execution_close", "requested_rows": len(raw_auth), "locally_filled_rows": len(raw_ready), "remaining_rows": len(raw_blocked)},
        ])
        coverage["ready_share"] = coverage["locally_filled_rows"] / coverage["requested_rows"]
        coverage["network_requests"] = 0
        coverage["future_data_violation_count"] = 0
        atomic_csv(output / "requested_vs_actual_local_extraction.csv", coverage)
        atomic_csv(output / "future_data_audit.csv", pd.DataFrame([
            {"audit": "exact_core_authority_only", "status": "pass", "future_data_violation_count": 0},
            {"audit": "network_requests", "status": "0", "future_data_violation_count": 0},
            {"audit": "neighbor_or_last_price_substitution", "status": "prohibited_and_unused", "future_data_violation_count": 0},
            {"audit": "raw_used_as_adjusted", "status": "false", "future_data_violation_count": 0},
        ]))

        readiness = {
            "task": TASK,
            "status": "local_extraction_complete_with_explicit_remaining_keys",
            "adjusted_authority_rows": len(adjusted_auth),
            "adjusted_locally_filled_rows": len(adjusted_ready),
            "adjusted_remaining_rows": len(adjusted_blocked),
            "raw_authority_rows": len(raw_auth),
            "raw_locally_filled_rows": len(raw_ready),
            "raw_remaining_rows": len(raw_blocked),
            "reusable_close_index_rows": len(index),
            "network_requests": 0,
            "ready_for_core_shifted_path_local_close_absorption": len(adjusted_ready) + len(raw_ready) > 0,
            "ready_for_experiments": False,
            "future_data_violation_count": 0,
            **FLAGS,
        }
        atomic_json(output / "readiness_for_core_shifted_path_local_close_absorption.json", readiness)
        atomic_text(output / "final_summary_zh.md", (
            "# P1/P2 shifted-path local close extraction\n\n"
            f"- adjusted：本機補 {len(adjusted_ready):,}/{len(adjusted_auth):,}，剩餘 {len(adjusted_blocked):,}\n"
            f"- official raw：本機補 {len(raw_ready):,}/{len(raw_auth):,}，剩餘 {len(raw_blocked):,}\n"
            f"- reusable close index：{len(index):,} rows\n"
            "- prior checkpoints只保留當輪target rows，未保留完整route payload。\n"
            "- network_requests=0；future_data_violation_count=0。\n"
        ))
        step(output, "completed_ready_for_core_local_extraction_absorption", **readiness)
        rebuild_manifest(output)
    finally:
        lock.unlink(missing_ok=True)


if __name__ == "__main__":
    run()
