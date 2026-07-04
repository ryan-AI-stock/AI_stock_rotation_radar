from __future__ import annotations

import csv
import hashlib
import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path


TASK_ID = "TASK-RADAR-DATA-STORAGE-CHECKSUM-ARCHIVE-DRYRUN-20260704"
OUTPUT_DIR = Path(__file__).resolve().parent
REPO_ROOT = OUTPUT_DIR.parents[1]
OUTPUTS_DIR = REPO_ROOT / "outputs"
AUDIT_DIR = OUTPUTS_DIR / "radar_storage_governance_audit_20260704"
ARCHIVE_CANDIDATES = AUDIT_DIR / "archive_or_compress_candidates.csv"

RAW_EXTENSIONS = {
    ".pdf",
    ".html",
    ".htm",
    ".json",
    ".jsonl",
    ".zip",
    ".har",
    ".png",
    ".jpg",
    ".jpeg",
    ".webp",
    ".xml",
}
GOVERNANCE_KEYWORDS = (
    "manifest",
    "readiness",
    "future_data_violation_audit",
    "source_manifest",
    "final_summary",
    "completed",
    "failed",
    "run_log",
    "coverage",
    "accepted_",
    "blocked_",
    "rejected_",
)
NO_TOUCH_PACKAGE_PATTERNS = (
    "0050_pit",
    "pcf_daily_full_range",
    "all_listed_liquid_universe",
    "pool1b_price_cache_repair",
    "mops_monthly_revenue",
    "quarterly_fundamentals_full_sweep",
    "listing",
    "status",
    "transition",
    "market_cap",
    "capital_stock",
)


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


def read_csv(path: Path) -> list[dict]:
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def is_governance_file(rel: str) -> bool:
    name = Path(rel).name.lower()
    return any(k in name for k in GOVERNANCE_KEYWORDS)


def artifact_class(path: Path, package_name: str, package_source_class: str) -> str:
    rel = str(path).replace("\\", "/").lower()
    suffix = path.suffix.lower()
    if "browser" in package_name.lower() or "browser" in rel or suffix == ".har":
        return "browser_artifact"
    if "raw_sources" in rel or "raw_source" in rel or suffix in RAW_EXTENSIONS:
        return "raw_source"
    if "failed_or_superseded" in package_source_class:
        return "failed_route_artifact"
    return "failed_route_bulky_artifact"


def compression_ratio(path: Path, artifact: str) -> float:
    suffix = path.suffix.lower()
    if suffix in {".zip", ".png", ".jpg", ".jpeg", ".webp", ".pdf"}:
        return 0.92
    if suffix in {".json", ".jsonl", ".html", ".htm", ".xml", ".har", ".csv", ".txt"}:
        return 0.35
    if artifact == "browser_artifact":
        return 0.45
    return 0.60


def should_include_file(path: Path, package_root: Path, package_source_class: str) -> tuple[bool, str]:
    rel = str(path.relative_to(package_root)).replace("\\", "/")
    lower = rel.lower()
    suffix = path.suffix.lower()
    size = path.stat().st_size
    if path.name in {".gitignore", ".gitkeep"}:
        return False, "control_file_excluded"
    if is_governance_file(lower):
        return False, "governance_ledger_excluded"
    if "raw_sources/" in lower or "raw_source" in lower:
        return True, "raw_source_path"
    if suffix in {".pdf", ".html", ".htm", ".zip", ".har"}:
        return True, "raw_artifact_extension"
    if suffix in {".json", ".jsonl", ".xml", ".png", ".jpg", ".jpeg", ".webp"} and size >= 64 * 1024:
        return True, "raw_artifact_extension_size_threshold"
    if "failed_or_superseded" in package_source_class and size >= 1024 * 1024:
        return True, "failed_route_bulky_file_threshold"
    return False, "not_raw_or_bulky_candidate"


def archive_group_for(package_name: str, artifact: str) -> str:
    safe = package_name.replace("radar_", "").replace("/", "_")
    return f"{safe}__{artifact}"


def is_no_touch_package(package_name: str) -> bool:
    lower = package_name.lower()
    return any(pattern in lower for pattern in NO_TOUCH_PACKAGE_PATTERNS)


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUTPUT_DIR / "current_step.txt").write_text("running_checksum_archive_dryrun\n", encoding="utf-8")
    write_csv(
        OUTPUT_DIR / "run_log.csv",
        [{"timestamp_utc": now_iso(), "status": "started", "detail": "checksum raw/archive candidates dry-run only"}],
        ["timestamp_utc", "status", "detail"],
    )

    candidate_rows = read_csv(ARCHIVE_CANDIDATES)
    by_package: dict[str, dict] = {}
    for row in candidate_rows:
        package = row.get("package", "")
        if package and package not in by_package:
            by_package[package] = row

    checksum_rows: list[dict] = []
    skipped_rows: list[dict] = []
    protected_excluded_rows: list[dict] = []
    source_package_rows: list[dict] = []
    hash_to_paths: dict[str, list[str]] = defaultdict(list)
    hash_to_size: dict[str, int] = {}
    hash_to_ratio: dict[str, float] = {}

    for package, row in sorted(by_package.items()):
        package_root = OUTPUTS_DIR / package
        if not package_root.exists():
            skipped_rows.append(
                {
                    "package": package,
                    "relative_path": "",
                    "reason": "package_missing",
                    "size_mb": 0,
                }
            )
            continue
        if is_no_touch_package(package):
            protected_excluded_rows.append(
                {
                    "package": package,
                    "source_class": row.get("source_class", ""),
                    "governance_disposition": row.get("governance_disposition", ""),
                    "source_audit_row_size_mb": row.get("size_mb", ""),
                    "reason": "hard_boundary_no_touch_package_excluded_from_archive_dryrun",
                    "delete_executed": "false",
                    "move_executed": "false",
                    "compress_executed": "false",
                }
            )
            source_package_rows.append(
                {
                    "package": package,
                    "source_class": row.get("source_class", ""),
                    "governance_disposition": row.get("governance_disposition", ""),
                    "candidate_file_count": 0,
                    "candidate_size_mb": 0,
                    "package_file_count": len([p for p in package_root.rglob("*") if p.is_file()]),
                    "dryrun_decision": "protected_no_touch_excluded",
                    "source_audit_row_size_mb": row.get("size_mb", ""),
                    "notes": "Excluded because package matches hard-boundary protected data class.",
                }
            )
            continue
        source_class = row.get("source_class", "")
        disposition = row.get("governance_disposition", "")
        package_file_count = 0
        package_candidate_count = 0
        package_candidate_size = 0
        for path in sorted(p for p in package_root.rglob("*") if p.is_file()):
            package_file_count += 1
            include, reason = should_include_file(path, package_root, source_class)
            rel_repo = str(path.relative_to(REPO_ROOT)).replace("\\", "/")
            if not include:
                if path.stat().st_size >= 10 * 1024 * 1024:
                    skipped_rows.append(
                        {
                            "package": package,
                            "relative_path": rel_repo,
                            "reason": reason,
                            "size_mb": mb(path.stat().st_size),
                        }
                    )
                continue
            size = path.stat().st_size
            artifact = artifact_class(path, package, source_class)
            digest = sha256_file(path)
            hash_to_paths[digest].append(rel_repo)
            hash_to_size[digest] = size
            ratio = compression_ratio(path, artifact)
            hash_to_ratio[digest] = ratio
            archive_group = archive_group_for(package, artifact)
            package_candidate_count += 1
            package_candidate_size += size
            checksum_rows.append(
                {
                    "package": package,
                    "relative_path": rel_repo,
                    "artifact_class": artifact,
                    "source_class": source_class,
                    "governance_disposition": disposition,
                    "size_bytes": size,
                    "size_mb": mb(size),
                    "mtime_utc": datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).replace(microsecond=0).isoformat(),
                    "sha256": digest,
                    "archive_group": archive_group,
                    "estimated_compression_ratio": ratio,
                    "estimated_compressed_size_mb": mb(int(size * ratio)),
                    "restore_source": rel_repo,
                    "approval_required": "true",
                    "action_executed": "false",
                }
            )
        source_package_rows.append(
            {
                "package": package,
                "source_class": source_class,
                "governance_disposition": disposition,
                "candidate_file_count": package_candidate_count,
                "candidate_size_mb": mb(package_candidate_size),
                "package_file_count": package_file_count,
                "dryrun_decision": "candidate_files_found" if package_candidate_count else "no_raw_bulky_files_selected",
                "source_audit_row_size_mb": row.get("size_mb", ""),
                "notes": row.get("recommendation", ""),
            }
        )

    for row in checksum_rows:
        paths = hash_to_paths[row["sha256"]]
        row["duplicate_count_for_hash"] = len(paths)
        row["duplicate_group_paths"] = " | ".join(paths[:20])
        if len(paths) > 1:
            row["artifact_class"] = "duplicate_raw_capture"

    checksum_fields = [
        "package",
        "relative_path",
        "artifact_class",
        "source_class",
        "governance_disposition",
        "size_bytes",
        "size_mb",
        "mtime_utc",
        "sha256",
        "duplicate_count_for_hash",
        "duplicate_group_paths",
        "archive_group",
        "estimated_compression_ratio",
        "estimated_compressed_size_mb",
        "restore_source",
        "approval_required",
        "action_executed",
    ]
    write_csv(OUTPUT_DIR / "checksum_manifest.csv", checksum_rows, checksum_fields)
    write_csv(
        OUTPUT_DIR / "source_package_map.csv",
        source_package_rows,
        ["package", "source_class", "governance_disposition", "candidate_file_count", "candidate_size_mb", "package_file_count", "dryrun_decision", "source_audit_row_size_mb", "notes"],
    )
    write_csv(OUTPUT_DIR / "skipped_large_non_archive_files.csv", skipped_rows, ["package", "relative_path", "reason", "size_mb"])
    write_csv(
        OUTPUT_DIR / "protected_excluded_from_dryrun.csv",
        protected_excluded_rows,
        ["package", "source_class", "governance_disposition", "source_audit_row_size_mb", "reason", "delete_executed", "move_executed", "compress_executed"],
    )

    grouped: dict[str, dict] = {}
    for row in checksum_rows:
        key = row["archive_group"]
        group = grouped.setdefault(
            key,
            {
                "archive_group": key,
                "artifact_class": row["artifact_class"],
                "file_count": 0,
                "original_size_bytes": 0,
                "unique_size_bytes": 0,
                "estimated_compressed_size_bytes": 0,
                "estimated_deduped_compressed_size_bytes": 0,
                "duplicate_file_count": 0,
                "planned_archive_path": f"DRYRUN_ONLY/{key}.zip",
                "compress_executed": "false",
                "move_executed": "false",
                "delete_executed": "false",
                "approval_required": "true",
                "reason": "dry-run candidate; user approval required before any archive/compress/move/delete",
            },
        )
        size = int(row["size_bytes"])
        group["file_count"] += 1
        group["original_size_bytes"] += size
        group["estimated_compressed_size_bytes"] += int(size * float(row["estimated_compression_ratio"]))
        if int(row["duplicate_count_for_hash"]) > 1:
            group["duplicate_file_count"] += 1

    unique_hashes_by_group: dict[str, set[str]] = defaultdict(set)
    for row in checksum_rows:
        unique_hashes_by_group[row["archive_group"]].add(row["sha256"])
    for group_key, hashes in unique_hashes_by_group.items():
        grouped[group_key]["unique_size_bytes"] = sum(hash_to_size[h] for h in hashes)
        grouped[group_key]["estimated_deduped_compressed_size_bytes"] = sum(int(hash_to_size[h] * hash_to_ratio[h]) for h in hashes)

    plan_rows = []
    for group in grouped.values():
        row = dict(group)
        row["original_size_mb"] = mb(row.pop("original_size_bytes"))
        row["unique_size_mb"] = mb(row.pop("unique_size_bytes"))
        row["estimated_compressed_size_mb"] = mb(row.pop("estimated_compressed_size_bytes"))
        row["estimated_deduped_compressed_size_mb"] = mb(row.pop("estimated_deduped_compressed_size_bytes"))
        plan_rows.append(row)
    plan_rows.sort(key=lambda r: float(r["original_size_mb"]), reverse=True)
    write_csv(
        OUTPUT_DIR / "archive_dryrun_plan.csv",
        plan_rows,
        [
            "archive_group",
            "artifact_class",
            "file_count",
            "duplicate_file_count",
            "original_size_mb",
            "unique_size_mb",
            "estimated_compressed_size_mb",
            "estimated_deduped_compressed_size_mb",
            "planned_archive_path",
            "compress_executed",
            "move_executed",
            "delete_executed",
            "approval_required",
            "reason",
        ],
    )

    restore_rows = [
        {
            "archive_group": row["archive_group"],
            "original_path": row["relative_path"],
            "planned_archive_path": f"DRYRUN_ONLY/{row['archive_group']}.zip",
            "restore_source": row["restore_source"],
            "sha256": row["sha256"],
            "size_bytes": row["size_bytes"],
            "restore_verified": "false",
            "notes": "Dry-run only; archive not created. Restore source remains original file path.",
        }
        for row in checksum_rows
    ]
    write_csv(
        OUTPUT_DIR / "restore_map.csv",
        restore_rows,
        ["archive_group", "original_path", "planned_archive_path", "restore_source", "sha256", "size_bytes", "restore_verified", "notes"],
    )

    approval_rows = [
        {
            "path": row["relative_path"],
            "size_mb": row["size_mb"],
            "reason": f"{row['artifact_class']} candidate from {row['package']}",
            "restore_source": row["restore_source"],
            "approval_required": "true",
            "delete_executed": "false",
            "move_executed": "false",
            "compress_executed": "false",
        }
        for row in checksum_rows
    ]
    write_csv(
        OUTPUT_DIR / "requires_user_approval.csv",
        approval_rows,
        ["path", "size_mb", "reason", "restore_source", "approval_required", "delete_executed", "move_executed", "compress_executed"],
    )

    dedupe_rows = []
    for digest, paths in sorted(hash_to_paths.items(), key=lambda item: (len(item[1]), hash_to_size[item[0]]), reverse=True):
        if len(paths) < 2:
            continue
        dedupe_rows.append(
            {
                "sha256": digest,
                "duplicate_count": len(paths),
                "size_mb_each": mb(hash_to_size[digest]),
                "duplicate_overhead_mb": mb(hash_to_size[digest] * (len(paths) - 1)),
                "paths": " | ".join(paths[:50]),
            }
        )
    write_csv(OUTPUT_DIR / "dedupe_summary.csv", dedupe_rows, ["sha256", "duplicate_count", "size_mb_each", "duplicate_overhead_mb", "paths"])

    total_original = sum(int(r["size_bytes"]) for r in checksum_rows)
    total_unique = sum(hash_to_size[h] for h in hash_to_paths)
    estimated_compressed = sum(int(int(r["size_bytes"]) * float(r["estimated_compression_ratio"])) for r in checksum_rows)
    estimated_deduped_compressed = sum(int(hash_to_size[h] * hash_to_ratio[h]) for h in hash_to_paths)
    duplicate_overhead = total_original - total_unique
    summary = {
        "task_id": TASK_ID,
        "status": "completed_checksum_archive_dryrun_only",
        "source_audit": str(AUDIT_DIR),
        "candidate_packages": len(by_package),
        "protected_excluded_packages": len(protected_excluded_rows),
        "checksum_manifest_rows": len(checksum_rows),
        "source_package_map_rows": len(source_package_rows),
        "archive_dryrun_plan_rows": len(plan_rows),
        "requires_user_approval_rows": len(approval_rows),
        "dedupe_hash_groups": len(dedupe_rows),
        "candidate_original_size_mb": mb(total_original),
        "candidate_unique_size_mb": mb(total_unique),
        "duplicate_overhead_mb": mb(duplicate_overhead),
        "estimated_compressed_size_mb": mb(estimated_compressed),
        "estimated_deduped_compressed_size_mb": mb(estimated_deduped_compressed),
        "delete_executed": False,
        "move_executed": False,
        "compress_executed": False,
        "raw_data_deleted": False,
        "formal_model_changed": False,
        "trade_decision_changed": False,
        "active_in_trade_decision": False,
    }
    (OUTPUT_DIR / "manifest.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    final = f"""# Storage checksum archive dry-run

## 結論
- 狀態：`completed_checksum_archive_dryrun_only`
- candidate packages：{len(by_package)}
- protected excluded packages：{len(protected_excluded_rows)}
- checksum rows：{len(checksum_rows)}
- 需使用者批准 rows：{len(approval_rows)}
- 原始候選大小：{mb(total_original)} MB
- 去重後唯一候選大小：{mb(total_unique)} MB
- 重複 raw capture overhead：{mb(duplicate_overhead)} MB
- 預估壓縮後大小：{mb(estimated_compressed)} MB
- 去重後預估壓縮大小：{mb(estimated_deduped_compressed)} MB

## 產物
- `checksum_manifest.csv`
- `archive_dryrun_plan.csv`
- `restore_map.csv`
- `source_package_map.csv`
- `requires_user_approval.csv`
- `dedupe_summary.csv`
- `protected_excluded_from_dryrun.csv`

## 邊界
- `delete_executed=false`
- `move_executed=false`
- `compress_executed=false`
- `raw_data_deleted=false`
- `formal_model_changed=false`
- `trade_decision_changed=false`
- `active_in_trade_decision=false`

## 說明
本棒只計算 SHA256、mtime、size、restore path 與 dry-run 壓縮估算。沒有建立 archive，沒有刪除、搬移或壓縮任何檔案。
"""
    (OUTPUT_DIR / "final_summary_zh.md").write_text(final, encoding="utf-8")
    write_csv(OUTPUT_DIR / "completed.csv", [{"task_id": TASK_ID, "status": "completed_checksum_archive_dryrun_only"}], ["task_id", "status"])
    write_csv(OUTPUT_DIR / "failed.csv", [], ["task_id", "status", "reason"])
    (OUTPUT_DIR / "current_step.txt").write_text("completed_checksum_archive_dryrun_only\n", encoding="utf-8")
    write_csv(
        OUTPUT_DIR / "run_log.csv",
        [
            {"timestamp_utc": now_iso(), "status": "started", "detail": "checksum raw/archive candidates dry-run only"},
            {"timestamp_utc": now_iso(), "status": "completed", "detail": f"files={len(checksum_rows)} original_mb={mb(total_original)} unique_mb={mb(total_unique)} estimated_compressed_mb={mb(estimated_compressed)} deduped_compressed_mb={mb(estimated_deduped_compressed)}"},
        ],
        ["timestamp_utc", "status", "detail"],
    )
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
