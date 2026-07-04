from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path


TASK_ID = "TASK-RADAR-DATA-STORAGE-GOVERNANCE-AUDIT-20260704"
OUTPUT_DIR = Path(__file__).resolve().parent
REPO_ROOT = OUTPUT_DIR.parents[1]
OUTPUTS_DIR = REPO_ROOT / "outputs"


PROTECTED_PATTERNS = [
    "pcf_daily_full_range_pit_candidate",
    "all_listed_liquid_universe_full_sweep",
    "pool1b_price_cache_repair",
    "mops_monthly_revenue_full_universe_pit",
    "quarterly_fundamentals_full_sweep",
    "tpex_historical_full_sweep",
    "tpex_suspension_transition_event_ledger",
    "market_cap_twse_route_tpex_full_sweep",
    "twse_capital_stock_full_sweep_proxy_contract",
    "listing_master_completion",
    "listing_delisting_suspension_master",
]

DIAGNOSTIC_PATTERNS = [
    "mops_document_extraction_v1",
    "mops_mainline_evidence_ledger",
    "sector_taxonomy_readiness",
    "sector_mainline_pit_source_package",
    "sector_mainline_pit_full_sweep",
    "tpex_static_reverse_archive_probe",
    "tpex_historical_listing_status_master",
]

SUPERSEDED_OR_ROUTE_ATTEMPT_PATTERNS = [
    "historical_source_download",
    "archived_html_crawler",
    "dated_api_disclosure_phase4",
    "endpoint_post_probe_phase5",
    "session_replay_phase6",
    "browser_network_capture_phase7",
    "formal_pit_source_phase8",
    "pit_source_acquisition_20260703",
]

RAW_MARKERS = ("raw_sources", "raw_source", "browser_capture", "html", "pdf", "json")
SHARD_MARKERS = ("shard", "shards", "_rows_20", "accepted_liquidity_rows_", "market_cap_rows_")
CACHE_MARKERS = ("cache_compatible", "cache-compatible")


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def mb(size: int) -> float:
    return round(size / 1024 / 1024, 3)


def write_csv(path: Path, rows: list[dict], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def package_category(name: str) -> tuple[str, str, str]:
    if any(p in name for p in PROTECTED_PATTERNS):
        return (
            "formal_or_source_backed_normalized_candidate",
            "keep_required_for_backtest",
            "保留 normalized rows/shards、manifest、readiness、future-data audit；raw source 可另列壓縮候選。",
        )
    if any(p in name for p in DIAGNOSTIC_PATTERNS):
        return (
            "diagnostic_only_evidence",
            "diagnostic_keep_optional",
            "保留 evidence ledger、manifest、audit；raw PDF/HTML 可壓縮封存，不可刪除尚未備份資料。",
        )
    if any(p in name for p in SUPERSEDED_OR_ROUTE_ATTEMPT_PATTERNS):
        return (
            "failed_or_superseded_route_attempt_evidence",
            "archive_or_compress_candidates",
            "保留 summary/manifest/attempt logs；raw wrappers、HTML、PDF、browser artifact 可壓縮封存。",
        )
    return (
        "proxy_partial_or_blocked_evidence",
        "diagnostic_keep_optional",
        "保留 package summary 與 readiness；依檔案型態分流 raw/archive 與 normalized rows。",
    )


def classify_file(path: Path, package_root: Path) -> str:
    rel = str(path.relative_to(package_root)).replace("\\", "/").lower()
    suffix = path.suffix.lower()
    if "raw_sources/" in rel or "raw_source" in rel or suffix in {".pdf", ".html", ".htm", ".zip"}:
        return "raw_source_archive"
    if any(marker in rel for marker in CACHE_MARKERS):
        return "cache_compatible_candidate"
    if any(marker in rel for marker in SHARD_MARKERS) or suffix in {".parquet", ".feather"}:
        return "large_local_shard"
    if suffix in {".csv", ".json", ".md", ".txt"}:
        if any(key in rel for key in ("manifest", "readiness", "audit", "summary", "coverage", "completed", "failed", "run_log")):
            return "source_manifest_or_governance_ledger"
        return "normalized_or_attempt_ledger"
    return "intermediate_or_unknown"


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUTPUT_DIR / "current_step.txt").write_text("running_storage_governance_audit\n", encoding="utf-8")
    write_csv(
        OUTPUT_DIR / "run_log.csv",
        [{"timestamp_utc": now_iso(), "status": "started", "detail": "scan outputs package sizes and governance classes"}],
        ["timestamp_utc", "status", "detail"],
    )

    inventory: list[dict] = []
    keep_required: list[dict] = []
    diagnostic_optional: list[dict] = []
    archive_candidates: list[dict] = []
    disposable_candidates: list[dict] = []
    large_shards: list[dict] = []

    package_dirs = [p for p in OUTPUTS_DIR.iterdir() if p.is_dir() and p != OUTPUT_DIR]
    total_size = 0
    total_files = 0

    for package in sorted(package_dirs, key=lambda p: p.name):
        files = [p for p in package.rglob("*") if p.is_file()]
        size = sum(p.stat().st_size for p in files)
        total_size += size
        total_files += len(files)
        class_counts: dict[str, int] = {}
        class_sizes: dict[str, int] = {}
        largest_file = ""
        largest_file_size = 0
        raw_size = shard_size = cache_size = 0

        for f in files:
            f_size = f.stat().st_size
            f_class = classify_file(f, package)
            class_counts[f_class] = class_counts.get(f_class, 0) + 1
            class_sizes[f_class] = class_sizes.get(f_class, 0) + f_size
            if f_size > largest_file_size:
                largest_file = str(f.relative_to(REPO_ROOT)).replace("\\", "/")
                largest_file_size = f_size
            if f_class == "raw_source_archive":
                raw_size += f_size
            elif f_class == "large_local_shard":
                shard_size += f_size
            elif f_class == "cache_compatible_candidate":
                cache_size += f_size
            if f_size >= 10 * 1024 * 1024 or f_class in {"large_local_shard", "cache_compatible_candidate"}:
                large_shards.append(
                    {
                        "package": package.name,
                        "relative_path": str(f.relative_to(REPO_ROOT)).replace("\\", "/"),
                        "file_class": f_class,
                        "size_mb": mb(f_size),
                        "recommendation": (
                            "keep local normalized shard; consider consolidated normalized data directory"
                            if f_class in {"large_local_shard", "cache_compatible_candidate"}
                            else "archive/compress raw artifact after manifest is verified"
                        ),
                    }
                )

        source_class, disposition, recommendation = package_category(package.name)
        row = {
            "package": package.name,
            "relative_path": str(package.relative_to(REPO_ROOT)).replace("\\", "/"),
            "size_mb": mb(size),
            "file_count": len(files),
            "source_class": source_class,
            "governance_disposition": disposition,
            "raw_source_size_mb": mb(raw_size),
            "large_shard_size_mb": mb(shard_size),
            "cache_compatible_size_mb": mb(cache_size),
            "largest_file": largest_file,
            "largest_file_size_mb": mb(largest_file_size),
            "recommendation": recommendation,
            "delete_allowed": "false",
            "notes": json.dumps({k: {"count": class_counts[k], "size_mb": mb(class_sizes[k])} for k in sorted(class_counts)}, ensure_ascii=False),
        }
        inventory.append(row)
        if disposition == "keep_required_for_backtest":
            keep_required.append(row)
        elif disposition == "diagnostic_keep_optional":
            diagnostic_optional.append(row)
        elif disposition == "archive_or_compress_candidates":
            archive_candidates.append(row)
        else:
            disposable_candidates.append(row)

        if raw_size > 0 and disposition != "keep_required_for_backtest":
            archive_candidates.append({**row, "governance_disposition": "raw_archive_compress_candidate"})

    inventory.sort(key=lambda r: float(r["size_mb"]), reverse=True)
    large_shards.sort(key=lambda r: float(r["size_mb"]), reverse=True)

    inv_fields = [
        "package",
        "relative_path",
        "size_mb",
        "file_count",
        "source_class",
        "governance_disposition",
        "raw_source_size_mb",
        "large_shard_size_mb",
        "cache_compatible_size_mb",
        "largest_file",
        "largest_file_size_mb",
        "recommendation",
        "delete_allowed",
        "notes",
    ]
    write_csv(OUTPUT_DIR / "storage_inventory.csv", inventory, inv_fields)
    write_csv(OUTPUT_DIR / "keep_required_for_backtest.csv", keep_required, inv_fields)
    write_csv(OUTPUT_DIR / "diagnostic_keep_optional.csv", diagnostic_optional, inv_fields)
    write_csv(OUTPUT_DIR / "archive_or_compress_candidates.csv", archive_candidates, inv_fields)
    write_csv(OUTPUT_DIR / "disposable_rebuildable_candidates.csv", disposable_candidates, inv_fields)
    write_csv(
        OUTPUT_DIR / "large_shard_manifest.csv",
        large_shards,
        ["package", "relative_path", "file_class", "size_mb", "recommendation"],
    )

    raw_policy = [
        {
            "artifact_type": "normalized candidate shards / cache-compatible rows",
            "policy": "keep_local_required_for_backtest",
            "delete_allowed": "false",
            "compress_candidate": "false",
            "notes": "Includes 0050 PCF, full-market liquidity, Pool1B price repair, MOPS revenue/fundamentals, market-cap candidate, listing/status metadata.",
        },
        {
            "artifact_type": "raw PDF / HTML / JSON / browser wrapper",
            "policy": "archive_or_compress_after_manifest_verified",
            "delete_allowed": "false",
            "compress_candidate": "true",
            "notes": "Do not delete in this task. Compress only after source manifest and checksum plan exist.",
        },
        {
            "artifact_type": "failed route attempts / intermediate probes",
            "policy": "keep_manifest_summary_attempt_log; archive bulky raw artifacts",
            "delete_allowed": "false",
            "compress_candidate": "true",
            "notes": "Evidence is useful for blocker history, but raw failed artifacts should not dominate local storage.",
        },
        {
            "artifact_type": "future-data audits / readiness ledgers / source manifests",
            "policy": "always_keep_tracked",
            "delete_allowed": "false",
            "compress_candidate": "false",
            "notes": "These are governance evidence and must stay accessible.",
        },
    ]
    write_csv(OUTPUT_DIR / "raw_source_archive_policy.csv", raw_policy, ["artifact_type", "policy", "delete_allowed", "compress_candidate", "notes"])

    protected_size = sum(float(r["size_mb"]) for r in keep_required)
    archive_size = sum(float(r["size_mb"]) for r in archive_candidates)
    large_size = sum(float(r["size_mb"]) for r in large_shards)
    summary = {
        "task_id": TASK_ID,
        "status": "completed_audit_plan_only",
        "output_path": str(OUTPUT_DIR),
        "scanned_packages": len(inventory),
        "scanned_files": total_files,
        "total_outputs_size_mb": mb(total_size),
        "keep_required_for_backtest_packages": len(keep_required),
        "keep_required_for_backtest_size_mb": round(protected_size, 3),
        "diagnostic_keep_optional_packages": len(diagnostic_optional),
        "archive_or_compress_candidate_rows": len(archive_candidates),
        "archive_or_compress_candidate_size_mb_duplicated_rows_possible": round(archive_size, 3),
        "large_shard_manifest_rows": len(large_shards),
        "large_shard_manifest_size_mb": round(large_size, 3),
        "delete_executed": False,
        "raw_data_deleted": False,
        "formal_model_changed": False,
        "trade_decision_changed": False,
        "active_in_trade_decision": False,
    }
    (OUTPUT_DIR / "manifest.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    plan = f"""# Normalized Data Consolidation Plan

## Scope
This audit scanned `outputs/` only and did not delete, move, or compress files.

## Current Size
- Packages scanned: {len(inventory)}
- Files scanned: {total_files}
- Total estimated size: {mb(total_size)} MB
- Protected backtest/source-candidate packages: {len(keep_required)} packages, {round(protected_size, 3)} MB

## Consolidation Recommendation
1. Create a shared normalized data area outside ad-hoc task outputs, for example `data/normalized_candidates/`.
2. Move only after a separate approved migration task:
   - 0050 PCF daily/monthly candidate rows.
   - Full-market TWSE/TPEx liquidity rows.
   - Pool1B repaired price cache including `6488.TWO`.
   - MOPS monthly revenue and quarterly fundamentals full-universe rows.
   - TPEx/TWSE listing/status/transition ledgers.
   - Market-cap source-candidate shards.
3. Keep every package `manifest.json`, `readiness_for_core.json`, `future_data_violation_audit.csv`, `source_manifest*`, and final summaries tracked in their original output package.
4. Raw PDFs/HTML/JSON/browser artifacts should be compressed or archived only after a checksum manifest exists. This audit does not authorize deletion.
5. Failed route attempts should retain summary/manifest/attempt CSVs. Bulky raw artifacts from failed routes are archive candidates, not immediate deletion candidates.

## Protected Data
Do not remove without a separate approval and verified backup:
- 0050 PIT / PCF full-range candidate.
- 2015-latest TWSE/TPEx liquidity and price data.
- Pool1B price repair, including `6488.TWO`.
- MOPS monthly revenue and quarterly fundamentals full-universe candidates.
- Listing/status metadata and transition ledgers.
- Source manifests, readiness ledgers, and future-data audits.

## Execution Boundary
- `delete_executed=false`
- `raw_data_deleted=false`
- `formal_model_changed=false`
- `trade_decision_changed=false`
- `active_in_trade_decision=false`
"""
    (OUTPUT_DIR / "normalized_data_consolidation_plan.md").write_text(plan, encoding="utf-8")

    final = f"""# RADAR/Data storage governance audit

## 結論
- 狀態：`completed_audit_plan_only`
- 掃描 packages：{len(inventory)}
- 掃描檔案：{total_files}
- `outputs/` 估計大小：{mb(total_size)} MB
- 最大 package：`{inventory[0]['package'] if inventory else ''}`，{inventory[0]['size_mb'] if inventory else 0} MB
- 不可動 / 回測必要 packages：{len(keep_required)}，約 {round(protected_size, 3)} MB
- large shard / cache candidate rows：{len(large_shards)}

## 不可動資料
- 0050 PIT / PCF full-range candidate。
- 2015-latest TWSE/TPEx liquidity / price data。
- Pool1B price repair including `6488.TWO`。
- MOPS monthly revenue / quarterly fundamentals full-universe candidate。
- listing/status metadata、transition ledgers。
- source manifests / readiness ledgers / future-data audits。

## 可瘦身方向
- raw PDF/HTML/JSON/browser artifacts：先補 checksum manifest，再壓縮封存。
- failed route attempts：保留 manifest/summary/attempt logs， bulky raw artifacts 列 archive candidate。
- normalized/cache-compatible 大表：另開 migration task 集中到共用 normalized data directory，不能在本 audit 直接搬移。

## 邊界
- `delete_executed=false`
- `raw_data_deleted=false`
- `formal_model_changed=false`
- `trade_decision_changed=false`
- `active_in_trade_decision=false`
"""
    (OUTPUT_DIR / "final_summary_zh.md").write_text(final, encoding="utf-8")
    write_csv(OUTPUT_DIR / "completed.csv", [{"task_id": TASK_ID, "status": "completed_audit_plan_only"}], ["task_id", "status"])
    write_csv(OUTPUT_DIR / "failed.csv", [], ["task_id", "status", "reason"])
    (OUTPUT_DIR / "current_step.txt").write_text("completed_audit_plan_only\n", encoding="utf-8")
    write_csv(
        OUTPUT_DIR / "run_log.csv",
        [
            {"timestamp_utc": now_iso(), "status": "started", "detail": "scan outputs package sizes and governance classes"},
            {"timestamp_utc": now_iso(), "status": "completed", "detail": f"packages={len(inventory)} files={total_files} size_mb={mb(total_size)}"},
        ],
        ["timestamp_utc", "status", "detail"],
    )
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
