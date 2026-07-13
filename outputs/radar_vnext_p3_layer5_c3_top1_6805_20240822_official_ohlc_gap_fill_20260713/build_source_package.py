from __future__ import annotations

import csv
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path


TASK_ID = "TASK-RADAR-DATA-VNEXT-P3-LAYER5-C3-TOP1-6805-20240822-OFFICIAL-OHLC-GAP-FILL-001"
REPO = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
CORE = Path(
    r"C:\Users\zergv\Documents\Codex\2026-05-30\ep05-chat-ai-stock-backtest-lab"
    r"\outputs\vnext_p3_layer5_C3_eligible_top1_incumbent_lifecycle_fixed_contract_20260713"
)
UPSTREAM = REPO / "outputs" / "radar_vnext_legacy_rs20_selected_stock_price_path_source_package_20260708"
SOURCE_ROWS = UPSTREAM / "selected_stock_price_rows_local_only.csv"
SOURCE_SHARDS = UPSTREAM / "source_shard_hash_manifest.csv"
UPSTREAM_MANIFEST = UPSTREAM / "manifest.json"
GAP_LEDGER = CORE / "p3_C3_top1_execution_gap_ledger.csv"

TARGET_TICKER = "6805"
TARGET_DATE = "2024-08-22"
TARGET_DECISION_DATE = "2024-08-21"
TARGET_SHARD_TOKEN = "accepted_liquidity_rows_2024_08.csv"

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


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def row_hash(row: dict[str, str]) -> str:
    payload = json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, object]], fieldnames: list[str]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def write_json(path: Path, payload: dict[str, object]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    generated_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()

    gap_rows = read_rows(GAP_LEDGER)
    assert len(gap_rows) == 1, f"Expected one gap row, got {len(gap_rows)}"
    gap = gap_rows[0]
    assert gap["decision_date"] == TARGET_DECISION_DATE
    assert gap["top1_ticker"] == TARGET_TICKER
    assert gap["next_execution_date"] == TARGET_DATE

    matches = [
        row
        for row in read_rows(SOURCE_ROWS)
        if row["ticker"] == TARGET_TICKER and row["date"] == TARGET_DATE
    ]
    assert len(matches) == 1, f"Expected one exact official source row, got {len(matches)}"
    source = matches[0]
    assert source["market"] == "TWSE"
    assert source["source_type"] == "official_daily_trading_pit"
    assert source["ready_for_core_cost_timing_unadjusted"].lower() == "true"
    for field in ("open", "high", "low", "close"):
        assert source[field] not in ("", None)

    shard_matches = [
        row for row in read_rows(SOURCE_SHARDS) if TARGET_SHARD_TOKEN in row["source_path"]
    ]
    assert len(shard_matches) == 1
    shard = shard_matches[0]
    assert shard["exists"].lower() == "true"

    upstream_manifest = json.loads(UPSTREAM_MANIFEST.read_text(encoding="utf-8"))
    source_exact_hash = row_hash(source)
    source_compact_hash = sha256_file(SOURCE_ROWS)

    filled_path = OUT / "p3_C3_top1_6805_20240822_official_ohlc_filled_rows.csv"
    filled_fields = [
        "decision_date", "next_execution_date", "ticker", "name", "market",
        "open", "high", "low", "close", "volume", "turnover_value",
        "official_raw_execution_ohlc_ready", "adjusted_analysis_ohlc_used",
        "source_quality", "source_type", "source_id", "source_url",
        "source_date", "source_row_sha256", "source_shard_sha256",
        "source_compact_sha256", "cache_reuse", "adjustment_policy",
        "accepted_for_core_execution_absorption", "accepted_for_formal",
        "future_data_violation_count",
    ]
    filled = {
        "decision_date": TARGET_DECISION_DATE,
        "next_execution_date": TARGET_DATE,
        "ticker": source["ticker"],
        "name": source["name"],
        "market": source["market"],
        "open": source["open"],
        "high": source["high"],
        "low": source["low"],
        "close": source["close"],
        "volume": source["volume"],
        "turnover_value": source["turnover_value"],
        "official_raw_execution_ohlc_ready": True,
        "adjusted_analysis_ohlc_used": False,
        "source_quality": "official_exact_unadjusted_execution_ohlcv_cache_reuse",
        "source_type": source["source_type"],
        "source_id": source["source_id"],
        "source_url": source["source_url"],
        "source_date": source["source_date"],
        "source_row_sha256": source_exact_hash,
        "source_shard_sha256": shard["sha256"],
        "source_compact_sha256": source_compact_hash,
        "cache_reuse": True,
        "adjustment_policy": source["adjustment_policy"],
        "accepted_for_core_execution_absorption": True,
        "accepted_for_formal": False,
        "future_data_violation_count": 0,
    }
    write_csv(filled_path, [filled], filled_fields)

    manifest_path = OUT / "p3_C3_top1_6805_20240822_official_ohlc_source_manifest.csv"
    manifest_fields = [
        "ticker", "target_date", "route", "source_url", "source_quality",
        "source_row_sha256", "source_compact_path", "source_compact_sha256",
        "source_shard_path", "source_shard_sha256", "upstream_package_created_at_utc",
        "package_materialized_at_utc", "new_download_performed", "market_available_at_policy",
        "retrieval_time_as_market_date", "future_data_violation_count",
    ]
    manifest_row = {
        "ticker": TARGET_TICKER,
        "target_date": TARGET_DATE,
        "route": "TWSE_MI_INDEX_ALLBUT0999_OFFICIAL_DAILY_CACHE",
        "source_url": source["source_url"],
        "source_quality": "official_exact_unadjusted_execution_ohlcv_cache_reuse",
        "source_row_sha256": source_exact_hash,
        "source_compact_path": str(SOURCE_ROWS),
        "source_compact_sha256": source_compact_hash,
        "source_shard_path": shard["source_path"],
        "source_shard_sha256": shard["sha256"],
        "upstream_package_created_at_utc": upstream_manifest["created_at_utc"],
        "package_materialized_at_utc": generated_at,
        "new_download_performed": False,
        "market_available_at_policy": "execution_date official EOD row; used only as realized next-day execution price, not as decision-date feature",
        "retrieval_time_as_market_date": False,
        "future_data_violation_count": 0,
    }
    write_csv(manifest_path, [manifest_row], manifest_fields)

    blocked_path = OUT / "p3_C3_top1_6805_20240822_official_ohlc_blocked_ledger.csv"
    write_csv(
        blocked_path,
        [],
        ["decision_date", "next_execution_date", "ticker", "blocked_reason", "attempted_source", "future_data_violation_count"],
    )

    audit_path = OUT / "p3_C3_top1_6805_20240822_official_ohlc_future_data_audit.csv"
    write_csv(
        audit_path,
        [
            {
                "audit_item": "decision_to_execution_timing",
                "status": "pass",
                "detail": "2024-08-21 decision uses 2024-08-22 official raw OHLC only as next-day execution realization",
                "future_data_violation_count": 0,
            },
            {
                "audit_item": "no_substitution",
                "status": "pass",
                "detail": "exact ticker/date row; no neighbor, last-price, adjusted-analysis, or benchmark substitution",
                "future_data_violation_count": 0,
            },
            {
                "audit_item": "retrieval_metadata",
                "status": "pass",
                "detail": "package materialization time is metadata and is not used as market date",
                "future_data_violation_count": 0,
            },
        ],
        ["audit_item", "status", "detail", "future_data_violation_count"],
    )

    readiness_path = OUT / "readiness_for_core_p3_C3_top1_6805_20240822_ohlc_absorption.json"
    readiness = {
        "task_id": TASK_ID,
        "status": "exact_official_raw_execution_ohlc_ready_for_core_absorption",
        "input_gap_rows": 1,
        "filled_rows": 1,
        "blocked_rows": 0,
        "official_unadjusted_ohlc_ready_share": 1.0,
        "next_execution_date_exact_ready": True,
        "ready_for_core_p3_C3_top1_execution_ohlc_absorption": True,
        "ready_for_experiments": False,
        "new_download_performed": False,
        "adjusted_analysis_ohlc_used": False,
        "future_data_violation_count": 0,
        **FLAGS,
    }
    write_json(readiness_path, readiness)

    summary_path = OUT / "final_summary_zh.md"
    summary_path.write_text(
        "# P3 C3 Top1 6805 execution OHLC 補件\n\n"
        "- 唯一 gap 已由既有 TWSE 官方日行情 cache exact-key 補齊。\n"
        "- 2024-08-22 富世達（6805）：open 807、high 814、low 786、close 786。\n"
        "- 使用官方未調整 execution OHLC；沒有使用鄰日、last price、adjusted analysis 或 benchmark。\n"
        "- 本次沒有新下載；來源列、上游 compact 與原始月 shard checksum 均已保存。\n"
        "- ready_for_core_p3_C3_top1_execution_ohlc_absorption=true。\n"
        "- ready_for_experiments=false；由 Core 吸收後刷新 123 個 Top1 execution readiness。\n"
        "- future_data_violation_count=0。\n",
        encoding="utf-8",
    )

    current_step_path = OUT / "current_step.txt"
    current_step_path.write_text("completed_ready_for_core_absorption\n", encoding="utf-8")

    artifacts = [
        filled_path,
        manifest_path,
        blocked_path,
        audit_path,
        readiness_path,
        summary_path,
        current_step_path,
        Path(__file__).resolve(),
    ]
    package_manifest = {
        "task_id": TASK_ID,
        "generated_at_utc": generated_at,
        "artifacts": [
            {"path": item.name, "size_bytes": item.stat().st_size, "sha256": sha256_file(item)}
            for item in artifacts
        ],
        "source_package_reused": str(UPSTREAM),
        "new_download_performed": False,
        "future_data_violation_count": 0,
        **FLAGS,
    }
    write_json(OUT / "manifest.json", package_manifest)


if __name__ == "__main__":
    main()
